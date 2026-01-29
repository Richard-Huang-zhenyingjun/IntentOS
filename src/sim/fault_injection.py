"""
Fault injection - deterministic failure scenarios for testing.
Week 8: Reproducible fault scenarios with seeded randomness.
"""

from dataclasses import dataclass
from typing import List, Set
from enum import Enum
import random


class FaultType(str, Enum):
    """Types of faults that can be injected."""
    EEG_DROPOUT = "eeg_dropout"              # Force EEG unstable/disconnected
    TARGET_LOSS = "target_loss"              # Force target to disappear
    SELECTION_FLICKER = "selection_flicker"  # Make selection unstable
    CONFIRM_BURST = "confirm_burst"          # Spam confirmations (should be blocked)
    HIGH_VARIANCE = "high_variance"          # Force high EEG variance


@dataclass
class ScheduledFault:
    """
    Scheduled fault event.
    
    Attributes:
        time_s: Trigger time (seconds from start)
        fault_type: Type of fault
        duration_s: Fault duration (seconds)
    """
    time_s: float
    fault_type: FaultType
    duration_s: float
    
    def is_active(self, current_time_s: float) -> bool:
        """Check if fault is currently active."""
        return self.time_s <= current_time_s < (self.time_s + self.duration_s)


class FaultInjector:
    """
    Deterministic fault injector.
    
    Injects scheduled faults for testing and demo scenarios.
    Week 8: Seeded randomness for reproducibility.
    """
    
    def __init__(self, seed: int = 42, schedule: List[ScheduledFault] = None):
        """
        Initialize fault injector.
        
        Args:
            seed: Random seed for determinism
            schedule: List of scheduled faults
        """
        self.seed = seed
        self.schedule = schedule or []
        self.start_time: float = 0.0
        self.enabled = False
        
        # Set random seed
        random.seed(seed)
        
        print(f"✓ FaultInjector initialized (seed={seed}, {len(self.schedule)} faults)")
    
    def start(self, start_time: float) -> None:
        """
        Start fault injection.
        
        Args:
            start_time: Simulation start time
        """
        self.start_time = start_time
        self.enabled = True
        print("✓ Fault injection enabled")
    
    def update(self, current_time: float) -> Set[FaultType]:
        """
        Update and get active faults.
        
        Args:
            current_time: Current simulation time
            
        Returns:
            Set of currently active fault types
        """
        if not self.enabled:
            return set()
        
        elapsed = current_time - self.start_time
        
        active_faults = set()
        for fault in self.schedule:
            if fault.is_active(elapsed):
                active_faults.add(fault.fault_type)
        
        return active_faults
    
    def get_status(self, current_time: float) -> dict:
        """
        Get fault injector status.
        
        Args:
            current_time: Current simulation time
            
        Returns:
            Dict with active faults and schedule info
        """
        if not self.enabled:
            return {"enabled": False, "active_faults": []}
        
        elapsed = current_time - self.start_time
        active = self.update(current_time)
        
        # Get upcoming faults
        upcoming = []
        for fault in self.schedule:
            if fault.time_s > elapsed:
                upcoming.append({
                    "type": str(fault.fault_type),
                    "in": fault.time_s - elapsed,
                })
        
        return {
            "enabled": True,
            "seed": self.seed,
            "elapsed": elapsed,
            "active_faults": [str(f) for f in active],
            "upcoming": upcoming[:3],  # Show next 3
        }
