"""
Robot arm state representation.
Read-only snapshot of joint angles, velocities, and end effector pose.
Week 1: State inspection only (no modification).
"""

from dataclasses import dataclass
from typing import Optional
import numpy as np
import pybullet as p
from .arm_model import ArmModel
from utils.safe_pybullet import is_valid_body


@dataclass
class ArmState:
    """
    Immutable snapshot of robot arm state.
    
    Attributes:
        q: Joint angles (radians)
        dq: Joint velocities (rad/s)
        ee_pos: End effector position [x, y, z] in world frame
        ee_orn: End effector orientation (quaternion [x, y, z, w])
        ee_pose_matrix: 4x4 transformation matrix (optional)
    """
    q: np.ndarray        # Shape: (n_joints,)
    dq: np.ndarray       # Shape: (n_joints,)
    ee_pos: np.ndarray   # Shape: (3,)
    ee_orn: np.ndarray   # Shape: (4,) quaternion
    
    @property
    def num_joints(self) -> int:
        """Number of joints in this state."""
        return len(self.q)
    
    def __repr__(self) -> str:
        """Human-readable state summary."""
        return (
            f"ArmState(\n"
            f"  joints: {self.num_joints}\n"
            f"  q: {np.round(self.q, 3)}\n"
            f"  ee_pos: {np.round(self.ee_pos, 3)}\n"
            f")"
        )


def read_arm_state(arm_model: ArmModel) -> Optional[ArmState]:
    """
    Read current arm state from PyBullet simulation.
    
    STEP D: Validates robot body ID before reading state.
    
    Args:
        arm_model: Robot arm model with body_id and joint metadata
        
    Returns:
        ArmState snapshot of current configuration, or None if body invalid
    """
    # STEP D: Validate robot body ID before reading state
    if not is_valid_body(arm_model.body_id):
        return None  # Robot body invalid or removed
    
    try:
        # Read joint states (body validated, so this should be safe)
        joint_states = p.getJointStates(
            arm_model.body_id,
            arm_model.joint_indices
        )
        
        q = np.array([state[0] for state in joint_states])   # positions
        dq = np.array([state[1] for state in joint_states])  # velocities
        
        # Read end effector pose (body validated, so this should be safe)
        ee_state = p.getLinkState(
            arm_model.body_id,
            arm_model.ee_link_index,
            computeForwardKinematics=True
        )
        
        ee_pos = np.array(ee_state[4])  # World position
        ee_orn = np.array(ee_state[5])  # World orientation (quaternion)
        
        return ArmState(
            q=q,
            dq=dq,
            ee_pos=ee_pos,
            ee_orn=ee_orn
        )
    except Exception:
        # If read fails, return None (body may have been removed)
        return None
