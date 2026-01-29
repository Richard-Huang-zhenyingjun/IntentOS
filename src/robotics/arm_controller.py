"""
Arm controller - autonomous action execution.
Week 5: IK + trajectory + safety + motor control.
This replaces the Week 4 execution stub with real motion.
"""

from typing import Optional, Tuple
import time
import numpy as np
import pybullet as p

from .action_types import ArmActionType
from .arm_actions import get_goal_pose, is_executable, requires_grasp_attach
from .ik_solver import solve_ik
from .trajectory import TrajectoryPlan, plan_steps
from .safety_limits import (
    clamp_joint_targets, clamp_joint_step, clamp_joint_velocity,
    compute_pose_error
)
from .execution_result import ExecutionResult
from .arm_state import read_arm_state
from .gripper_state import GripperState, GripperSnapshot
from .grasp_logic import GraspLogic


class ArmController:
    """
    Autonomous arm controller.
    
    Executes actions approved by user through safe motion:
    1. Compute target EE pose
    2. Solve IK
    3. Plan safe trajectory
    4. Execute with motor control
    5. Monitor completion/timeout
    
    Week 5: MOVE_ARM_UP and REACH_FORWARD.
    Week 7: Add GRASP_OBJECT.
    """
    
    def __init__(self, cfg: dict):
        """
        Initialize controller.
        
        Args:
            cfg: Configuration dict
        """
        self.cfg = cfg
        
        # Active execution state
        self.active_action: Optional[ArmActionType] = None
        self.trajectory: Optional[TrajectoryPlan] = None
        self.target_pos: Optional[np.ndarray] = None
        self.target_orn: Optional[np.ndarray] = None
        self.q_goal: Optional[np.ndarray] = None
        
        # Execution tracking
        self.steps_used: int = 0
        self.cancelled: bool = False
        self.started_at: float = 0.0
        
        # Config shortcuts
        self.max_steps = cfg['control']['max_steps_per_action']
        self.settle_steps = cfg['control']['settle_steps_after']
        self.pos_tolerance = cfg['safety']['pos_tolerance_m']
        self.orn_tolerance = cfg['safety']['orn_tolerance_rad']
        self.max_step_rad = cfg['safety']['max_joint_step_rad']
        self.dt = cfg['physics']['timestep']
        self.max_vel = cfg['safety']['max_joint_vel_rad_s']
        
        # Week 6: Grasp logic
        self.grasp_logic = GraspLogic(cfg)
        self.gripper_state = GripperState.OPEN
        self.gripper_changed_at = 0.0
        
        # Grasp execution phases
        self.grasp_phase: Optional[str] = None  # "approaching", "attaching", "lifting"
        self.lift_started = False
        
        # Week 8: Recovery state
        self.rest_pose_q: Optional[np.ndarray] = None
        self.frozen = False
    
    def start_action(self, action_type: ArmActionType, world, sim) -> None:
        """
        Start executing an action.
        
        Args:
            action_type: Action to execute
            world: WorldModel instance
            sim: ArmSimulator instance
            
        Raises:
            ValueError: If action not executable
        """
        # Check if action is executable
        if not is_executable(action_type):
            raise ValueError(f"Action not executable: {action_type}")
        
        self.active_action = action_type
        self.cancelled = False
        self.steps_used = 0
        self.started_at = time.time()
        
        # Week 6: Initialize grasp phase if needed
        if requires_grasp_attach(action_type):
            self.grasp_phase = "approaching"
            self.lift_started = False
        else:
            self.grasp_phase = None
        
        # Compute target pose
        self.target_pos, self.target_orn, reason = get_goal_pose(action_type, world, self.cfg)
        
        print(f"✓ Starting execution: {action_type}")
        print(f"  Target: {self.target_pos}")
        print(f"  Reason: {reason}")
        if self.grasp_phase:
            print(f"  Grasp phase: {self.grasp_phase}")
        
        # Get current joint configuration
        arm_state = read_arm_state(sim.robot)
        q_current = arm_state.q
        
        # Solve IK
        try:
            self.q_goal = solve_ik(
                sim.robot,
                self.target_pos,
                self.target_orn,
                current_q=q_current
            )
        except ValueError as e:
            print(f"⚠️  IK solver failed: {e}")
            self.q_goal = q_current  # Fallback: stay in place
            return
        
        # Plan trajectory
        steps_needed = plan_steps(q_current, self.q_goal, self.max_step_rad)
        self.trajectory = TrajectoryPlan(
            q_start=q_current,
            q_goal=self.q_goal,
            steps_total=steps_needed
        )
        
        print(f"  Planned {steps_needed} steps")
    
    def tick(self, world, sim) -> Tuple[bool, Optional[ExecutionResult]]:
        """
        Advance execution one step.
        
        Args:
            world: WorldModel instance
            sim: ArmSimulator instance
            
        Returns:
            (done, result) where:
            - done: True if execution complete or failed
            - result: ExecutionResult if done, else None
        """
        # Week 8: Don't tick if frozen
        if self.frozen:
            return False, None
        
        if self.active_action is None or self.trajectory is None:
            return True, ExecutionResult(
                success=False,
                reason="No active action",
                steps_used=0,
                final_error_pos=0.0
            )
        
        # Check cancellation
        if self.cancelled:
            return self._finish_cancelled(world, sim)
        
        # Check timeout
        if self.steps_used >= self.max_steps:
            return self._finish_timeout(world, sim)
        
        # Get current state
        arm_state = read_arm_state(sim.robot)
        q_current = arm_state.q
        
        # Get next trajectory point
        q_next = self.trajectory.next_q()
        
        # Apply safety limits
        q_safe = clamp_joint_targets(q_next, sim.robot.joint_lower, sim.robot.joint_upper)
        q_safe = clamp_joint_step(q_current, q_safe, self.max_step_rad)
        q_safe = clamp_joint_velocity(q_current, q_safe, self.dt, self.max_vel)
        
        # Apply motor control
        p.setJointMotorControlArray(
            sim.robot.body_id,
            sim.robot.joint_indices,
            controlMode=p.POSITION_CONTROL,
            targetPositions=q_safe.tolist(),
            forces=[200.0] * len(sim.robot.joint_indices)  # Increased force for faster motion (3x speed)
        )
        
        self.steps_used += 1
        
        # Check completion (after settle period)
        # CRITICAL: If in lifting phase, check lift completion when trajectory is done
        if requires_grasp_attach(self.active_action) and self.grasp_phase == "lifting":
            # Diagnostic: Log lift phase status
            if self.steps_used == 0:
                print(f"\n[LIFT] Starting lift execution:")
                print(f"  Trajectory exists: {self.trajectory is not None}")
                print(f"  Trajectory steps: {self.trajectory.steps_total if self.trajectory else 'N/A'}")
                print(f"  Target pos: {self.target_pos}")
                print(f"  Current EE pos: {world.arm_state.ee_pos}")
            
            # Check if trajectory exists
            if self.trajectory is None:
                print("[LIFT] ⚠️ ERROR: Trajectory is None in lifting phase!")
                return True, ExecutionResult(
                    success=False,
                    reason="Lift trajectory missing",
                    steps_used=self.steps_used,
                    final_error_pos=0.0,
                    action_type=str(self.active_action)
                )
            
            # Lift phase: check lift completion when trajectory is complete
            if self.trajectory.is_complete() and self.steps_used > self.trajectory.steps_total + self.settle_steps:
                return self._handle_grasp_completion(world, sim, 0.0, 0.0)
            else:
                # Still lifting - log progress periodically
                if self.steps_used % 20 == 0:  # Log every 20 steps for more frequent updates
                    progress = self.trajectory.progress() if self.trajectory else 0.0
                    current_pos = world.arm_state.ee_pos
                    print(f"  [LIFT] {progress*100:.0f}% complete | Step {self.steps_used}/{self.trajectory.steps_total + self.settle_steps} | EE z={current_pos[2]:.3f}m")
                return False, None  # Continue lifting
        elif self.trajectory.is_complete() and self.steps_used > self.trajectory.steps_total + self.settle_steps:
            # Normal completion check
            return self._check_completion(world, sim)
        
        return False, None  # Continue executing
    
    def _check_completion(self, world, sim) -> Tuple[bool, Optional[ExecutionResult]]:
        """Check if target reached and handle grasp-specific logic."""
        arm_state = read_arm_state(sim.robot)
        pos_error, orn_error = compute_pose_error(
            arm_state.ee_pos, self.target_pos,
            arm_state.ee_orn if self.target_orn is not None else None,
            self.target_orn
        )
        
        # Check if within tolerance
        if pos_error < self.pos_tolerance:
            if self.target_orn is None or orn_error < self.orn_tolerance:
                # Position reached - handle grasp logic
                if requires_grasp_attach(self.active_action):
                    return self._handle_grasp_completion(world, sim, pos_error, orn_error)
                else:
                    # Non-grasp action: success
                    return True, ExecutionResult(
                        success=True,
                        reason="Target reached",
                        steps_used=self.steps_used,
                        final_error_pos=pos_error,
                        final_error_orn=orn_error if self.target_orn is not None else None,
                        action_type=str(self.active_action)
                    )
        
        # Keep going if not converged yet
        return False, None
    
    def _handle_grasp_completion(self, world, sim, pos_error: float, orn_error: float) -> Tuple[bool, Optional[ExecutionResult]]:
        """Handle grasp-specific completion logic."""
        
        # Phase 1: Approaching - try to attach
        if self.grasp_phase == "approaching":
            if self.grasp_logic.can_attach(world, sim):
                # Attempt attachment
                success = self.grasp_logic.attach(sim, world.target_object_id)
                
                if success:
                    self.gripper_state = GripperState.CLOSED
                    self.gripper_changed_at = time.time()
                    print("\n" + "="*60)
                    print("✓✓✓ OBJECT ATTACHED SUCCESSFULLY ✓✓✓")
                    print(f"  Object ID: {world.target_object_id}")
                    print(f"  Constraint ID: {self.grasp_logic.constraint_id}")
                    print(f"  Current EE position: {world.arm_state.ee_pos}")
                    print("="*60)
                    
                    # Check if post-grasp lift enabled
                    if self.cfg['grasp'].get('enable_post_grasp_lift', True):
                        print("\n[GRASP] Transitioning to LIFTING phase...")
                        self.grasp_phase = "lifting"
                        self._start_post_grasp_lift(world, sim)
                        print(f"[GRASP] Lift phase set to: {self.grasp_phase}")
                        print(f"[GRASP] Trajectory exists: {self.trajectory is not None}")
                        if self.trajectory:
                            print(f"[GRASP] Trajectory steps: {self.trajectory.steps_total}")
                        return False, None  # Continue to lift phase
                    else:
                        # No lift: complete immediately
                        print("[GRASP] Post-grasp lift DISABLED - completing action")
                        return True, ExecutionResult(
                            success=True,
                            reason="Grasped object (no lift)",
                            steps_used=self.steps_used,
                            final_error_pos=pos_error,
                            final_error_orn=orn_error,
                            action_type=str(self.active_action)
                        )
                else:
                    # Attachment failed
                    return True, ExecutionResult(
                        success=False,
                        reason="Attachment failed (too far or already holding)",
                        steps_used=self.steps_used,
                        final_error_pos=pos_error,
                        action_type=str(self.active_action)
                    )
            else:
                # Not close enough to attach
                return True, ExecutionResult(
                    success=False,
                    reason=f"Cannot attach (pos_err={pos_error:.3f}m > {self.cfg['grasp']['attach_dist_m']}m)",
                    steps_used=self.steps_used,
                    final_error_pos=pos_error,
                    action_type=str(self.active_action)
                )
        
        # Phase 2: Lifting - completion is checked in tick() before calling this
        elif self.grasp_phase == "lifting":
            # This is only called when lift trajectory is complete (checked in tick())
            print(f"✓ Post-grasp lift complete (lifted {self.cfg['grasp']['lift_after_grasp_delta_z']*100:.1f}cm)")
            return True, ExecutionResult(
                success=True,
                reason=f"Grasped and lifted object ({self.cfg['grasp']['lift_after_grasp_delta_z']*100:.1f}cm)",
                steps_used=self.steps_used,
                final_error_pos=pos_error,
                final_error_orn=orn_error,
                action_type=str(self.active_action)
            )
        
        # Still executing
        return False, None
    
    def _start_post_grasp_lift(self, world, sim) -> None:
        """Start post-grasp lift (move up with object attached)."""
        arm_state = read_arm_state(sim.robot)
        current_pos = arm_state.ee_pos
        
        # Lift target
        lift_delta = self.cfg['grasp']['lift_after_grasp_delta_z']
        lift_target = np.array([current_pos[0], current_pos[1], current_pos[2] + lift_delta])
        
        print(f"\n✓ Starting post-grasp lift: +{lift_delta*100:.1f}cm (from z={current_pos[2]:.3f}m to z={lift_target[2]:.3f}m)")
        
        # Reset step counter for lift phase
        self.steps_used = 0
        
        # Solve IK for lift
        try:
            q_lift_goal = solve_ik(sim.robot, lift_target, current_q=arm_state.q)
            
            # Plan lift trajectory
            steps_needed = plan_steps(arm_state.q, q_lift_goal, self.max_step_rad)
            self.trajectory = TrajectoryPlan(
                q_start=arm_state.q,
                q_goal=q_lift_goal,
                steps_total=steps_needed
            )
            self.target_pos = lift_target
            
            print(f"  ✓ Planned {steps_needed} lift steps (will take ~{steps_needed/120:.2f}s at 120Hz)")
        except ValueError as e:
            print(f"⚠️  Post-grasp lift IK failed: {e}")
            print(f"  Current pos: {current_pos}, Target pos: {lift_target}")
    
    def _finish_timeout(self, world, sim) -> Tuple[bool, ExecutionResult]:
        """Handle timeout."""
        arm_state = read_arm_state(sim.robot)
        pos_error, orn_error = compute_pose_error(
            arm_state.ee_pos, self.target_pos
        )
        
        return True, ExecutionResult(
            success=False,
            reason=f"Timeout after {self.steps_used} steps (pos_err={pos_error:.3f}m)",
            steps_used=self.steps_used,
            final_error_pos=pos_error,
            final_error_orn=orn_error,
            action_type=str(self.active_action)
        )
    
    def _finish_cancelled(self, world, sim) -> Tuple[bool, ExecutionResult]:
        """Handle cancellation."""
        # Week 6: Detach if holding object and configured to do so
        if self.cfg['grasp']['detach_on_cancel'] and self.grasp_logic.is_holding():
            self.grasp_logic.detach()
            self.gripper_state = GripperState.OPEN
            self.gripper_changed_at = time.time()
            print("✓ Detached object on cancel")
        
        # Hold current position
        arm_state = read_arm_state(sim.robot)
        p.setJointMotorControlArray(
            sim.robot.body_id,
            sim.robot.joint_indices,
            controlMode=p.POSITION_CONTROL,
            targetPositions=arm_state.q.tolist(),
            forces=[100.0] * len(sim.robot.joint_indices)
        )
        
        pos_error, _ = compute_pose_error(arm_state.ee_pos, self.target_pos)
        
        return True, ExecutionResult(
            success=False,
            reason="Cancelled by user",
            steps_used=self.steps_used,
            final_error_pos=pos_error,
            action_type=str(self.active_action)
        )
    
    def cancel(self) -> None:
        """Cancel active execution."""
        if self.active_action is not None:
            print(f"⚠️  Cancelling execution: {self.active_action}")
            self.cancelled = True
    
    def reset(self) -> None:
        """Reset controller state."""
        self.active_action = None
        self.trajectory = None
        self.target_pos = None
        self.target_orn = None
        self.q_goal = None
        self.steps_used = 0
        self.cancelled = False
        self.grasp_phase = None
        self.lift_started = False
    
    def capture_rest_pose(self, sim) -> None:
        """
        Capture current pose as rest pose.
        
        Args:
            sim: ArmSimulator instance
        """
        arm_state = read_arm_state(sim.robot)
        self.rest_pose_q = arm_state.q.copy()
        print(f"✓ Rest pose captured: {self.rest_pose_q}")
    
    def freeze_hold(self, sim) -> None:
        """
        Freeze robot in current position.
        
        Args:
            sim: ArmSimulator instance
        """
        if self.frozen:
            return
        
        arm_state = read_arm_state(sim.robot)
        
        # Hold current position with position control
        p.setJointMotorControlArray(
            sim.robot.body_id,
            sim.robot.joint_indices,
            controlMode=p.POSITION_CONTROL,
            targetPositions=arm_state.q.tolist(),
            forces=[200.0] * len(sim.robot.joint_indices)
        )
        
        self.frozen = True
        print("⚠️  Robot frozen in current position")
    
    def unfreeze(self) -> None:
        """Unfreeze robot (allow new trajectories)."""
        if self.frozen:
            self.frozen = False
            print("✓ Robot unfrozen")
    
    def return_to_rest(self, world, sim) -> bool:
        """
        Start trajectory to return to rest pose.
        
        Args:
            world: WorldModel instance
            sim: ArmSimulator instance
            
        Returns:
            True if trajectory started
        """
        # Unfreeze first
        self.unfreeze()
        
        # Determine rest pose
        if self.rest_pose_q is None:
            # Use current pose as rest
            arm_state = read_arm_state(sim.robot)
            q_rest = arm_state.q
            print("⚠️  No rest pose captured, using current pose")
        else:
            q_rest = self.rest_pose_q
        
        # Get current state
        arm_state = read_arm_state(sim.robot)
        q_current = arm_state.q
        
        # Plan trajectory to rest
        steps_needed = plan_steps(q_current, q_rest, self.max_step_rad)
        
        self.trajectory = TrajectoryPlan(
            q_start=q_current,
            q_goal=q_rest,
            steps_total=steps_needed
        )
        
        self.q_goal = q_rest
        self.active_action = None  # Not a user action
        self.cancelled = False
        self.steps_used = 0
        
        print(f"✓ Returning to rest pose ({steps_needed} steps)")
        return True
    
    def undo_last_action(self, world, sim) -> bool:
        """
        Undo last action (detach if holding, return to rest).
        
        Args:
            world: WorldModel instance
            sim: ArmSimulator instance
            
        Returns:
            True if undo started
        """
        print("⚠️  Undo requested")
        
        # Step 1: Detach if holding object
        if self.grasp_logic.is_holding():
            self.grasp_logic.detach()
            self.gripper_state = GripperState.OPEN
            self.gripper_changed_at = time.time()
            print("  ✓ Object detached")
        
        # Step 2: Return to rest
        return self.return_to_rest(world, sim)
    
    def get_progress(self) -> float:
        """Get execution progress [0, 1]."""
        if self.trajectory is None:
            return 0.0
        return self.trajectory.progress()
    
    def is_active(self) -> bool:
        """Check if controller is actively executing."""
        return self.active_action is not None and not self.cancelled
    
    def get_gripper_snapshot(self) -> GripperSnapshot:
        """
        Get current gripper snapshot.
        
        Returns:
            GripperSnapshot with current state
        """
        return GripperSnapshot(
            state=self.gripper_state,
            last_changed_at=self.gripper_changed_at,
            holding_object_id=self.grasp_logic.get_held_object_id()
        )
    
    def get_status(self) -> dict:
        """
        Get controller status for monitoring.
        
        Returns:
            Dict with controller state
        """
        return {
            "active": self.is_active(),
            "active_action": str(self.active_action) if self.active_action else None,
            "steps_used": self.steps_used,
            "progress": self.get_progress(),
            "holding_object_id": self.grasp_logic.get_held_object_id(),
            "cancelled": self.cancelled,
            "frozen": self.frozen,
            "has_rest_pose": self.rest_pose_q is not None,
            "grasp_phase": self.grasp_phase,
        }

