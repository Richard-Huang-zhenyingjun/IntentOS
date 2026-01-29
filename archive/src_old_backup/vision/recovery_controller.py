"""
Recovery Controller - Week 8 Enhanced Failure Recovery

Central safety brain for the system.
Orchestrates comprehensive failure detection, structured recovery plans,
and transparent recovery tracking.

Week 7: Basic failure detection (object loss, hand loss, ambiguity)
Week 8: Centralized, comprehensive, with recovery state tracking
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple
from intent_core.schema import SystemState
from vision.object_loss_detector import ObjectLossDetector
from vision.hand_loss_detector import HandLossDetector
from vision.ambiguity_during_confirm_detector import AmbiguityDuringConfirmDetector
from vision.object_tracker import ObjectTracker

# Import types if available
try:
    from src.vision.hand_detector import HandDetectionResult
except ImportError:
    HandDetectionResult = None

try:
    from src.vision.candidate_ranker import RankedCandidates
except ImportError:
    RankedCandidates = None


class PauseTrigger(str, Enum):
    """
    Reasons for triggering pause (ENHANCED Week 8)
    
    Week 7 triggers: Basic failure detection
    Week 8 triggers: Comprehensive safety monitoring
    """
    # Week 7 triggers
    OBJECT_LOSS = "object_loss"
    HAND_LOSS = "hand_loss"
    AMBIGUITY_DURING_CONFIRM = "ambiguity_during_confirm"
    OSCILLATION = "oscillation"
    
    # NEW Week 8 triggers
    CONFIDENCE_DROP = "confidence_drop"  # Sudden confidence collapse
    ATTENTION_TIMEOUT = "attention_timeout"  # User stopped paying attention
    STATE_UNCERTAINTY = "state_uncertainty"  # State inference became uncertain
    SCOPE_DRIFT = "scope_drift"  # Object moved significantly
    
    # Manual
    MANUAL = "manual"  # User-initiated pause


class RecoveryAction(str, Enum):
    """
    Required recovery actions (NEW Week 8)
    
    Structured steps user must complete to recover from pause.
    """
    RESCOPE_OBJECT = "rescope_object"
    RECONFIRM_ACTION = "reconfirm_action"
    WAIT_FOR_CLARITY = "wait_for_clarity"
    WAIT_FOR_HAND = "wait_for_hand"
    WAIT_FOR_STABILITY = "wait_for_stability"


@dataclass(frozen=True)
class RecoveryPlan:
    """
    Structured recovery plan (ENHANCED Week 8)
    
    Specifies:
    - Why paused
    - What was cleared
    - What user must do (step-by-step)
    - When system can resume
    
    Week 7: Basic pause with reason
    Week 8: Comprehensive recovery roadmap
    """
    # Pause decision
    should_pause: bool
    trigger: Optional[PauseTrigger]
    reason: str  # Human-readable explanation
    
    # State clearing
    clear_scope: bool
    clear_confirmation: bool
    clear_execution: bool
    clear_undo: bool  # NEW: Clear undo availability
    
    # Recovery requirements (NEW Week 8)
    recovery_actions: List[RecoveryAction] = field(default_factory=list)
    recovery_explanation: str = ""  # Step-by-step instructions
    
    # Evidence (for logging/debugging)
    evidence: Dict[str, Any] = field(default_factory=dict)
    
    # Metadata
    timestamp: float = 0.0
    system_state_at_pause: str = ""
    
    @classmethod
    def create_no_pause(cls, timestamp: float) -> 'RecoveryPlan':
        """Factory for no-pause plan"""
        return cls(
            should_pause=False,
            trigger=None,
            reason="",
            clear_scope=False,
            clear_confirmation=False,
            clear_execution=False,
            clear_undo=False,
            recovery_actions=[],
            recovery_explanation="",
            evidence={},
            timestamp=timestamp,
            system_state_at_pause=""
        )


class RecoveryController:
    """
    Central recovery coordination (ENHANCED Week 8)
    
    Responsibilities:
    - Monitor all failure conditions (comprehensive)
    - Decide when to pause (priority-based)
    - Generate structured recovery plans
    - Track recovery progress (NEW Week 8)
    - Validate recovery completion (NEW Week 8)
    
    Design Philosophy:
    - Defensive: Prefer safe stop over partial execution
    - Transparent: Always explain why paused
    - Structured: Provide clear recovery steps
    - Trackable: Log everything for replay
    
    Week 7: Basic failure detection
    Week 8: Centralized safety brain with recovery tracking
    """
    
    def __init__(self, config: dict):
        self.config = config
        
        # Config
        recovery_config = config.get('recovery', {})
        self.require_rescope = recovery_config.get('require_rescope_after_pause', True)
        self.require_reconfirm = recovery_config.get('require_reconfirm_after_pause', True)
        self.clear_undo_on_pause = recovery_config.get('clear_undo_on_pause', True)
        
        # NEW Week 8: Additional safety checks
        self.confidence_drop_threshold = recovery_config.get('confidence_drop_threshold', 0.3)
        self.attention_timeout_seconds = recovery_config.get('attention_timeout_seconds', 10.0)
        self.state_uncertainty_threshold = recovery_config.get('state_uncertainty_threshold', 0.4)
        
        # Failure detectors (Week 7 - initialized in __init__ or injected)
        self.object_loss_detector = ObjectLossDetector(config.get('object_loss', {}))
        self.hand_loss_detector = HandLossDetector(config.get('hand_loss', {}))
        self.ambiguity_detector = AmbiguityDuringConfirmDetector(config.get('ambiguity_during_confirm', {}))
        
        # State
        self.currently_paused = False
        self.pause_reason: Optional[str] = None
        self.pause_trigger: Optional[PauseTrigger] = None
        self.pause_timestamp: Optional[float] = None
        
        # Recovery tracking (NEW Week 8)
        self.recovery_in_progress = False
        self.recovery_steps_completed: List[str] = []
        self.required_recovery_actions: List[RecoveryAction] = []
        
        # Statistics
        self.total_checks = 0
        self.pause_events = 0
        self.recovery_events = 0
        self.pause_triggers_count: Dict[str, int] = {}
    
    def check_and_plan(self,
                       scoped_object_id: Optional[str],
                       ranked_candidates: Optional['RankedCandidates'],
                       hand_detection: Optional['HandDetectionResult'],
                       tracker: Optional[ObjectTracker],
                       system_state: SystemState,
                       timestamp: float,
                       state_estimate: Optional[Any] = None,
                       confidence_history: Optional[Dict] = None) -> RecoveryPlan:
        """
        Comprehensive safety check (ENHANCED Week 8)
        
        Checks all failure conditions in priority order:
        1. Object loss (Week 7)
        2. Hand loss (Week 7)
        3. Ambiguity during confirm (Week 7)
        4. Confidence drop (NEW Week 8)
        5. State uncertainty (NEW Week 8)
        
        Args:
            scoped_object_id: Currently scoped object
            ranked_candidates: Current ranking result
            hand_detection: Current hand detection
            tracker: Object tracker
            system_state: Current system state
            timestamp: Current timestamp
            state_estimate: State inference result (NEW Week 8)
            confidence_history: Confidence tracking (NEW Week 8)
        
        Returns:
            RecoveryPlan with pause decision and recovery steps
        """
        self.total_checks += 1
        
        # Only check during vulnerable states
        vulnerable_states = [
            SystemState.CONFIRMING,
            SystemState.EXECUTING,
            SystemState.UNDO_CONFIRMING
        ]
        
        if system_state not in vulnerable_states:
            return RecoveryPlan.create_no_pause(timestamp)
        
        # === RUN ALL CHECKS (Priority Order) ===
        
        failures: List[Tuple[PauseTrigger, str, Dict[str, Any]]] = []
        
        # 1. Object loss (Week 7 - highest priority)
        if self.object_loss_detector and tracker:
            should_pause, reason = self.object_loss_detector.check(
                scoped_object_id=scoped_object_id,
                tracker=tracker,
                system_state=system_state,
                timestamp=timestamp
            )
            if should_pause:
                failures.append((PauseTrigger.OBJECT_LOSS, reason, {
                    'scoped_object_id': scoped_object_id,
                    'frames_missing': self.object_loss_detector.frames_missing
                }))
        
        # 2. Hand loss (Week 7)
        if self.hand_loss_detector and hand_detection:
            should_pause, reason = self.hand_loss_detector.check(
                hand_detection=hand_detection,
                system_state=system_state,
                timestamp=timestamp
            )
            if should_pause:
                failures.append((PauseTrigger.HAND_LOSS, reason, {
                    'frames_without_hand': self.hand_loss_detector.frames_without_hand
                }))
        
        # 3. Ambiguity during confirm (Week 7)
        if self.ambiguity_detector and ranked_candidates:
            should_pause, reason = self.ambiguity_detector.check(
                ranked_candidates=ranked_candidates,
                system_state=system_state,
                timestamp=timestamp
            )
            if should_pause:
                failures.append((PauseTrigger.AMBIGUITY_DURING_CONFIRM, reason, {
                    'num_candidates': ranked_candidates.num_candidates,
                    'margin': ranked_candidates.margin
                }))
        
        # 4. Confidence drop (NEW Week 8)
        if confidence_history and scoped_object_id:
            confidence_drop = self._check_confidence_drop(
                confidence_history, scoped_object_id
            )
            if confidence_drop:
                failures.append((PauseTrigger.CONFIDENCE_DROP, 
                               f"Detection confidence dropped by {confidence_drop:.2f}",
                               {'confidence_drop': confidence_drop}))
        
        # 5. State uncertainty (NEW Week 8)
        if state_estimate and hasattr(state_estimate, 'uncertain'):
            if state_estimate.uncertain:
                failures.append((PauseTrigger.STATE_UNCERTAINTY,
                               f"Object state became uncertain: {state_estimate.reason}",
                               {'state_confidence': getattr(state_estimate, 'confidence', 0.0)}))
        
        # === GENERATE RECOVERY PLAN ===
        
        if len(failures) > 0:
            # Take first failure (priority order)
            trigger, reason, evidence = failures[0]
            
            # Log all failures if multiple
            if len(failures) > 1:
                evidence['additional_failures'] = [
                    {'trigger': t.value, 'reason': r} for t, r, _ in failures[1:]
                ]
            
            return self._create_pause_plan(
                trigger=trigger,
                reason=reason,
                evidence=evidence,
                timestamp=timestamp,
                system_state=system_state
            )
        
        # No failures - continue
        return RecoveryPlan.create_no_pause(timestamp)
    
    def check(self, **kwargs) -> RecoveryPlan:
        """
        Alias for check_and_plan() for backward compatibility with tests.
        
        Accepts the same arguments as check_and_plan().
        """
        return self.check_and_plan(**kwargs)
    
    def _check_confidence_drop(self, confidence_history: Dict, object_id: str) -> Optional[float]:
        """
        Check if confidence dropped suddenly (NEW Week 8)
        
        Args:
            confidence_history: Dict mapping object_id to list of confidence values
            object_id: Object to check
        
        Returns:
            Confidence drop amount if significant, None otherwise
        """
        if object_id not in confidence_history:
            return None
        
        history = confidence_history[object_id]
        if len(history) < 2:
            return None
        
        # Get recent readings (last 5)
        recent = history[-5:] if len(history) >= 5 else history
        
        if len(recent) < 2:
            return None
        
        # Check for sudden drop
        prev_avg = sum(recent[:-1]) / len(recent[:-1])
        current = recent[-1]
        drop = prev_avg - current
        
        if drop > self.confidence_drop_threshold:
            return drop
        
        return None
    
    def _create_pause_plan(self,
                          trigger: PauseTrigger,
                          reason: str,
                          evidence: Dict[str, Any],
                          timestamp: float,
                          system_state: SystemState) -> RecoveryPlan:
        """
        Create comprehensive pause plan with recovery steps (ENHANCED Week 8)
        
        Generates structured recovery roadmap based on failure type.
        """
        
        self.pause_events += 1
        self.pause_triggers_count[trigger.value] = \
            self.pause_triggers_count.get(trigger.value, 0) + 1
        
        self.currently_paused = True
        self.pause_reason = reason
        self.pause_trigger = trigger
        self.pause_timestamp = timestamp
        
        # Determine recovery actions based on trigger (NEW Week 8)
        recovery_actions: List[RecoveryAction] = []
        recovery_explanation = ""
        
        if trigger == PauseTrigger.OBJECT_LOSS:
            recovery_actions = [
                RecoveryAction.RESCOPE_OBJECT,
                RecoveryAction.RECONFIRM_ACTION
            ]
            recovery_explanation = (
                "1. Bring object back into view\n"
                "2. Wait for stable scope (green box)\n"
                "3. Confirm action again with pinch gesture"
            )
        
        elif trigger == PauseTrigger.HAND_LOSS:
            recovery_actions = [
                RecoveryAction.WAIT_FOR_HAND,
                RecoveryAction.RECONFIRM_ACTION
            ]
            recovery_explanation = (
                "1. Ensure hand is visible to camera\n"
                "2. System will detect hand automatically\n"
                "3. Confirm action again with pinch gesture"
            )
        
        elif trigger == PauseTrigger.AMBIGUITY_DURING_CONFIRM:
            recovery_actions = [
                RecoveryAction.WAIT_FOR_CLARITY,
                RecoveryAction.RECONFIRM_ACTION
            ]
            recovery_explanation = (
                "1. Move competing objects apart\n"
                "2. Wait for clear focus (single green box)\n"
                "3. Confirm action again with pinch gesture"
            )
        
        elif trigger == PauseTrigger.CONFIDENCE_DROP:
            recovery_actions = [
                RecoveryAction.WAIT_FOR_STABILITY,
                RecoveryAction.RESCOPE_OBJECT,
                RecoveryAction.RECONFIRM_ACTION
            ]
            recovery_explanation = (
                "1. Improve object visibility (better lighting/angle)\n"
                "2. Wait for stable detection\n"
                "3. Confirm action again with pinch gesture"
            )
        
        elif trigger == PauseTrigger.STATE_UNCERTAINTY:
            recovery_actions = [
                RecoveryAction.WAIT_FOR_CLARITY,
                RecoveryAction.RECONFIRM_ACTION
            ]
            recovery_explanation = (
                "1. Wait for clear object state\n"
                "2. Confirm action again with pinch gesture"
            )
        
        else:
            # Generic recovery
            recovery_actions = [
                RecoveryAction.RESCOPE_OBJECT,
                RecoveryAction.RECONFIRM_ACTION
            ]
            recovery_explanation = (
                "1. Re-establish focus on object\n"
                "2. Confirm action again with pinch gesture"
            )
        
        # Store required actions for validation
        self.required_recovery_actions = recovery_actions
        
        return RecoveryPlan(
            should_pause=True,
            trigger=trigger,
            reason=reason,
            clear_scope=self.require_rescope,
            clear_confirmation=True,  # Always clear confirmation
            clear_execution=True,  # Always clear execution
            clear_undo=self.clear_undo_on_pause,
            recovery_actions=recovery_actions,
            recovery_explanation=recovery_explanation,
            evidence=evidence,
            timestamp=timestamp,
            system_state_at_pause=system_state.value
        )
    
    def start_recovery(self) -> bool:
        """
        Start recovery process (NEW Week 8)
        
        Transitions from PAUSED to RECOVERING state.
        
        Returns:
            True if recovery can start, False if not paused
        """
        if not self.currently_paused:
            return False
        
        self.recovery_in_progress = True
        self.recovery_steps_completed = []
        self.recovery_events += 1
        
        return True
    
    def complete_recovery_step(self, step: RecoveryAction):
        """
        Mark recovery step as completed (NEW Week 8)
        
        Args:
            step: Recovery action that was completed
        """
        if step.value not in self.recovery_steps_completed:
            self.recovery_steps_completed.append(step.value)
    
    def validate_recovery(self, required_actions: Optional[List[RecoveryAction]] = None) -> Tuple[bool, str]:
        """
        Validate if recovery is complete (NEW Week 8)
        
        Args:
            required_actions: Actions to validate (defaults to current required actions)
        
        Returns:
            (is_complete, reason) tuple
        """
        if required_actions is None:
            required_actions = self.required_recovery_actions
        
        for action in required_actions:
            if action.value not in self.recovery_steps_completed:
                return (False, f"Incomplete: {action.value} not done")
        
        return (True, "Recovery complete - all steps validated")
    
    def clear_pause(self):
        """
        Clear pause state after successful recovery
        
        Resets all pause-related state and detectors.
        """
        self.currently_paused = False
        self.pause_reason = None
        self.pause_trigger = None
        self.pause_timestamp = None
        self.recovery_in_progress = False
        self.recovery_steps_completed = []
        self.required_recovery_actions = []
        
        # Reset detectors
        if self.object_loss_detector:
            self.object_loss_detector.reset()
        if self.hand_loss_detector:
            self.hand_loss_detector.reset()
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get recovery statistics
        
        Returns:
            Dictionary with comprehensive recovery metrics
        """
        return {
            'total_checks': self.total_checks,
            'pause_events': self.pause_events,
            'recovery_events': self.recovery_events,
            'pause_rate': self.pause_events / max(1, self.total_checks),
            'recovery_rate': self.recovery_events / max(1, self.pause_events),
            'pause_triggers': self.pause_triggers_count,
            'currently_paused': self.currently_paused,
            'recovery_in_progress': self.recovery_in_progress
        }
