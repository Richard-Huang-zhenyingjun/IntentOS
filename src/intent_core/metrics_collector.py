"""
Metrics Collector - Quantitative Safety Proof (Week 9)

Collects comprehensive metrics to prove safety guarantees quantitatively.
Essential for demo, evaluation, and trust reporting.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
import time


@dataclass
class SessionMetrics:
    """Complete session metrics"""
    # Session info
    session_id: str
    start_time: float
    duration_seconds: float
    total_frames: int
    
    # Safety metrics (CRITICAL)
    false_executions: int  # MUST BE ZERO
    unauthorized_executions: int  # MUST BE ZERO
    
    # Intent flow
    scope_acquisitions: int
    scope_losses: int
    scope_changes: int
    
    # Affordances
    affordances_generated: int
    affordances_blocked: int
    state_aware_affordances: int
    fallback_affordances: int
    
    # Confirmation
    confirmation_attempts: int
    confirmation_successes: int
    confirmation_cancellations: int
    
    # Execution
    execution_requests: int
    execution_successes: int
    execution_refusals: int
    refusal_reasons: Dict[str, int]
    
    # Undo
    undo_requests: int
    undo_successes: int
    undo_refusals: int
    undo_expirations: int
    
    # Robustness
    ambiguity_waits: int
    oscillation_events: int
    pause_triggers: int
    pause_trigger_types: Dict[str, int]
    recovery_completions: int
    
    # Multi-object
    max_tracked_objects: int
    avg_tracked_objects: float
    
    # Performance
    avg_frame_time_ms: float
    max_frame_time_ms: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'session_id': self.session_id,
            'start_time': self.start_time,
            'duration_seconds': self.duration_seconds,
            'total_frames': self.total_frames,
            'false_executions': self.false_executions,
            'unauthorized_executions': self.unauthorized_executions,
            'scope_acquisitions': self.scope_acquisitions,
            'scope_losses': self.scope_losses,
            'scope_changes': self.scope_changes,
            'affordances_generated': self.affordances_generated,
            'affordances_blocked': self.affordances_blocked,
            'state_aware_affordances': self.state_aware_affordances,
            'fallback_affordances': self.fallback_affordances,
            'confirmation_attempts': self.confirmation_attempts,
            'confirmation_successes': self.confirmation_successes,
            'confirmation_cancellations': self.confirmation_cancellations,
            'execution_requests': self.execution_requests,
            'execution_successes': self.execution_successes,
            'execution_refusals': self.execution_refusals,
            'refusal_reasons': self.refusal_reasons,
            'undo_requests': self.undo_requests,
            'undo_successes': self.undo_successes,
            'undo_refusals': self.undo_refusals,
            'undo_expirations': self.undo_expirations,
            'ambiguity_waits': self.ambiguity_waits,
            'oscillation_events': self.oscillation_events,
            'pause_triggers': self.pause_triggers,
            'pause_trigger_types': self.pause_trigger_types,
            'recovery_completions': self.recovery_completions,
            'max_tracked_objects': self.max_tracked_objects,
            'avg_tracked_objects': self.avg_tracked_objects,
            'avg_frame_time_ms': self.avg_frame_time_ms,
            'max_frame_time_ms': self.max_frame_time_ms
        }


class MetricsCollector:
    """
    Collect comprehensive system metrics (Week 9)
    
    Purpose:
    - Track all system events
    - Prove safety guarantees
    - Measure performance
    - Generate trust reports
    
    Design:
    - Frame-by-frame tracking
    - Event-based recording
    - Aggregate statistics
    - Safety-critical counters
    """
    
    def __init__(self):
        """Initialize metrics collector"""
        # Session tracking
        self.session_id = f"session_{int(time.time())}"
        self.session_start = time.time()
        self.frame_count = 0
        
        # === CRITICAL SAFETY COUNTERS ===
        self.false_executions = 0  # MUST REMAIN ZERO
        self.unauthorized_executions = 0  # MUST REMAIN ZERO
        
        # Intent flow
        self.scope_acquisitions = 0
        self.scope_losses = 0
        self.scope_changes = 0
        self.last_scoped_id: Optional[str] = None
        
        # Affordances
        self.affordances_generated = 0
        self.affordances_blocked = 0
        self.state_aware_affordances = 0
        self.fallback_affordances = 0
        
        # Confirmation
        self.confirmation_attempts = 0
        self.confirmation_successes = 0
        self.confirmation_cancellations = 0
        
        # Execution
        self.execution_requests = 0
        self.execution_successes = 0
        self.execution_refusals = 0
        self.refusal_reasons: Dict[str, int] = {}
        
        # Undo
        self.undo_requests = 0
        self.undo_successes = 0
        self.undo_refusals = 0
        self.undo_expirations = 0
        
        # Robustness
        self.ambiguity_waits = 0
        self.oscillation_events = 0
        self.pause_triggers = 0
        self.pause_trigger_types: Dict[str, int] = {}
        self.recovery_completions = 0
        
        # Multi-object
        self.max_tracked_objects = 0
        self.total_tracked_objects = 0
        self.tracked_object_samples = 0
        
        # Performance
        self.frame_times: List[float] = []
        self.last_frame_time = time.time()
    
    # === Frame-level tracking ===
    
    def record_frame(self, snapshot):
        """
        Record frame-level metrics
        
        Args:
            snapshot: UISnapshot for current frame
        """
        self.frame_count += 1
        
        # Frame time
        current_time = time.time()
        frame_time = (current_time - self.last_frame_time) * 1000  # ms
        self.frame_times.append(frame_time)
        self.last_frame_time = current_time
        
        # Scope tracking
        current_scope_id = snapshot.scoped_object_id
        if current_scope_id != self.last_scoped_id:
            if current_scope_id is not None and self.last_scoped_id is None:
                self.scope_acquisitions += 1
            elif current_scope_id is None and self.last_scoped_id is not None:
                self.scope_losses += 1
            elif current_scope_id is not None and self.last_scoped_id is not None:
                self.scope_changes += 1
            
            self.last_scoped_id = current_scope_id
        
        # Multi-object tracking
        num_tracked = snapshot.num_tracked_objects
        self.max_tracked_objects = max(self.max_tracked_objects, num_tracked)
        self.total_tracked_objects += num_tracked
        self.tracked_object_samples += 1
        
        # Ambiguity
        if snapshot.ambiguity_detected:
            self.ambiguity_waits += 1
        
        # Oscillation
        if snapshot.oscillation_detected:
            self.oscillation_events += 1
        
        # Pause
        if snapshot.paused:
            self.pause_triggers += 1
            trigger = snapshot.pause_trigger
            if trigger:
                self.pause_trigger_types[trigger] = \
                    self.pause_trigger_types.get(trigger, 0) + 1
    
    # === Affordance tracking ===
    
    def record_affordance_generation(self, state_aware: bool, blocked: bool):
        """
        Record affordance generation
        
        Args:
            state_aware: Was state inference used?
            blocked: Were affordances blocked?
        """
        if blocked:
            self.affordances_blocked += 1
        else:
            self.affordances_generated += 1
            if state_aware:
                self.state_aware_affordances += 1
            else:
                self.fallback_affordances += 1
    
    # === Confirmation tracking ===
    
    def record_confirmation_attempt(self):
        """Record confirmation attempt"""
        self.confirmation_attempts += 1
    
    def record_confirmation_success(self):
        """Record successful confirmation"""
        self.confirmation_successes += 1
    
    def record_confirmation_cancellation(self):
        """Record confirmation cancellation"""
        self.confirmation_cancellations += 1
    
    # === Execution tracking ===
    
    def record_execution_request(self):
        """Record execution request"""
        self.execution_requests += 1
    
    def record_execution_success(self):
        """Record successful execution"""
        self.execution_successes += 1
    
    def record_execution_refusal(self, reason: str):
        """
        Record execution refusal
        
        Args:
            reason: Why execution was refused
        """
        self.execution_refusals += 1
        self.refusal_reasons[reason] = self.refusal_reasons.get(reason, 0) + 1
    
    def record_false_execution(self):
        """
        Record false execution (CRITICAL)
        
        This should NEVER be called.
        If called, it indicates a safety violation.
        """
        self.false_executions += 1
        print("⚠️ CRITICAL: FALSE EXECUTION DETECTED ⚠️")
        print("  A safety invariant has been violated!")
        print("  System executed without proper authorization.")
    
    def record_unauthorized_execution(self):
        """
        Record unauthorized execution (CRITICAL)
        
        This should NEVER be called.
        If called, it indicates a security violation.
        """
        self.unauthorized_executions += 1
        print("⚠️ CRITICAL: UNAUTHORIZED EXECUTION DETECTED ⚠️")
        print("  A security invariant has been violated!")
        print("  System executed action without user confirmation.")
    
    # === Undo tracking ===
    
    def record_undo_request(self):
        """Record undo request"""
        self.undo_requests += 1
    
    def record_undo_success(self):
        """Record successful undo"""
        self.undo_successes += 1
    
    def record_undo_refusal(self):
        """Record undo refusal"""
        self.undo_refusals += 1
    
    def record_undo_expiration(self):
        """Record undo expiration"""
        self.undo_expirations += 1
    
    # === Recovery tracking ===
    
    def record_recovery_completion(self):
        """Record successful recovery"""
        self.recovery_completions += 1
    
    # === Aggregate metrics ===
    
    def get_session_metrics(self) -> SessionMetrics:
        """
        Get complete session metrics
        
        Returns:
            SessionMetrics with all collected data
        """
        current_time = time.time()
        duration = current_time - self.session_start
        
        # Calculate averages
        avg_tracked = (self.total_tracked_objects / max(1, self.tracked_object_samples))
        avg_frame_time = sum(self.frame_times) / max(1, len(self.frame_times))
        max_frame_time = max(self.frame_times) if self.frame_times else 0.0
        
        return SessionMetrics(
            session_id=self.session_id,
            start_time=self.session_start,
            duration_seconds=duration,
            total_frames=self.frame_count,
            
            # Safety (CRITICAL)
            false_executions=self.false_executions,
            unauthorized_executions=self.unauthorized_executions,
            
            # Intent flow
            scope_acquisitions=self.scope_acquisitions,
            scope_losses=self.scope_losses,
            scope_changes=self.scope_changes,
            
            # Affordances
            affordances_generated=self.affordances_generated,
            affordances_blocked=self.affordances_blocked,
            state_aware_affordances=self.state_aware_affordances,
            fallback_affordances=self.fallback_affordances,
            
            # Confirmation
            confirmation_attempts=self.confirmation_attempts,
            confirmation_successes=self.confirmation_successes,
            confirmation_cancellations=self.confirmation_cancellations,
            
            # Execution
            execution_requests=self.execution_requests,
            execution_successes=self.execution_successes,
            execution_refusals=self.execution_refusals,
            refusal_reasons=self.refusal_reasons.copy(),
            
            # Undo
            undo_requests=self.undo_requests,
            undo_successes=self.undo_successes,
            undo_refusals=self.undo_refusals,
            undo_expirations=self.undo_expirations,
            
            # Robustness
            ambiguity_waits=self.ambiguity_waits,
            oscillation_events=self.oscillation_events,
            pause_triggers=self.pause_triggers,
            pause_trigger_types=self.pause_trigger_types.copy(),
            recovery_completions=self.recovery_completions,
            
            # Multi-object
            max_tracked_objects=self.max_tracked_objects,
            avg_tracked_objects=avg_tracked,
            
            # Performance
            avg_frame_time_ms=avg_frame_time,
            max_frame_time_ms=max_frame_time
        )
    
    def get_safety_metrics(self) -> Dict[str, Any]:
        """
        Get safety-critical metrics
        
        Returns:
            Dict with safety metrics and interpretation
        """
        safety_guarantee_met = (
            self.false_executions == 0 and
            self.unauthorized_executions == 0
        )
        
        if safety_guarantee_met:
            interpretation = "✓ Safety guaranteed: 0 false executions, 0 unauthorized executions"
        else:
            interpretation = (
                f"✗ Safety VIOLATION: "
                f"{self.false_executions} false executions, "
                f"{self.unauthorized_executions} unauthorized executions"
            )
        
        return {
            'false_executions': self.false_executions,
            'unauthorized_executions': self.unauthorized_executions,
            'safety_guarantee_met': safety_guarantee_met,
            'interpretation': interpretation,
            'total_actions_executed': self.execution_successes,
            'total_actions_refused': self.execution_refusals,
            'refusal_rate': self.execution_refusals / max(1, self.execution_requests),
            'total_pause_events': self.pause_triggers,
            'total_recovery_completions': self.recovery_completions
        }
    
    def get_trust_report(self) -> str:
        """
        Generate human-readable trust report
        
        Returns:
            Formatted trust report string
        """
        session_metrics = self.get_session_metrics()
        safety_metrics = self.get_safety_metrics()
        
        report = []
        report.append("=" * 60)
        report.append("TRUST REPORT")
        report.append("=" * 60)
        report.append("")
        
        # Session info
        report.append(f"Session: {session_metrics.session_id}")
        report.append(f"Duration: {session_metrics.duration_seconds:.1f}s")
        report.append(f"Frames: {session_metrics.total_frames}")
        report.append("")
        
        # Safety guarantees (MOST IMPORTANT)
        report.append("SAFETY GUARANTEES:")
        report.append(f"  {safety_metrics['interpretation']}")
        report.append(f"  False Executions: {session_metrics.false_executions}")
        report.append(f"  Unauthorized Executions: {session_metrics.unauthorized_executions}")
        report.append("")
        
        # Execution summary
        report.append("EXECUTION SUMMARY:")
        report.append(f"  Requests: {session_metrics.execution_requests}")
        report.append(f"  Successes: {session_metrics.execution_successes}")
        report.append(f"  Refusals: {session_metrics.execution_refusals}")
        if session_metrics.refusal_reasons:
            report.append("  Refusal Reasons:")
            for reason, count in session_metrics.refusal_reasons.items():
                report.append(f"    - {reason}: {count}")
        report.append("")
        
        # Robustness
        report.append("ROBUSTNESS:")
        report.append(f"  Ambiguity Events: {session_metrics.ambiguity_waits}")
        report.append(f"  Oscillation Events: {session_metrics.oscillation_events}")
        report.append(f"  Pause Events: {session_metrics.pause_triggers}")
        if session_metrics.pause_trigger_types:
            report.append("  Pause Triggers:")
            for trigger, count in session_metrics.pause_trigger_types.items():
                report.append(f"    - {trigger}: {count}")
        report.append(f"  Recoveries: {session_metrics.recovery_completions}")
        report.append("")
        
        # Undo usage
        report.append("UNDO USAGE:")
        report.append(f"  Requests: {session_metrics.undo_requests}")
        report.append(f"  Successes: {session_metrics.undo_successes}")
        report.append(f"  Refusals: {session_metrics.undo_refusals}")
        report.append(f"  Expirations: {session_metrics.undo_expirations}")
        report.append("")
        
        # Performance
        report.append("PERFORMANCE:")
        report.append(f"  Avg Frame Time: {session_metrics.avg_frame_time_ms:.2f}ms")
        report.append(f"  Max Frame Time: {session_metrics.max_frame_time_ms:.2f}ms")
        report.append("")
        
        report.append("=" * 60)
        
        return "\n".join(report)
    
    def print_trust_report(self):
        """Print trust report to console"""
        print(self.get_trust_report())
