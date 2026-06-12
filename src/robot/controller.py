"""Robot motion controller."""

import math
import logging
import time
import numpy as np
import pybullet as p
from typing import Optional
from src.robot.simulator import RobotSimulator, ArmState
from src.planning.trajectory import (
    IKOutOfLimitsError,
    TrajectoryInterpolator,
    Waypoint,
    calculate_limited_tool_down_ik,
    get_ik_limits,
)

logger = logging.getLogger(__name__)


class RobotController:
    """Control arm motion with IK and safety limits."""
    
    def __init__(self, config: dict, sim: RobotSimulator):
        self.config = config
        self.sim = sim
        
        # NEW: Motor control parameters
        robot_config = config.get('robot', {})
        self.max_force = robot_config.get('max_force', 400.0)
        self.pos_gain = robot_config.get('position_gain', 0.2)
        self.vel_gain = robot_config.get('velocity_gain', 1.0)
        self.tolerance_rad = robot_config.get('tolerance_rad', 0.02)
        self.settle_frames_required = robot_config.get('settle_frames_required', 10)
        
        # Keep backward compatibility
        self.max_joint_velocity = robot_config.get('max_joint_vel_rad_s', 2.5)
        self.position_gain = self.pos_gain  # Alias for backward compatibility
        self.settle_threshold = robot_config.get('settle_threshold', 0.01)
        
        # NEW: Execution state
        self.executing = False
        self.target_joints = None
        self._settle_counter = 0
        
        # Get discovered joint indices and EE link
        self.joint_indices = sim.get_joint_indices()
        self.ee_link_index = sim.get_ee_link_index()
        
        # Execution state (keep existing for backward compatibility)
        self.target_position: Optional[np.ndarray] = None
        self._cmd_force = self.max_force
        self._cmd_pos_gain = self.pos_gain
        self._cmd_vel_gain = self.vel_gain
        self._cmd_max_velocity = self.max_joint_velocity
        self.trajectory_interpolator = TrajectoryInterpolator()
        self._trajectory: Optional[list[Waypoint]] = None
        self._trajectory_index = 0
        self._trajectory_start_time = 0.0
        self.last_motion_error: Optional[str] = None
        self.last_ik_orientation = None
        self.last_ik_orientation_offsets = None
        
        print(f"[CTRL] Initialized with {len(self.joint_indices)} joints")
        print(f"[CTRL] max_force={self.max_force}, tolerance={self.tolerance_rad}")
    
    def move_to_position(
        self,
        target_xyz: np.ndarray,
        slow: bool = False,
        velocity: float = 0.5,
    ):
        """Start moving to target position (does NOT wait for completion)."""
        self.last_motion_error = None
        # Compute IK
        ik_result = self._compute_ik(target_xyz)
        
        if ik_result is None:
            print(f"[CTRL] IK failed for target {target_xyz}")
            self.executing = False
            self.target_joints = None
            return
        
        # Extract joint positions (use discovered joint count)
        n_joints = len(self.joint_indices)
        self.target_joints = np.array(ik_result[:n_joints])
        
        self.executing = True
        self._settle_counter = 0
        if slow:
            self._cmd_force = min(self.max_force, 100.0)
            self._cmd_pos_gain = min(self.pos_gain, 0.03)
            self._cmd_vel_gain = min(self.vel_gain, 0.5)
            self._cmd_max_velocity = max(0.01, float(velocity))
        else:
            self._cmd_force = self.max_force
            self._cmd_pos_gain = self.pos_gain
            self._cmd_vel_gain = self.vel_gain
            self._cmd_max_velocity = self.max_joint_velocity
        
        # Keep backward compatibility
        self.target_position = target_xyz
        
        print(f"[CTRL] Started motion to {target_xyz}, target_joints={self.target_joints}")

    def follow_trajectory(self, waypoints: list[Waypoint]) -> None:
        """Start following a precomputed joint-space trajectory."""
        self.last_motion_error = None
        self._trajectory = waypoints
        self._trajectory_index = 0
        self._trajectory_start_time = time.time()
        self.executing = True
        self.target_joints = None
        self.target_position = None
        self._settle_counter = 0

    def update_trajectory(self, current_state: ArmState) -> bool:
        """Update trajectory execution; returns True when complete."""
        if self._trajectory is None:
            return False
        if current_state is None:
            return False

        elapsed = time.time() - self._trajectory_start_time
        prev_index = self._trajectory_index
        while (
            self._trajectory_index < len(self._trajectory)
            and self._trajectory[self._trajectory_index].time <= elapsed
        ):
            self._trajectory_index += 1
        if self._trajectory_index < len(self._trajectory) and self._trajectory_index == prev_index:
            # Keep deterministic progress in fast simulation/test loops.
            self._trajectory_index += 1

        if self._trajectory_index >= len(self._trajectory):
            final_waypoint = self._trajectory[-1]
            try:
                p.setJointMotorControlArray(
                    bodyIndex=self.sim.robot_id,
                    jointIndices=self.joint_indices,
                    controlMode=p.POSITION_CONTROL,
                    targetPositions=final_waypoint.joint_positions.tolist(),
                    forces=[self._cmd_force] * len(self.joint_indices),
                    positionGains=[self._cmd_pos_gain] * len(self.joint_indices),
                    velocityGains=[self._cmd_vel_gain] * len(self.joint_indices),
                    maxVelocities=[self._cmd_max_velocity] * len(self.joint_indices),
                )
            except TypeError:
                p.setJointMotorControlArray(
                    bodyIndex=self.sim.robot_id,
                    jointIndices=self.joint_indices,
                    controlMode=p.POSITION_CONTROL,
                    targetPositions=final_waypoint.joint_positions.tolist(),
                    forces=[self._cmd_force] * len(self.joint_indices),
                    positionGains=[self._cmd_pos_gain] * len(self.joint_indices),
                    velocityGains=[self._cmd_vel_gain] * len(self.joint_indices),
                )
            except Exception as exc:
                logger.error("[CTRL] Trajectory final hold failed: %s", exc)
                self._trajectory = None
                self.executing = False
                return False
            self._apply_kinematic_joint_state(final_waypoint.joint_positions)

            current_state = self.sim.get_arm_state()
            current_joints = np.array(
                [
                    current_state.joint_positions[i]
                    for i in range(len(self.joint_indices))
                ]
            )
            error = np.linalg.norm(current_joints - final_waypoint.joint_positions)
            if error < self.tolerance_rad:
                self._settle_counter += 1
                if self._settle_counter >= self.settle_frames_required:
                    self._trajectory = None
                    self.executing = False
                    self._settle_counter = 0
                    return True
            else:
                self._settle_counter = 0
            return False

        waypoint = self._trajectory[self._trajectory_index]
        try:
            p.setJointMotorControlArray(
                bodyIndex=self.sim.robot_id,
                jointIndices=self.joint_indices,
                controlMode=p.POSITION_CONTROL,
                targetPositions=waypoint.joint_positions.tolist(),
                forces=[self._cmd_force] * len(self.joint_indices),
                positionGains=[self._cmd_pos_gain] * len(self.joint_indices),
                velocityGains=[self._cmd_vel_gain] * len(self.joint_indices),
                maxVelocities=[self._cmd_max_velocity] * len(self.joint_indices),
            )
        except TypeError:
            p.setJointMotorControlArray(
                bodyIndex=self.sim.robot_id,
                jointIndices=self.joint_indices,
                controlMode=p.POSITION_CONTROL,
                targetPositions=waypoint.joint_positions.tolist(),
                forces=[self._cmd_force] * len(self.joint_indices),
                positionGains=[self._cmd_pos_gain] * len(self.joint_indices),
                velocityGains=[self._cmd_vel_gain] * len(self.joint_indices),
            )
        except Exception as exc:
            logger.error("[CTRL] Trajectory update failed: %s", exc)
            self._trajectory = None
            self.executing = False
            return False
        self._apply_kinematic_joint_state(waypoint.joint_positions)

        return False

    def move_to_position_smooth(self, target_cart: np.ndarray, duration: float = 2.0) -> None:
        """Move to Cartesian target with smooth interpolated trajectory."""
        current_cart = self.get_end_effector_position()
        if current_cart is None:
            self.move_to_position(target_cart)
            return

        timestep = 1.0 / 60.0
        num_waypoints = max(2, int(duration / timestep))
        interp = TrajectoryInterpolator(duration=duration, timestep=timestep)
        rest_pose = [
            float(v)
            for v in self.sim.get_arm_state().joint_positions[: len(self.joint_indices)]
        ]
        try:
            waypoints = interp.interpolate_cartesian(
                robot_id=self.sim.robot_id,
                ee_link_index=self.ee_link_index,
                joint_count=len(self.joint_indices),
                start_cart=np.array(current_cart, dtype=float),
                end_cart=np.array(target_cart, dtype=float),
                num_waypoints=num_waypoints,
                arm_joint_indices=self.joint_indices,
                rest_pose=rest_pose,
            )
            self.last_ik_orientation = interp.last_orientation
            self.last_ik_orientation_offsets = interp.last_orientation_offsets
        except IKOutOfLimitsError as exc:
            print(f"[CTRL-IK] IK out of limits for target {target_cart}: {exc}")
            self.last_motion_error = "ik_out_of_limits"
            self.stop()
            return
        self.follow_trajectory(waypoints)
    
    def update(self, current_state: ArmState) -> bool:
        """
        Apply motor commands and check convergence.
        
        Returns:
            True if motion complete (settled)
            False if still executing OR not started OR failed
        """
        # Trajectory mode
        if self._trajectory is not None:
            return self.update_trajectory(current_state)

        # Not executing → not complete
        if not self.executing:
            return False
        
        # No target → error state → not complete
        if self.target_joints is None:
            print("[CTRL] ERROR: update() called but no target set")
            self.executing = False
            return False
        
        if current_state is None:
            print("[CTRL] ERROR: No arm state available")
            return False
        
        # Apply motor control with forces
        try:
            p.setJointMotorControlArray(
                bodyIndex=self.sim.robot_id,
                jointIndices=self.joint_indices,
                controlMode=p.POSITION_CONTROL,
                targetPositions=self.target_joints.tolist(),
                forces=[self._cmd_force] * len(self.joint_indices),
                positionGains=[self._cmd_pos_gain] * len(self.joint_indices),
                velocityGains=[self._cmd_vel_gain] * len(self.joint_indices),
                maxVelocities=[self._cmd_max_velocity] * len(self.joint_indices),
            )
        except TypeError:
            p.setJointMotorControlArray(
                bodyIndex=self.sim.robot_id,
                jointIndices=self.joint_indices,
                controlMode=p.POSITION_CONTROL,
                targetPositions=self.target_joints.tolist(),
                forces=[self._cmd_force] * len(self.joint_indices),
                positionGains=[self._cmd_pos_gain] * len(self.joint_indices),
                velocityGains=[self._cmd_vel_gain] * len(self.joint_indices),
            )
        self._apply_kinematic_joint_state(self.target_joints)
        
        # Compute error
        current_state = self.sim.get_arm_state()
        current_joints = np.array([current_state.joint_positions[i] for i in range(len(self.joint_indices))])
        error = np.linalg.norm(current_joints - self.target_joints)
        
        # Diagnostic logging (every N frames)
        if hasattr(self, '_frame_counter'):
            self._frame_counter += 1
        else:
            self._frame_counter = 0
        
        debug_config = self.config.get('debug', {})
        diag_log_every_n = debug_config.get('diag_log_every_n_frames', 120)
        verbose_controller = debug_config.get('verbose_controller', False)

        if verbose_controller and self._frame_counter % diag_log_every_n == 0:
            j0_cur = current_joints[0] if len(current_joints) > 0 else 0.0
            j0_tgt = self.target_joints[0] if len(self.target_joints) > 0 else 0.0
            print(f"[CTRL-DIAG] j0: cur={j0_cur:.4f} tgt={j0_tgt:.4f} diff={abs(j0_cur-j0_tgt):.4f}, error_norm={error:.4f}")
        
        # Check convergence with settle logic
        if error < self.tolerance_rad:
            self._settle_counter += 1
            
            if self._settle_counter >= self.settle_frames_required:
                print(f"[CTRL] Motion complete (error={error:.4f})")
                self.executing = False
                self.target_joints = None
                return True  # Complete!
        else:
            self._settle_counter = 0  # Reset if error increases
        
        return False  # Still executing

    def _apply_kinematic_joint_state(self, joint_positions: np.ndarray) -> None:
        """Keep the PyBullet sim stable by applying commanded joint states."""
        for joint_idx, joint_pos in zip(self.joint_indices, joint_positions):
            p.resetJointState(
                self.sim.robot_id,
                joint_idx,
                float(joint_pos),
                physicsClientId=self.sim.client,
            )
    
    def _compute_ik(self, target_xyz: np.ndarray):
        """Compute inverse kinematics using discovered EE link"""
        print(f"[CTRL-IK] Computing IK for target: {target_xyz}")
        try:
            arm_state = self.sim.get_arm_state()
            rest_pose = None
            if arm_state is not None:
                rest_pose = [
                    float(v)
                    for v in arm_state.joint_positions[: len(self.joint_indices)]
                ]
            lower, upper, ranges, rest = get_ik_limits(
                self.sim.robot_id,
                self.joint_indices,
                rest_pose=rest_pose,
            )
            ik_result, orientation, offsets, _ = calculate_limited_tool_down_ik(
                robot_id=self.sim.robot_id,
                ee_link_index=self.ee_link_index,
                desired_link7_position=target_xyz.tolist(),
                lower=lower,
                upper=upper,
                ranges=ranges,
                rest=rest,
                joint_count=len(self.joint_indices),
            )
            self.last_ik_orientation = orientation
            self.last_ik_orientation_offsets = offsets
            
            if ik_result:
                n = len(self.joint_indices)
                print(
                    f"[CTRL-IK] IK solution ({n} joints, "
                    f"orientation_offsets={offsets}): {ik_result[:n]}"
                )
                return ik_result
            else:
                print("[CTRL-IK] IK returned empty result")
                return None
        except IKOutOfLimitsError as e:
            print(f"[CTRL-IK] IK out of limits: {e}")
            self.last_motion_error = "ik_out_of_limits"
            return None
        except Exception as e:
            print(f"[CTRL-IK] IK failed: {e}")
            return None
    
    def stop(self):
        """Stop current motion."""
        self.executing = False
        self.target_position = None
        self.target_joints = None
        self._trajectory = None
        self._trajectory_index = 0
        self._trajectory_start_time = 0.0
        self._settle_counter = 0
    
    def is_executing(self) -> bool:
        """Check if motion is in progress."""
        return self.executing

    def get_end_effector_position(self) -> Optional[np.ndarray]:
        """Get current end-effector position."""
        arm = self.sim.get_arm_state()
        if arm is None:
            return None
        return arm.ee_position

    def check_divergence(self) -> bool:
        """Detect if physics has diverged (NaN positions, inf forces)."""
        if self.sim is None or self.sim.robot_id is None:
            return False

        for joint_idx in self.joint_indices:
            joint_state = p.getJointState(self.sim.robot_id, joint_idx)
            pos = joint_state[0]
            motor_torque = joint_state[3]
            if math.isnan(pos) or math.isinf(pos):
                return True
            if math.isnan(motor_torque) or math.isinf(motor_torque):
                return True
        return False

    def divergence_state_dump(self) -> dict:
        """Structured state dump for diagnostics/logging when divergence occurs."""
        dump = {
            "robot_id": self.sim.robot_id if self.sim else None,
            "executing": self.executing,
            "target_joints": self.target_joints.tolist() if isinstance(self.target_joints, np.ndarray) else None,
            "joint_states": [],
        }
        if self.sim is None or self.sim.robot_id is None:
            return dump

        for joint_idx in self.joint_indices:
            try:
                pos, vel, _, torque = p.getJointState(self.sim.robot_id, joint_idx)
                dump["joint_states"].append(
                    {
                        "joint_idx": joint_idx,
                        "position": float(pos),
                        "velocity": float(vel),
                        "torque": float(torque),
                    }
                )
            except Exception as exc:
                logger.error("[CTRL] Failed to read joint state for dump: joint=%s err=%s", joint_idx, exc)
                dump["joint_states"].append(
                    {"joint_idx": joint_idx, "error": str(exc)}
                )
        return dump
