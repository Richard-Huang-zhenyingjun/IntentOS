"""
Fault injection system for testing recovery.
Week 8: Deterministic fault injection for validation.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import random


class FaultType(str, Enum):
    """Types of faults that can be injected."""
    EEG_DROPOUT = "eeg_dropout"           # Simulate EEG disconnection
    EEG_UNSTABLE = "eeg_unstable"         # Simulate unstable signal
    TARGET_LOST = "target_lost"           # Simulate target disappearing
    ACTION_TIMEOUT = "action_timeout"     # Simulate slow action
    COLLISION = "collision"               # Simulate collision (reserved)


@dataclass
class ScheduledFault:
    """
    A fault scheduled to occur at a specific time.
    
    Attributes:
        fault_type: Type of fault to inject
        trigger_frame: Frame number when fault should trigger
        duration_frames: How long fault lasts (0 = instant)
        metadata: Additional fault-specific data
    """
    fault_type: FaultType
    trigger_frame: int
    duration_frames: int = 0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class FaultInjector:
    """
    Fault injection system for testing recovery.
    
    Week 8 design:
    - Deterministic (seeded random)
    - Scheduled faults (frame-based)
    - Transparent (logs all injections)
    - Configurable via YAML
    
    Usage:
        injector = FaultInjector(config)
        injector.schedule_fault(FaultType.EEG_DROPOUT, frame=100, duration=30)
        
        # In control loop:
        if injector.should_inject_eeg_dropout(current_frame):
            # Simulate dropout
            ...
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize fault injector.
        
        Args:
            config: Faults section from robotics.yaml
        """
        self.config = config
        self.enabled = config.get('enabled', False)
        self.seed = config.get('seed', 42)
        
        # Scheduled faults from config
        self.schedule: List[ScheduledFault] = []
        for fault_dict in config.get('schedule', []):
            self.schedule.append(ScheduledFault(**fault_dict))
        
        # Runtime state
        self.current_frame = 0
        self.active_faults: Dict[FaultType, ScheduledFault] = {}
        self.injection_log: List[str] = []
        
        # Seed random for deterministic behavior
        random.seed(self.seed)
        
        if self.enabled:
            print(f"⚠️  Fault injection ENABLED (seed={self.seed}, {len(self.schedule)} scheduled)")
    
    def tick(self, frame: Optional[int] = None) -> None:
        """
        Advance fault injector one frame.
        
        Args:
            frame: Optional explicit frame number (otherwise auto-increments)
        """
        if not self.enabled:
            return
        
        if frame is not None:
            self.current_frame = frame
        else:
            self.current_frame += 1
        
        # Check scheduled faults
        for fault in self.schedule:
            if fault.trigger_frame == self.current_frame:
                self._activate_fault(fault)
        
        # Deactivate expired faults
        expired = []
        for fault_type, fault in self.active_faults.items():
            if fault.duration_frames > 0:
                end_frame = fault.trigger_frame + fault.duration_frames
                if self.current_frame >= end_frame:
                    expired.append(fault_type)
        
        for fault_type in expired:
            self._deactivate_fault(fault_type)
    
    def schedule_fault(self, fault_type: FaultType, trigger_frame: int,
                      duration_frames: int = 0, metadata: Dict[str, Any] = None) -> None:
        """
        Schedule a fault to occur at a specific frame.
        
        Args:
            fault_type: Type of fault
            trigger_frame: Frame when fault triggers
            duration_frames: How long fault lasts (0 = instant)
            metadata: Additional fault-specific data
        """
        fault = ScheduledFault(
            fault_type=fault_type,
            trigger_frame=trigger_frame,
            duration_frames=duration_frames,
            metadata=metadata or {}
        )
        self.schedule.append(fault)
        print(f"✓ Scheduled {fault_type.value} at frame {trigger_frame} (duration: {duration_frames})")
    
    def should_inject_eeg_dropout(self) -> bool:
        """Check if EEG dropout should be injected this frame."""
        return self.enabled and FaultType.EEG_DROPOUT in self.active_faults
    
    def should_inject_eeg_unstable(self) -> bool:
        """Check if EEG unstable should be injected this frame."""
        return self.enabled and FaultType.EEG_UNSTABLE in self.active_faults
    
    def should_inject_target_lost(self) -> bool:
        """Check if target lost should be injected this frame."""
        return self.enabled and FaultType.TARGET_LOST in self.active_faults
    
    def should_inject_action_timeout(self) -> bool:
        """Check if action timeout should be injected this frame."""
        return self.enabled and FaultType.ACTION_TIMEOUT in self.active_faults
    
    def is_fault_active(self, fault_type: FaultType) -> bool:
        """Check if a specific fault is currently active."""
        return fault_type in self.active_faults
    
    def get_active_faults(self) -> List[FaultType]:
        """Get list of currently active faults."""
        return list(self.active_faults.keys())
    
    def get_injection_log(self) -> List[str]:
        """Get log of all fault injections."""
        return self.injection_log.copy()
    
    def _activate_fault(self, fault: ScheduledFault) -> None:
        """Activate a fault."""
        self.active_faults[fault.fault_type] = fault
        log_msg = f"Frame {self.current_frame}: INJECT {fault.fault_type.value}"
        if fault.duration_frames > 0:
            log_msg += f" (duration: {fault.duration_frames} frames)"
        self.injection_log.append(log_msg)
        print(f"⚠️  {log_msg}")
    
    def _deactivate_fault(self, fault_type: FaultType) -> None:
        """Deactivate a fault."""
        if fault_type in self.active_faults:
            del self.active_faults[fault_type]
            log_msg = f"Frame {self.current_frame}: CLEAR {fault_type.value}"
            self.injection_log.append(log_msg)
            print(f"✓ {log_msg}")
    
    def reset(self) -> None:
        """Reset fault injector state."""
        self.current_frame = 0
        self.active_faults.clear()
        self.injection_log.clear()
        random.seed(self.seed)
    
    def clear_schedule(self) -> None:
        """Clear all scheduled faults."""
        self.schedule.clear()
        print("✓ Cleared fault schedule")




