"""
Arm trust metrics - track safety guarantees.
Week 8: Paper's "shared control requires trust" - quantify it.
"""

from dataclasses import dataclass, field
from typing import Dict
import time


@dataclass
class ArmTrustMetrics:
    """
    Trust and safety metrics.
    
    Critical invariant: false_executions MUST always be 0.
    
    Attributes:
        false_executions: Executions started without confirmation (MUST BE 0)
        executions_started: Total executions started
        executions_completed: Total executions completed successfully
        executions_failed: Total executions failed
        executions_cancelled: Total executions cancelled
        executions_blocked_unstable: Confirmations blocked due to instability
        pauses_triggered: Total pauses triggered
        pauses_by_trigger: Breakdown of pauses by trigger type
        undos_performed: Total undo operations
        target_loss_events: Target loss events
        eeg_dropout_events: EEG dropout events
        session_start_time: Session start timestamp
    """
    # CRITICAL: false_executions must always be 0
    false_executions: int = 0
    
    # Execution counts
    executions_started: int = 0
    executions_completed: int = 0
    executions_failed: int = 0
    executions_cancelled: int = 0
    
    # Safety blocks
    executions_blocked_unstable: int = 0
    
    # Recovery events
    pauses_triggered: int = 0
    pauses_by_trigger: Dict[str, int] = field(default_factory=dict)
    undos_performed: int = 0
    
    # Specific failure modes
    target_loss_events: int = 0
    eeg_dropout_events: int = 0
    
    # Session info
    session_start_time: float = field(default_factory=time.time)
    
    def record_execution_start(self, confirmed: bool) -> None:
        """
        Record execution start.
        
        Args:
            confirmed: Whether user confirmed the action
        """
        if confirmed:
            self.executions_started += 1
        else:
            # CRITICAL VIOLATION
            self.false_executions += 1
            print("🚨 CRITICAL: Execution started without confirmation!")
    
    def record_execution_complete(self, success: bool) -> None:
        """Record execution completion."""
        if success:
            self.executions_completed += 1
        else:
            self.executions_failed += 1
    
    def record_execution_cancelled(self) -> None:
        """Record execution cancellation."""
        self.executions_cancelled += 1
    
    def record_blocked_unstable(self) -> None:
        """Record confirmation blocked due to instability."""
        self.executions_blocked_unstable += 1
    
    def record_pause(self, trigger: str) -> None:
        """
        Record pause event.
        
        Args:
            trigger: Pause trigger name
        """
        self.pauses_triggered += 1
        self.pauses_by_trigger[trigger] = self.pauses_by_trigger.get(trigger, 0) + 1
        
        # Track specific events
        if "target_lost" in trigger.lower():
            self.target_loss_events += 1
        if "eeg" in trigger.lower() and "drop" in trigger.lower():
            self.eeg_dropout_events += 1
    
    def record_undo(self) -> None:
        """Record undo operation."""
        self.undos_performed += 1
    
    def get_session_duration(self) -> float:
        """Get session duration in seconds."""
        return time.time() - self.session_start_time
    
    def get_summary(self) -> dict:
        """
        Get metrics summary.
        
        Returns:
            Dict with all metrics
        """
        return {
            "false_executions": self.false_executions,
            "executions_started": self.executions_started,
            "executions_completed": self.executions_completed,
            "executions_failed": self.executions_failed,
            "executions_cancelled": self.executions_cancelled,
            "success_rate": (self.executions_completed / self.executions_started * 100) 
                           if self.executions_started > 0 else 0.0,
            "blocked_unstable": self.executions_blocked_unstable,
            "pauses_triggered": self.pauses_triggered,
            "pauses_by_trigger": self.pauses_by_trigger,
            "undos_performed": self.undos_performed,
            "target_loss_events": self.target_loss_events,
            "eeg_dropout_events": self.eeg_dropout_events,
            "session_duration": self.get_session_duration(),
        }
    
    def print_summary(self) -> None:
        """Print metrics summary to console."""
        print("\n" + "="*70)
        print("TRUST & SAFETY METRICS")
        print("="*70)
        
        # Critical metric
        status = "✓ PASS" if self.false_executions == 0 else "🚨 FAIL"
        print(f"False Executions (MUST BE 0): {self.false_executions} {status}")
        
        print(f"\nExecution Stats:")
        print(f"  Started:    {self.executions_started}")
        print(f"  Completed:  {self.executions_completed}")
        print(f"  Failed:     {self.executions_failed}")
        print(f"  Cancelled:  {self.executions_cancelled}")
        
        if self.executions_started > 0:
            success_rate = self.executions_completed / self.executions_started * 100
            print(f"  Success Rate: {success_rate:.1f}%")
        
        print(f"\nSafety Events:")
        print(f"  Blocked (unstable): {self.executions_blocked_unstable}")
        print(f"  Pauses triggered:   {self.pauses_triggered}")
        print(f"  Undos performed:    {self.undos_performed}")
        
        if self.pauses_by_trigger:
            print(f"\nPause Breakdown:")
            for trigger, count in self.pauses_by_trigger.items():
                print(f"  {trigger}: {count}")
        
        print(f"\nSession Duration: {self.get_session_duration():.1f}s")
        print("="*70 + "\n")




