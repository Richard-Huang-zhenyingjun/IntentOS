"""
Safety limits - enforce joint limits and velocity constraints.
Week 5: Critical safety layer for motion control.
"""

import numpy as np


def clamp(x: float, lo: float, hi: float) -> float:
    """Clamp value to range [lo, hi]."""
    return max(lo, min(hi, x))


def clamp_joint_targets(q_desired: np.ndarray, 
                        lower: np.ndarray, 
                        upper: np.ndarray) -> np.ndarray:
    """
    Clamp joint angles to valid range.
    
    Args:
        q_desired: Desired joint angles
        lower: Lower joint limits
        upper: Upper joint limits
        
    Returns:
        Clamped joint angles (within limits)
    """
    return np.clip(q_desired, lower, upper)


def clamp_joint_step(q_prev: np.ndarray, 
                     q_next: np.ndarray, 
                     max_step_rad: float) -> np.ndarray:
    """
    Limit maximum joint change per step.
    
    Args:
        q_prev: Previous joint angles
        q_next: Desired next joint angles
        max_step_rad: Maximum change per joint (radians)
        
    Returns:
        Clamped joint angles (max step size respected)
    """
    delta = q_next - q_prev
    delta_clamped = np.clip(delta, -max_step_rad, max_step_rad)
    return q_prev + delta_clamped


def clamp_joint_velocity(q_prev: np.ndarray,
                         q_next: np.ndarray,
                         dt: float,
                         max_vel_rad_s: float) -> np.ndarray:
    """
    Limit joint velocity.
    
    Args:
        q_prev: Previous joint angles
        q_next: Desired next joint angles
        dt: Time step (seconds)
        max_vel_rad_s: Maximum velocity per joint (rad/s)
        
    Returns:
        Clamped joint angles (velocity limit respected)
    """
    max_delta = max_vel_rad_s * dt
    return clamp_joint_step(q_prev, q_next, max_delta)


def within_limits(q: np.ndarray, 
                  lower: np.ndarray, 
                  upper: np.ndarray,
                  tolerance: float = 1e-6) -> bool:
    """
    Check if joint angles are within limits.
    
    Args:
        q: Joint angles
        lower: Lower limits
        upper: Upper limits
        tolerance: Tolerance for boundary checks
        
    Returns:
        True if all joints within limits
    """
    return np.all(q >= lower - tolerance) and np.all(q <= upper + tolerance)


def compute_pose_error(current_pos: np.ndarray,
                       target_pos: np.ndarray,
                       current_orn: np.ndarray = None,
                       target_orn: np.ndarray = None) -> tuple[float, float]:
    """
    Compute position and orientation error.
    
    Args:
        current_pos: Current position [x, y, z]
        target_pos: Target position [x, y, z]
        current_orn: Current orientation quaternion (optional)
        target_orn: Target orientation quaternion (optional)
        
    Returns:
        (position_error, orientation_error) in meters and radians
    """
    pos_error = np.linalg.norm(target_pos - current_pos)
    
    # Orientation error (if provided)
    orn_error = 0.0
    if current_orn is not None and target_orn is not None:
        # Simple quaternion distance (not geodesic, but sufficient)
        orn_error = np.linalg.norm(target_orn - current_orn)
    
    return pos_error, orn_error




