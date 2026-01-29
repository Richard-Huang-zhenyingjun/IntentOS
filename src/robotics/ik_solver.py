"""
IK solver - inverse kinematics using PyBullet.
Week 5: Compute joint angles for target end-effector pose.
"""

from typing import Optional
import numpy as np
import pybullet as p
from .arm_model import ArmModel
from .safety_limits import clamp_joint_targets, within_limits


def solve_ik(arm_model: ArmModel,
             target_pos: np.ndarray,
             target_orn: Optional[np.ndarray] = None,
             current_q: Optional[np.ndarray] = None) -> np.ndarray:
    """
    Solve inverse kinematics for target end-effector pose.
    
    Args:
        arm_model: Robot arm model
        target_pos: Target position [x, y, z]
        target_orn: Target orientation quaternion (optional)
        current_q: Current joint angles (used as seed, optional)
        
    Returns:
        Joint angles achieving target pose (clamped to limits)
        
    Raises:
        ValueError: If IK solution violates joint limits after clamping
    """
    # Prepare IK parameters
    ik_kwargs = {
        'lowerLimits': arm_model.joint_lower.tolist(),
        'upperLimits': arm_model.joint_upper.tolist(),
        'jointRanges': (arm_model.joint_upper - arm_model.joint_lower).tolist(),
        'maxNumIterations': 100,
        'residualThreshold': 1e-4
    }
    
    # Only add restPoses if current_q is provided
    if current_q is not None:
        ik_kwargs['restPoses'] = current_q.tolist()
    
    if target_orn is None:
        # Position-only IK
        joint_poses = p.calculateInverseKinematics(
            arm_model.body_id,
            arm_model.ee_link_index,
            target_pos,
            **ik_kwargs
        )
    else:
        # Position + orientation IK
        joint_poses = p.calculateInverseKinematics(
            arm_model.body_id,
            arm_model.ee_link_index,
            target_pos,
            target_orn,
            **ik_kwargs
        )
    
    # Extract only controllable joints (IK returns all joints)
    q_solution = np.array([joint_poses[i] for i in arm_model.joint_indices])
    
    # Safety: clamp to limits
    q_clamped = clamp_joint_targets(q_solution, arm_model.joint_lower, arm_model.joint_upper)
    
    # Verify solution is within limits
    if not within_limits(q_clamped, arm_model.joint_lower, arm_model.joint_upper):
        raise ValueError(f"IK solution violates joint limits: {q_clamped}")
    
    return q_clamped

