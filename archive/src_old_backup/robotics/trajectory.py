"""
Trajectory planning - safe joint interpolation.
Week 5: Step-by-step motion from start to goal configuration.
"""

from dataclasses import dataclass
import numpy as np
import math


def interpolate_joints(q_start: np.ndarray, 
                       q_goal: np.ndarray, 
                       alpha: float) -> np.ndarray:
    """
    Linear interpolation between joint configurations.
    
    Args:
        q_start: Start joint angles
        q_goal: Goal joint angles
        alpha: Interpolation parameter [0, 1]
        
    Returns:
        Interpolated joint angles
    """
    alpha = np.clip(alpha, 0.0, 1.0)
    return q_start + alpha * (q_goal - q_start)


def plan_steps(q_start: np.ndarray,
               q_goal: np.ndarray,
               max_step_rad: float) -> int:
    """
    Compute number of steps needed for safe trajectory.
    
    Args:
        q_start: Start joint angles
        q_goal: Goal joint angles
        max_step_rad: Maximum joint change per step
        
    Returns:
        Number of steps required
    """
    max_delta = np.max(np.abs(q_goal - q_start))
    steps = int(math.ceil(max_delta / max_step_rad))
    return max(1, steps)  # At least 1 step


@dataclass
class TrajectoryPlan:
    """
    Trajectory plan for joint motion.
    
    Attributes:
        q_start: Start configuration
        q_goal: Goal configuration
        steps_total: Total number of steps
        step_idx: Current step index
    """
    q_start: np.ndarray
    q_goal: np.ndarray
    steps_total: int
    step_idx: int = 0
    
    def next_q(self) -> np.ndarray:
        """
        Get next joint configuration in trajectory.
        
        Returns:
            Next joint angles (interpolated)
        """
        if self.step_idx >= self.steps_total:
            return self.q_goal.copy()
        
        alpha = (self.step_idx + 1) / self.steps_total
        self.step_idx += 1
        
        return interpolate_joints(self.q_start, self.q_goal, alpha)
    
    def progress(self) -> float:
        """
        Get trajectory progress [0, 1].
        
        Returns:
            Progress fraction
        """
        if self.steps_total == 0:
            return 1.0
        return min(1.0, self.step_idx / self.steps_total)
    
    def is_complete(self) -> bool:
        """Check if trajectory is complete."""
        return self.step_idx >= self.steps_total




