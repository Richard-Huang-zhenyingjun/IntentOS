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
        
        # Motion parameters
        self.max_joint_velocity = config.get('max_joint_vel_rad_s', 2.5)
        self.position_gain = config.get('position_gain', 0.3)
        self.settle_threshold = config.get('settle_threshold', 0.01)
        
        # Execution state
        self.target_position: Optional[np.ndarray] = None
        self.executing = False
    
    def move_to_position(self, target_xyz: np.ndarray):
        """Start motion to target 3D position."""
        self.target_position = target_xyz
        self.executing = True
        print(f"[CTRL] → Moving to {target_xyz}")
    
    def update(self, current_state: ArmState) -> bool:
        """Update controller, returns True if motion complete."""
        if not self.executing:
            return True
        
        if self.target_position is None:
            return True
        
        # Compute IK
        target_joints = self._compute_ik(self.target_position)
        if target_joints is None:
            print("[CTRL] IK failed")
            self.executing = False
            return True
        
        # Apply joint control
        p.setJointMotorControlArray(
            bodyIndex=self.sim.robot_id,
            jointIndices=self.sim.joint_indices,
            controlMode=p.POSITION_CONTROL,
            targetPositions=target_joints,
            positionGains=[self.position_gain] * len(self.sim.joint_indices),
            maxVelocities=[self.max_joint_velocity] * len(self.sim.joint_indices)
        )
        
        # Check if settled
        error = np.linalg.norm(target_joints - current_state.joint_positions)
        if error < self.settle_threshold:
            print(f"[CTRL] ✓ Motion complete (error={error:.4f})")
            self.executing = False
            return True
        
        return False
    
    def _compute_ik(self, target_xyz: np.ndarray) -> Optional[np.ndarray]:
        """Compute IK for target position."""
        try:
            # PyBullet IK
            joint_poses = p.calculateInverseKinematics(
                bodyIndex=self.sim.robot_id,
                endEffectorLinkIndex=self.sim.ee_link_index,
                targetPosition=target_xyz.tolist(),
                maxNumIterations=100,
                residualThreshold=1e-5
            )
            return np.array(joint_poses[:7])  # First 7 joints
        except Exception as e:
            print(f"[CTRL] IK error: {e}")
            return None
    
    def stop(self):
        """Stop current motion."""
        self.executing = False
        self.target_position = None
    
    def is_executing(self) -> bool:
        """Check if motion is in progress."""
        return self.executing

