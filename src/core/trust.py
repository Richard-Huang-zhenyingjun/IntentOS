"""
Deterministic trust engine.

Trust is NOT "AI confidence." It's a measurable safety metric
computed from observable execution outcomes.

Design:
- Penalty tiers (MINOR/MODERATE/SEVERE) with clear semantics
- Trust only decreases from penalties; bounded recovery on success
- Re-auth threshold triggers when trust drops too low
- All updates logged as events for replay
"""
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


class PenaltySeverity(Enum):
    """
    Structured penalty tiers.
    
    Design: 2 SEVERE events = re-auth threshold (at default 0.55).
    This makes the relationship between events and thresholds predictable.
    """
    MINOR = "minor"         # -0.05: expected imperfections
    MODERATE = "moderate"   # -0.12: concerning but recoverable
    SEVERE = "severe"       # -0.22: significant safety concern


# Penalty values per severity
PENALTY_VALUES = {
    PenaltySeverity.MINOR: 0.05,
    PenaltySeverity.MODERATE: 0.12,
    PenaltySeverity.SEVERE: 0.22,
}

# Map execution events to penalty severities
DEFAULT_PENALTY_MAP = {
    'primitive_timeout': PenaltySeverity.MODERATE,
    'grasp_retry': PenaltySeverity.MINOR,
    'grasp_fail': PenaltySeverity.SEVERE,
    'unreachable_skip': PenaltySeverity.MODERATE,
    'object_timeout': PenaltySeverity.SEVERE,
    'ik_fail': PenaltySeverity.MODERATE,
    'out_of_bounds': PenaltySeverity.MODERATE,
    'object_missing': PenaltySeverity.MINOR,
}

# Recovery on success
SUCCESS_RECOVERY = 0.03  # Per successful object completion


@dataclass
class TrustSnapshot:
    """Immutable trust state at a point in time"""
    task_trust: float
    object_index: int
    event_type: str
    penalty_applied: float
    recovery_applied: float
    timestamp_ms: float
    details: Dict[str, Any] = field(default_factory=dict)


class TrustEngine:
    """
    Computes and tracks trust across a task session.
    
    Trust starts at 1.0 each session.
    Penalties decrease trust on failures.
    Bounded recovery increases trust on successes.
    Re-auth triggers when trust drops below threshold.
    
    All updates are deterministic: same inputs → same trust trajectory.
    """
    
    def __init__(self, config: dict):
        trust_cfg = config.get('trust', {})
        
        self.init_trust = trust_cfg.get('init_task_trust', 1.0)
        self.recovery_per_success = trust_cfg.get('recovery_per_success', SUCCESS_RECOVERY)
        self.max_recovery_trust = trust_cfg.get('max_recovery_trust', 0.90)
        
        # Penalty overrides from config
        penalty_cfg = trust_cfg.get('penalties', {})
        self.penalty_map = dict(DEFAULT_PENALTY_MAP)
        # Allow config to override severity assignments
        for event_name, severity_str in penalty_cfg.items():
            if isinstance(severity_str, str):
                try:
                    self.penalty_map[event_name] = PenaltySeverity(severity_str.lower())
                except ValueError:
                    pass
        
        # Re-auth thresholds
        reauth_cfg = trust_cfg.get('reauth', {})
        self.reauth_enabled = reauth_cfg.get('enable', True)
        self.reauth_trust_threshold = reauth_cfg.get('task_trust_below', 0.55)
        self.reauth_consecutive_failures = reauth_cfg.get('consecutive_failures', 2)
        
        # State
        self._task_trust: float = self.init_trust
        self._consecutive_failures: int = 0
        self._history: List[TrustSnapshot] = []
        self._current_object_index: int = 0
        self._session_active: bool = False
        
        # Decision quality modifier
        self._auth_quality: float = 1.0
    
    def start_session(self, auth_quality: float = 1.0):
        """Reset trust for new task session"""
        self._task_trust = self.init_trust
        self._consecutive_failures = 0
        self._history = []
        self._current_object_index = 0
        self._session_active = True
        self._auth_quality = auth_quality
        
        # Apply quality modifier: low-quality authorization starts with lower trust
        if auth_quality < 1.0:
            quality_modifier = 0.6 + 0.4 * auth_quality  # Range [0.6, 1.0]
            self._task_trust *= quality_modifier
            self._record('session_start', penalty=1.0 - self._task_trust,
                         details={'auth_quality': auth_quality, 'modifier': quality_modifier})
        else:
            self._record('session_start', details={'auth_quality': auth_quality})
        
        logger.info(f"[TRUST] Session started: trust={self._task_trust:.3f}")
    
    def record_primitive_result(self, error_code: str, object_index: int):
        """
        Record a primitive execution result.
        
        Args:
            error_code: Error code string (from ErrorCode enum .value)
                       "none" for success
            object_index: Which object this primitive belongs to
        """
        self._current_object_index = object_index
        
        if error_code == "none":
            # Success — no penalty, no recovery at primitive level
            return
        
        # Look up penalty
        severity = self.penalty_map.get(error_code)
        if severity is None:
            logger.debug(f"[TRUST] Unknown error code: {error_code}, applying MINOR")
            severity = PenaltySeverity.MINOR
        
        penalty = PENALTY_VALUES[severity]
        self._task_trust = max(0.0, self._task_trust - penalty)
        
        self._record(
            f'penalty_{error_code}',
            penalty=penalty,
            details={'severity': severity.value, 'error_code': error_code},
        )
        
        logger.info(
            f"[TRUST] Penalty: {error_code} ({severity.value}, -{penalty:.3f}) "
            f"→ trust={self._task_trust:.3f}"
        )
    
    def record_object_complete(self, success: bool, object_index: int):
        """Record object completion (success or failure)"""
        self._current_object_index = object_index
        
        if success:
            self._consecutive_failures = 0
            
            # Bounded recovery: trust can increase, but not above max_recovery
            if self._task_trust < self.max_recovery_trust:
                recovery = min(
                    self.recovery_per_success,
                    self.max_recovery_trust - self._task_trust,
                )
                self._task_trust += recovery
                self._record('object_success', recovery=recovery)
                logger.info(f"[TRUST] Recovery +{recovery:.3f} → trust={self._task_trust:.3f}")
            else:
                self._record('object_success')
        else:
            self._consecutive_failures += 1
            self._record(
                'object_failed',
                details={'consecutive_failures': self._consecutive_failures},
            )
            logger.info(
                f"[TRUST] Object failed (consecutive={self._consecutive_failures})"
            )
    
    def record_object_skipped(self, reason: str, object_index: int):
        """Record object skipped (unreachable, out of bounds, etc.)"""
        self._current_object_index = object_index
        
        severity = self.penalty_map.get(reason, PenaltySeverity.MODERATE)
        penalty = PENALTY_VALUES[severity]
        self._task_trust = max(0.0, self._task_trust - penalty)
        self._consecutive_failures += 1
        
        self._record(
            f'object_skipped_{reason}',
            penalty=penalty,
            details={'reason': reason, 'consecutive_failures': self._consecutive_failures},
        )
    
    def should_reauth(self) -> Optional[str]:
        """
        Check if re-authorization should be triggered.
        
        Returns:
            Reason string if re-auth needed, None if trust is okay.
        """
        if not self.reauth_enabled:
            return None
        
        if self._task_trust < self.reauth_trust_threshold:
            return f"trust_below_threshold ({self._task_trust:.3f} < {self.reauth_trust_threshold})"
        
        if self._consecutive_failures >= self.reauth_consecutive_failures:
            return f"consecutive_failures ({self._consecutive_failures} >= {self.reauth_consecutive_failures})"
        
        return None
    
    def end_session(self):
        """Mark session as ended"""
        self._session_active = False
        self._record('session_end', details={
            'final_trust': self._task_trust,
            'consecutive_failures': self._consecutive_failures,
        })
    
    @property
    def task_trust(self) -> float:
        return self._task_trust
    
    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures
    
    def get_history(self) -> List[TrustSnapshot]:
        return list(self._history)
    
    def get_stats(self) -> dict:
        return {
            'task_trust': self._task_trust,
            'consecutive_failures': self._consecutive_failures,
            'session_active': self._session_active,
            'history_length': len(self._history),
            'auth_quality': self._auth_quality,
        }
    
    def _record(
        self,
        event_type: str,
        penalty: float = 0.0,
        recovery: float = 0.0,
        details: dict = None,
    ):
        self._history.append(TrustSnapshot(
            task_trust=self._task_trust,
            object_index=self._current_object_index,
            event_type=event_type,
            penalty_applied=penalty,
            recovery_applied=recovery,
            timestamp_ms=time.time() * 1000,
            details=details or {},
        ))



