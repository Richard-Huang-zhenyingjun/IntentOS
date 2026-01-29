"""
Undo and return-to-rest actions.
Week 8: Safe retreat and recovery paths.
"""

from typing import Optional, Tuple
import numpy as np
import pybullet as p
from dataclasses import dataclass

from robotics.arm_state import read_arm_state
from robotics.ik_solver import solve_ik
from robotics.trajectory import TrajectoryPlan, plan_steps
from robotics.safety_limits import clamp_joint_step, compute_pose_error
from robotics.execution_result import ExecutionResult
from robotics.gripper_state import GripperState


@dataclass
class UndoResult:
    """Result of undo/return-to-rest operation."""
    success: bool
    reason: str
    steps_used: int = 0


class UndoController:
    """
    Undo and return-to-rest controller.
    
    Week 8: Provides safe retreat paths:
    - Return to rest pose
    - Detach before rest (if holding object)
    - Safe motion planning
    """
    
    def __init__(self, config: dict):
        """
        Initialize undo controller.
        
        Args:
            config: Recovery section from robotics.yaml
        """
        self.config = config
        self.undo_cfg = config.get('undo', {})
        self.rest_pose_cfg = config.get('rest_pose', {})
        
        self.enable_return_to_rest = self.undo_cfg.get('enable_return_to_rest', True)
        self.detach_before_rest = self.undo_cfg.get('detach_before_rest', True)
        
        # Rest pose joint positions (empty = use current)
        self.rest_joint_positions = self.rest_pose_cfg.get('joint_positions', [])
        
        # Execution state
        self.active = False
        self.trajectory: Optional[TrajectoryPlan] = None
        self.steps_used = 0
        self.max_steps = 1200  # 10s at 120Hz
    
    def start_return_to_rest(self, sim, grasp_logic) -> bool:
        """
        Start return to rest pose.
        
        Args:
            sim: ArmSimulator instance
            grasp_logic: GraspLogic instance
            
        Returns:
            True if started successfully, False otherwise
        """
        if not self.enable_return_to_rest:
            print("⚠️  Return to rest disabled")
            return False
        
        # Detach if holding object
        if self.detach_before_rest and grasp_logic.is_holding():
            grasp_logic.detach()
            print("✓ Detached object before return to rest")
        
        # Get current state
        arm_state = read_arm_state(sim.robot)
        
        # Determine rest pose
        if self.rest_joint_positions:
            # Use configured rest pose
            q_rest = np.array(self.rest_joint_positions)
        else:
            # Use current pose as rest
            q_rest = arm_state.q.copy()
            print("✓ Using current pose as rest position")
        
        # Plan trajectory to rest pose
        self.trajectory = plan_steps(
            q_start=arm_state.q,
            q_goal=q_rest,
            max_steps=self.max_steps
        )
        
        self.active = True
        self.steps_used = 0
        
        print(f"✓ Starting return to rest (steps: {self.trajectory.total_steps})")
        return True
    
    def tick(self, sim) -> Tuple[bool, Optional[UndoResult]]:
        """
        Execute one tick of return to rest.
        
        Args:
            sim: ArmSimulator instance
            
        Returns:
            (done, result) tuple
        """
        if not self.active or self.trajectory is None:
            return False, None
        
        # Check timeout
        if self.steps_used >= self.max_steps:
            self.active = False
            return True, UndoResult(
                success=False,
                reason="Return to rest timed out",
                steps_used=self.steps_used
            )
        
        # Get current state
        arm_state = read_arm_state(sim.robot)
        
        # Get next target from trajectory
        q_target = self.trajectory.step()
        self.steps_used += 1
        
        # Apply clamped joint control
        q_clamped = clamp_joint_step(arm_state.q, q_target, max_step=0.02)
        
        p.setJointMotorControlArray(
            sim.robot.body_id,
            sim.robot.joint_indices,
            controlMode=p.POSITION_CONTROL,
            targetPositions=q_clamped.tolist(),
            forces=[100.0] * len(sim.robot.joint_indices)
        )
        
        # Check completion
        if self.trajectory.is_complete():
            self.active = False
            return True, UndoResult(
                success=True,
                reason="Returned to rest pose",
                steps_used=self.steps_used
            )
        
        return False, None
    
    def cancel(self) -> None:
        """Cancel active return to rest."""
        if self.active:
            print("⚠️  Cancelled return to rest")
            self.active = False
    
    def reset(self) -> None:
        """Reset undo controller."""
        self.active = False
        self.trajectory = None
        self.steps_used = 0
    
    def is_active(self) -> bool:
        """Check if undo controller is active."""
        return self.active

