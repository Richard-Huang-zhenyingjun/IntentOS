"""Robot simulator - PyBullet integration."""

import pybullet as p
import pybullet_data
import numpy as np
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class ArmState:
    """Current arm state snapshot."""
    joint_positions: np.ndarray  # 7 joints
    ee_position: np.ndarray      # [x, y, z] end effector
    ee_orientation: np.ndarray   # quaternion [x, y, z, w]


@dataclass
class ObjectState:
    """Current object state snapshot."""
    position: np.ndarray         # [x, y, z]
    orientation: np.ndarray      # quaternion [x, y, z, w]
    visible: bool                # Is object still in world?


class RobotSimulator:
    """PyBullet simulation wrapper."""
    
    def __init__(self, config: dict, use_gui: bool = True):
        self.config = config
        
        # Connect to PyBullet
        if use_gui:
            self.client = p.connect(p.GUI)
        else:
            self.client = p.connect(p.DIRECT)
        
        p.setAdditionalSearchPath(pybullet_data.getDataPath())
        p.setGravity(0, 0, -9.81)
        
        # Load plane
        self.plane_id = p.loadURDF("plane.urdf")
        
        # Load KUKA arm
        self.robot_id = p.loadURDF(
            "kuka_iiwa/model.urdf",
            basePosition=[0, 0, 0],
            useFixedBase=True
        )
        
        # Get arm info
        self.num_joints = p.getNumJoints(self.robot_id)
        self.joint_indices = list(range(7))  # First 7 joints
        self.ee_link_index = 6  # End effector link
        
        # Spawn cube
        cube_urdf_path = config.get('cube_urdf', 'cube_small.urdf')
        self.cube_id = p.loadURDF(
            cube_urdf_path,
            basePosition=[0.5, 0, 0.65],
            baseOrientation=[0, 0, 0, 1]
        )
        
        print(f"[SIM] ✓ Initialized (robot={self.robot_id}, cube={self.cube_id})")
    
    def step(self):
        """Step simulation forward."""
        p.stepSimulation()
    
    def get_arm_state(self) -> Optional[ArmState]:
        """Read current arm state safely."""
        try:
            # Read joint states
            joint_states = p.getJointStates(self.robot_id, self.joint_indices)
            positions = np.array([s[0] for s in joint_states])
            
            # Read end effector state
            ee_state = p.getLinkState(
                self.robot_id,
                self.ee_link_index,
                computeForwardKinematics=True
            )
            ee_pos = np.array(ee_state[4])  # world position
            ee_orn = np.array(ee_state[5])  # world orientation
            
            return ArmState(
                joint_positions=positions,
                ee_position=ee_pos,
                ee_orientation=ee_orn
            )
        except Exception as e:
            print(f"[SIM] Error reading arm state: {e}")
            return None
    
    def get_object_state(self) -> Optional[ObjectState]:
        """Read current object state safely."""
        try:
            # Validate object still exists
            pos, orn = p.getBasePositionAndOrientation(self.cube_id)
            return ObjectState(
                position=np.array(pos),
                orientation=np.array(orn),
                visible=True
            )
        except Exception as e:
            # Object removed or invalid
            return ObjectState(
                position=np.zeros(3),
                orientation=np.array([0, 0, 0, 1]),
                visible=False
            )
    
    def is_valid_object(self, object_id: int) -> bool:
        """Check if object ID is valid."""
        try:
            p.getBodyInfo(object_id)
            return True
        except:
            return False
    
    def close(self):
        """Disconnect from PyBullet."""
        p.disconnect(self.client)

