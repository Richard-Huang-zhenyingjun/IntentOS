"""
Gripper state - virtual gripper for grasping simulation.
Week 6: Open/closed states + held object tracking.
Note: KUKA IIWA has no real gripper - we simulate with constraints.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import time


class GripperState(str, Enum):
    """Virtual gripper state."""
    OPEN = "open"
    CLOSED = "closed"


@dataclass
class GripperSnapshot:
    """
    Snapshot of gripper state.
    
    Attributes:
        state: Current gripper state (OPEN/CLOSED)
        last_changed_at: Timestamp of last state change
        holding_object_id: Object ID if holding, else None
    """
    state: GripperState
    last_changed_at: float
    holding_object_id: Optional[int] = None
    
    def is_holding(self) -> bool:
        """Check if gripper is holding an object."""
        return self.holding_object_id is not None
    
    def __repr__(self) -> str:
        """Human-readable summary."""
        holding_str = f"holding object {self.holding_object_id}" if self.is_holding() else "empty"
        return f"Gripper({self.state}, {holding_str})"




