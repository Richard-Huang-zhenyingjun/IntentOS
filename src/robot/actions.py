"""Robot action definitions."""

from enum import Enum
from dataclasses import dataclass
from typing import Callable
import numpy as np


class ActionType(str, Enum):
    """High-level action types"""
    IDLE = "idle"
    
    # Week 0 actions
    MOVE_UP = "move_up"        # Raise arm to safe height
    REACH = "reach"            # Move to object
    GRASP = "grasp"            # Attach object
    PLACE = "place"            # Release object at target
    
    # NEW Week 1 action
    CLEAN_TABLE = "clean_table"


@dataclass
class ActionSpec:
    """Action specification."""
    name: str
    description: str
    estimated_duration: float  # seconds
    
    def __str__(self):
        return f"{self.name}: {self.description}"


# Action catalog
ACTION_SPECS = {
    ActionType.MOVE_UP: ActionSpec(
        name="Move Up",
        description="Raise arm to safe working height",
        estimated_duration=1.5
    ),
    ActionType.REACH: ActionSpec(
        name="Reach",
        description="Move end effector to object position",
        estimated_duration=2.0
    ),
    ActionType.GRASP: ActionSpec(
        name="Grasp",
        description="Attach object to end effector",
        estimated_duration=0.5
    ),
    ActionType.PLACE: ActionSpec(
        name="Place",
        description="Release object at target location",
        estimated_duration=1.5
    ),
}

