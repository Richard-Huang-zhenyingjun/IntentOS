"""Robot motion controller."""

import numpy as np
import pybullet as p
from typing import Optional
from src.robot.simulator import RobotSimulator, ArmState


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
        
        print(f"[CTRL] Initialized with {len(self.joint_indices)} joints")
        print(f"[CTRL] max_force={self.max_force}, tolerance={self.tolerance_rad}")
    
    def move_to_position(self, target_xyz: np.ndarray):
        """Start moving to target position (does NOT wait for completion)"""
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
        
        # Keep backward compatibility
        self.target_position = target_xyz
        
        print(f"[CTRL] Started motion to {target_xyz}, target_joints={self.target_joints}")
    
    def update(self, current_state: ArmState) -> bool:
        """
        Apply motor commands and check convergence.
        
        Returns:
            True if motion complete (settled)
            False if still executing OR not started OR failed
        """
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
        p.setJointMotorControlArray(
            bodyIndex=self.sim.robot_id,
            jointIndices=self.joint_indices,
            controlMode=p.POSITION_CONTROL,
            targetPositions=self.target_joints.tolist(),
            forces=[self.max_force] * len(self.joint_indices),
            positionGains=[self.pos_gain] * len(self.joint_indices),
            velocityGains=[self.vel_gain] * len(self.joint_indices)
        )
        
        # Compute error
        current_joints = np.array([current_state.joint_positions[i] for i in range(len(self.joint_indices))])
        error = np.linalg.norm(current_joints - self.target_joints)
        
        # Diagnostic logging (every N frames)
        if hasattr(self, '_frame_counter'):
            self._frame_counter += 1
        else:
            self._frame_counter = 0
        
        debug_config = self.config.get('debug', {})
        diag_log_every_n = debug_config.get('diag_log_every_n_frames', 15)
        
        if self._frame_counter % diag_log_every_n == 0:
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
    
    def _compute_ik(self, target_xyz: np.ndarray):
        """Compute inverse kinematics using discovered EE link"""
        print(f"[CTRL-IK] Computing IK for target: {target_xyz}")
        try:
            ik_result = p.calculateInverseKinematics(
                bodyIndex=self.sim.robot_id,
                endEffectorLinkIndex=self.ee_link_index,  # Use discovered index
                targetPosition=target_xyz.tolist(),
                maxNumIterations=100,
                residualThreshold=0.001
            )
            
            if ik_result:
                n = len(self.joint_indices)
                print(f"[CTRL-IK] IK solution ({n} joints): {ik_result[:n]}")
                return ik_result
            else:
                print("[CTRL-IK] IK returned empty result")
                return None
        except Exception as e:
            print(f"[CTRL-IK] IK failed: {e}")
            return None
    
    def stop(self):
        """Stop current motion."""
        self.executing = False
        self.target_position = None
        self.target_joints = None
        self._settle_counter = 0
    
    def is_executing(self) -> bool:
        """Check if motion is in progress."""
        return self.executing

