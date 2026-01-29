"""
Object state representation for world model.
Week 2: Read object pose, velocity, and visibility from PyBullet.
"""

from typing import Optional
from dataclasses import dataclass
import numpy as np
import pybullet as p
from utils.safe_pybullet import safe_get_pose


@dataclass
class ObjectState:
    """
    Immutable snapshot of object state.
    
    Attributes:
        object_id: PyBullet body ID
        pos: Position [x, y, z] in world frame
        orn: Orientation quaternion [x, y, z, w]
        lin_vel: Linear velocity [vx, vy, vz]
        ang_vel: Angular velocity [wx, wy, wz]
        visible: Whether object is visible (Week 2: always True)
    """
    object_id: int
    pos: np.ndarray       # Shape: (3,)
    orn: np.ndarray       # Shape: (4,) quaternion
    lin_vel: np.ndarray   # Shape: (3,)
    ang_vel: np.ndarray   # Shape: (3,)
    visible: bool
    
    def __repr__(self) -> str:
        """Human-readable summary."""
        return (
            f"ObjectState(\n"
            f"  id: {self.object_id}\n"
            f"  pos: {np.round(self.pos, 3)}\n"
            f"  visible: {self.visible}\n"
            f")"
        )


def read_object_state(object_id: int) -> Optional[ObjectState]:
    """
    Read current object state from PyBullet - returns None if invalid.
    
    Returns None if object ID is invalid or object has been removed.
    
    Args:
        object_id: PyBullet body ID
        
    Returns:
        ObjectState snapshot, or None if invalid/removed
    """
    # Guard against invalid IDs
    if object_id is None or object_id < 0:
        return None
    
    # STEP B5: Use safe wrapper - returns None if body invalid
    pose = safe_get_pose(object_id)
    
    if pose is None:
        return None  # Object doesn't exist
    
    pos, orn = pose
    
    # Get velocities (object is validated, so this should be safe)
    # Still wrapped in try-except as defensive programming
    try:
        lin_vel, ang_vel = p.getBaseVelocity(object_id)
    except Exception:
        # If velocity read fails, return None (object may have been removed)
        return None
    
    return ObjectState(
        object_id=object_id,
        pos=np.array(pos, dtype=np.float64),
        orn=np.array(orn, dtype=np.float64),
        lin_vel=np.array(lin_vel, dtype=np.float64),
        ang_vel=np.array(ang_vel, dtype=np.float64),
        visible=True  # Week 2: always visible (camera vision comes later)
    )

