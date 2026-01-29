"""
Action type definitions for robot arm control.
Week 2: Three core actions (semantics only, no execution yet).
"""

from enum import Enum


class ArmActionType(str, Enum):
    """
    Robot arm action types.
    
    Week 2: Only availability rules defined.
    Week 5+: Execution implemented.
    """
    MOVE_ARM_UP = "move_arm_up"
    REACH_FORWARD = "reach_forward"
    GRASP_OBJECT = "grasp_object"
    PLACE_OBJECT = "place_object"  # NEW: Place held object in place zone
    
    def __str__(self) -> str:
        """String representation (just the value)."""
        return self.value


