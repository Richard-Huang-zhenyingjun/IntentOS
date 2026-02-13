from dataclasses import dataclass, field
from typing import Optional
import numpy as np
from enum import Enum

class PrimitiveType(Enum):
    """Week 1 primitive actions"""
    REACH = "reach"          # Move end effector to position
    GRASP = "grasp"          # Attach grasp constraint
    MOVE_TO = "move_to"      # Move to position (while grasping)
    RELEASE = "release"      # Detach grasp constraint

@dataclass
class Primitive:
    """Single executable action in a plan"""
    type: PrimitiveType
    target_xyz: Optional[np.ndarray] = None  # For REACH, MOVE_TO
    object_id: Optional[int] = None          # For GRASP, RELEASE
    metadata: dict = field(default_factory=dict)  # Debug info
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}



