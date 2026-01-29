"""
Trust metrics tracker - safety guarantees and transparency.
Week 8: Track false executions, pause events, recovery success.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import time
import json

from .pause_triggers import PauseTrigger


@dataclass
class PauseEvent:
    """Record of a pause event."""
    timestamp: float
    trigger: PauseTrigger
    explanation: str
    frame: int
    recovered: bool = False
    recovery_time: Optional[float] = None


@dataclass
class ExecutionEvent:
    """Record of an execution event."""
    timestamp: float
    action: str
    confirmed: bool
    frame: int
    success: bool = False
    result: Optional[str] = None


@dataclass
class TrustReport:
    """
    Trust metrics report.
    
    Week 8 safety guarantees:
    - false_executions = 0 (never execute without confirmation)
    - pause_on_failure = True (always pause on detected failure)
    - transparent_refusals = True (always explain why paused)
    """
    # Safety metrics
    false_executions: int = 0           # Actions executed without confirmation
    confirmed_executions: int = 0       # Actions executed with confirmation
    pauses_triggered: int = 0           # Total pause events
    pauses_recovered: int = 0           # Pauses successfully recovered from
    
    # Pause breakdown
    pause_by_trigger: Dict[str, int] = field(default_factory=dict)
    
    # Timing
    total_runtime_seconds: float = 0.0
    total_paused_seconds: float = 0.0
    mean_recovery_time_seconds: float = 0.0
    
    # Transparency
    all_refusals_explained: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "safety_metrics": {
                "false_executions": self.false_executions,
                "confirmed_executions": self.confirmed_executions,
                "safety_guarantee": "PASS" if self.false_executions == 0 else "FAIL",
            },
            "pause_metrics": {
                "pauses_triggered": self.pauses_triggered,
                "pauses_recovered": self.pauses_recovered,
                "recovery_rate": self.pauses_recovered / self.pauses_triggered if self.pauses_triggered > 0 else 0.0,
                "pause_by_trigger": self.pause_by_trigger,
            },
            "timing": {
                "total_runtime_seconds": self.total_runtime_seconds,
                "total_paused_seconds": self.total_paused_seconds,
                "mean_recovery_time_seconds": self.mean_recovery_time_seconds,
            },
            "transparency": {
                "all_refusals_explained": self.all_refusals_explained,
            }
        }


class TrustMetricsTracker:
    """
    Trust metrics tracker.
    
    Week 8: Tracks safety guarantees and provides transparency.
    
    Key metrics:
    - false_executions: Must be 0 (safety guarantee)
    - pause events: All failures trigger pause
    - recovery: User can recover from all pauses
    - transparency: All refusals explained
    """
    
    def __init__(self):
        """Initialize trust metrics tracker."""
        self.start_time = time.time()
        self.current_frame = 0
        
        # Event logs
        self.pause_events: List[PauseEvent] = []
        self.execution_events: List[ExecutionEvent] = []
        
        # Current state
        self.is_paused = False
        self.current_pause_start: Optional[float] = None
        self.current_pause_event: Optional[PauseEvent] = None
        
        # Metrics
        self.false_executions = 0
        self.confirmed_executions = 0
        self.total_paused_time = 0.0
    
    def record_execution(self, action: str, confirmed: bool, 
                        success: bool = False, result: Optional[str] = None) -> None:
        """
        Record an execution event.
        
        Args:
            action: Action type executed
            confirmed: Whether action was confirmed by user
            success: Whether execution succeeded
            result: Execution result message
        """
        event = ExecutionEvent(
            timestamp=time.time(),
            action=action,
            confirmed=confirmed,
            frame=self.current_frame,
            success=success,
            result=result
        )
        self.execution_events.append(event)
        
        if confirmed:
            self.confirmed_executions += 1
        else:
            self.false_executions += 1
            print(f"⚠️  FALSE EXECUTION DETECTED: {action} (frame {self.current_frame})")
    
    def record_pause(self, trigger: PauseTrigger, explanation: str) -> None:
        """
        Record a pause event.
        
        Args:
            trigger: Pause trigger type
            explanation: Human-readable explanation
        """
        event = PauseEvent(
            timestamp=time.time(),
            trigger=trigger,
            explanation=explanation,
            frame=self.current_frame
        )
        self.pause_events.append(event)
        self.current_pause_event = event
        self.current_pause_start = time.time()
        self.is_paused = True
        
        print(f"📊 Pause recorded: {trigger.value} at frame {self.current_frame}")
    
    def record_recovery(self) -> None:
        """Record successful recovery from pause."""
        if self.current_pause_event and self.current_pause_start:
            recovery_time = time.time() - self.current_pause_start
            self.current_pause_event.recovered = True
            self.current_pause_event.recovery_time = recovery_time
            self.total_paused_time += recovery_time
            
            print(f"✓ Recovery recorded: {recovery_time:.2f}s")
        
        self.is_paused = False
        self.current_pause_start = None
        self.current_pause_event = None
    
    def tick(self, frame: Optional[int] = None) -> None:
        """
        Advance tracker one frame.
        
        Args:
            frame: Optional explicit frame number
        """
        if frame is not None:
            self.current_frame = frame
        else:
            self.current_frame += 1
    
    def generate_report(self) -> TrustReport:
        """
        Generate trust metrics report.
        
        Returns:
            TrustReport with all metrics
        """
        # Calculate pause breakdown
        pause_by_trigger: Dict[str, int] = {}
        for event in self.pause_events:
            trigger_name = event.trigger.value
            pause_by_trigger[trigger_name] = pause_by_trigger.get(trigger_name, 0) + 1
        
        # Calculate recovery metrics
        pauses_recovered = sum(1 for e in self.pause_events if e.recovered)
        recovery_times = [e.recovery_time for e in self.pause_events if e.recovery_time is not None]
        mean_recovery_time = sum(recovery_times) / len(recovery_times) if recovery_times else 0.0
        
        # Check transparency (all pauses have explanations)
        all_explained = all(bool(e.explanation) for e in self.pause_events)
        
        # Calculate runtime
        runtime = time.time() - self.start_time
        
        return TrustReport(
            false_executions=self.false_executions,
            confirmed_executions=self.confirmed_executions,
            pauses_triggered=len(self.pause_events),
            pauses_recovered=pauses_recovered,
            pause_by_trigger=pause_by_trigger,
            total_runtime_seconds=runtime,
            total_paused_seconds=self.total_paused_time,
            mean_recovery_time_seconds=mean_recovery_time,
            all_refusals_explained=all_explained
        )
    
    def save_report(self, filepath: str) -> None:
        """
        Save trust report to JSON file.
        
        Args:
            filepath: Path to save report
        """
        report = self.generate_report()
        with open(filepath, 'w') as f:
            json.dump(report.to_dict(), f, indent=2)
        print(f"✓ Trust report saved to {filepath}")
    
    def print_summary(self) -> None:
        """Print trust metrics summary to console."""
        report = self.generate_report()
        
        print("\n" + "="*60)
        print("TRUST METRICS SUMMARY (Week 8)")
        print("="*60)
        
        print("\n🛡️  SAFETY GUARANTEES:")
        print(f"  False executions: {report.false_executions} (must be 0)")
        print(f"  Confirmed executions: {report.confirmed_executions}")
        if report.false_executions == 0:
            print("  ✅ SAFETY GUARANTEE: PASS")
        else:
            print("  ❌ SAFETY GUARANTEE: FAIL")
        
        print("\n⏸️  PAUSE METRICS:")
        print(f"  Pauses triggered: {report.pauses_triggered}")
        print(f"  Pauses recovered: {report.pauses_recovered}")
        if report.pauses_triggered > 0:
            recovery_rate = report.pauses_recovered / report.pauses_triggered * 100
            print(f"  Recovery rate: {recovery_rate:.1f}%")
        
        if report.pause_by_trigger:
            print("\n  Pause breakdown:")
            for trigger, count in sorted(report.pause_by_trigger.items()):
                print(f"    - {trigger}: {count}")
        
        print("\n⏱️  TIMING:")
        print(f"  Total runtime: {report.total_runtime_seconds:.2f}s")
        print(f"  Total paused: {report.total_paused_seconds:.2f}s")
        if report.mean_recovery_time_seconds > 0:
            print(f"  Mean recovery time: {report.mean_recovery_time_seconds:.2f}s")
        
        print("\n📝 TRANSPARENCY:")
        if report.all_refusals_explained:
            print("  ✅ All refusals explained")
        else:
            print("  ❌ Some refusals not explained")
        
        print("="*60 + "\n")
    
    def reset(self) -> None:
        """Reset all metrics."""
        self.start_time = time.time()
        self.current_frame = 0
        self.pause_events.clear()
        self.execution_events.clear()
        self.is_paused = False
        self.current_pause_start = None
        self.current_pause_event = None
        self.false_executions = 0
        self.confirmed_executions = 0
        self.total_paused_time = 0.0




