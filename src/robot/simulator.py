"""Robot simulator - PyBullet integration with robust URDF loading."""

import pybullet as p
import pybullet_data
import numpy as np
from typing import Optional, Tuple
from dataclasses import dataclass
import os
from src.robot.joint_discovery import (
    get_revolute_joint_indices,
    get_joint_name_map,
    guess_end_effector_link,
    print_joint_table,
    discover_gripper_joints,
)


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
    """PyBullet simulation wrapper with robust URDF loading."""
    
    def __init__(self, config: dict, use_gui: bool = True):
        self.config = config
        
        # Connect to PyBullet
        if use_gui:
            self.client = p.connect(p.GUI)
            print("[SIM] Connected to PyBullet GUI")
        else:
            self.client = p.connect(p.DIRECT)
            print("[SIM] Connected to PyBullet (headless)")
        
        # Set PyBullet data path
        p.setAdditionalSearchPath(pybullet_data.getDataPath())
        print(f"[SIM] PyBullet data path: {pybullet_data.getDataPath()}")
        
        # Physics setup
        p.setGravity(0, 0, -9.81)
        p.setRealTimeSimulation(0)  # Step manually
        
        # DIAGNOSTIC: Ensure real-time simulation is OFF
        # Note: getRealTimeSimulation() doesn't exist in PyBullet 3.25
        # We just set it to 0, so we know it's off
        print(f"[SIM-DIAG] Real-time simulation set to: 0 (manual stepping mode)")
        
        # Load plane
        print("[SIM] Loading plane...")
        self.plane_id = p.loadURDF("plane.urdf")
        print(f"[SIM] ✓ Plane loaded (id={self.plane_id})")
        
        # Load KUKA arm with error handling
        print("[SIM] Loading KUKA IIWA arm...")
        self.robot_id = self._load_robot()
        
        if self.robot_id < 0:
            raise RuntimeError("Failed to load robot arm!")
        
        print(f"[SIM] ✓ Robot loaded (id={self.robot_id})")
        
        # NEW: After robot loads, discover joints
        self.joint_indices = get_revolute_joint_indices(self.robot_id)
        self.joint_name_map = get_joint_name_map(self.robot_id)
        self.ee_link_index = guess_end_effector_link(self.robot_id, self.joint_indices)
        
        # Print diagnostic table (once)
        print_joint_table(self.robot_id)
        print(f"[SIM] Discovered {len(self.joint_indices)} revolute joints: {self.joint_indices}")
        print(f"[SIM] End effector link index: {self.ee_link_index}")
        gripper_joints = discover_gripper_joints(self.robot_id)
        if gripper_joints:
            print(f"[SIM] Discovered gripper joints: {gripper_joints}")
            self._tune_gripper_dynamics(gripper_joints)
        
        # Reset arm to home position
        self._reset_arm_position()
        
        # Spawn cube
        print("[SIM] Loading cube...")
        self.cube_id = self._load_cube()
        
        if self.cube_id < 0:
            raise RuntimeError("Failed to load cube!")
        
        print(f"[SIM] ✓ Cube loaded (id={self.cube_id})")
        
        # Step physics to settle
        for _ in range(100):
            p.stepSimulation()
        
        print(f"[SIM] ✓ Simulation ready")
        print(f"[SIM]   Robot: {self.robot_id}, Cube: {self.cube_id}")
    
    def _load_robot(self) -> int:
        """Load KUKA robot with multiple fallback paths."""
        
        # Try multiple URDF paths
        urdf_paths = [
            "models/kuka_iiwa/kuka_with_gripper.urdf",  # Local arm + gripper
            "models/kuka_iiwa/model.urdf",              # Local arm copy
            "kuka_iiwa/model.urdf",                    # Standard PyBullet data
            "kuka_iiwa7/model.urdf",                   # Alternative name
            os.path.join(pybullet_data.getDataPath(), "kuka_iiwa/model.urdf"),
        ]
        
        for urdf_path in urdf_paths:
            try:
                print(f"[SIM]   Trying: {urdf_path}")
                robot_id = p.loadURDF(
                    urdf_path,
                    basePosition=[0, 0, 0],
                    baseOrientation=[0, 0, 0, 1],
                    useFixedBase=True,
                    flags=p.URDF_USE_SELF_COLLISION
                )
                
                if robot_id >= 0:
                    print(f"[SIM]   ✓ Loaded from: {urdf_path}")
                    return robot_id
                    
            except Exception as e:
                print(f"[SIM]   ✗ Failed: {e}")
                continue
        
        # If all paths fail, return error
        print("[SIM] ✗ ERROR: Could not load robot from any path!")
        print("[SIM]   Available URDFs in PyBullet data:")
        data_path = pybullet_data.getDataPath()
        
        # List available URDFs
        if os.path.exists(data_path):
            for item in os.listdir(data_path):
                item_path = os.path.join(data_path, item)
                if os.path.isdir(item_path) and 'kuka' in item.lower():
                    print(f"[SIM]     - {item}/")
        
        return -1
    
    def _discover_arm_config(self):
        """Discover controllable joints and end effector link from loaded URDF.
        
        Returns:
            tuple: (joint_indices, ee_link_index)
        """
        print("[SIM] Discovering arm configuration from URDF...")
        
        # Find all revolute/prismatic joints (controllable)
        controllable_joints = []
        
        for j in range(self.num_joints):
            joint_info = p.getJointInfo(self.robot_id, j)
            joint_name = joint_info[1].decode('utf-8')
            joint_type = joint_info[2]
            
            # Joint types: REVOLUTE=0, PRISMATIC=1, FIXED=4
            if joint_type in [p.JOINT_REVOLUTE, p.JOINT_PRISMATIC]:
                controllable_joints.append(j)
                print(f"[SIM]     Joint {j}: {joint_name} (type={joint_type})")
        
        if len(controllable_joints) == 0:
            raise RuntimeError("No controllable joints found in URDF!")
        
        # For 7-DOF arms, take first 7 controllable joints
        joint_indices = controllable_joints[:7]
        
        # Find end effector link
        # Strategy: Look for link with "ee", "tool", "link_7", or use last controllable joint
        ee_link_index = None
        
        for j in range(self.num_joints):
            joint_info = p.getJointInfo(self.robot_id, j)
            link_name = joint_info[12].decode('utf-8')  # Child link name
            
            # Common EE link name patterns
            if any(pattern in link_name.lower() for pattern in ['ee', 'tool', 'link_7', 'flange']):
                ee_link_index = j
                print(f"[SIM]     Found EE link: {link_name} at index {j}")
                break
        
        # Fallback: Use last controllable joint's link
        if ee_link_index is None:
            ee_link_index = joint_indices[-1]
            joint_info = p.getJointInfo(self.robot_id, ee_link_index)
            link_name = joint_info[12].decode('utf-8')
            print(f"[SIM]     Using last joint link as EE: {link_name} at index {ee_link_index}")
        
        # Validate EE link position
        ee_state = p.getLinkState(self.robot_id, ee_link_index)
        ee_pos = ee_state[4]  # World position
        print(f"[SIM]     EE initial position: {ee_pos}")
        
        return joint_indices, ee_link_index
    
    def _load_cube(self) -> int:
        """Load cube with fallback to simple cube."""
        
        # Get cube config
        cube_urdf = self.config.get('cube_urdf', 'cube_small.urdf')
        cube_pos = self.config.get('cube_position', [0.5, 0, 0.65])
        
        # Try to load configured cube
        try:
            print(f"[SIM]   Trying: {cube_urdf}")
            cube_id = p.loadURDF(
                cube_urdf,
                basePosition=cube_pos,
                baseOrientation=[0, 0, 0, 1]
            )
            
            if cube_id >= 0:
                print(f"[SIM]   ✓ Loaded: {cube_urdf}")
                return cube_id
                
        except Exception as e:
            print(f"[SIM]   ✗ Failed to load {cube_urdf}: {e}")
        
        # Fallback: Create simple cube programmatically
        print("[SIM]   Creating simple cube...")
        
        # Create collision shape
        collision_shape = p.createCollisionShape(
            p.GEOM_BOX,
            halfExtents=[0.05, 0.05, 0.05]  # 10cm cube
        )
        
        # Create visual shape
        visual_shape = p.createVisualShape(
            p.GEOM_BOX,
            halfExtents=[0.05, 0.05, 0.05],
            rgbaColor=[1, 0, 0, 1]  # Red cube
        )
        
        # Create multi-body
        cube_id = p.createMultiBody(
            baseMass=0.1,
            baseCollisionShapeIndex=collision_shape,
            baseVisualShapeIndex=visual_shape,
            basePosition=cube_pos,
            baseOrientation=[0, 0, 0, 1]
        )
        
        print(f"[SIM]   ✓ Created simple cube (id={cube_id})")
        return cube_id

    def _tune_gripper_dynamics(self, gripper_joints: dict[str, int]):
        """Apply high-friction compliant contact tuning for gripper links."""
        for joint_name, joint_idx in gripper_joints.items():
            try:
                p.changeDynamics(
                    self.robot_id,
                    joint_idx,
                    lateralFriction=2.0,
                    spinningFriction=0.1,
                    rollingFriction=0.05,
                    restitution=0.0,
                    contactStiffness=100000,
                    contactDamping=100,
                )
            except TypeError:
                p.changeDynamics(
                    self.robot_id,
                    joint_idx,
                    lateralFriction=2.0,
                    spinningFriction=0.1,
                    rollingFriction=0.05,
                    restitution=0.0,
                )
            except Exception as exc:
                print(f"[SIM] WARNING: gripper tuning failed for {joint_name}: {exc}")

        # Gripper base contact tuning.
        for i in range(p.getNumJoints(self.robot_id)):
            info = p.getJointInfo(self.robot_id, i)
            if info[1].decode("utf-8") == "gripper_attach":
                try:
                    p.changeDynamics(
                        self.robot_id,
                        i,
                        lateralFriction=1.5,
                        spinningFriction=0.05,
                        rollingFriction=0.03,
                    )
                except Exception:
                    pass
                break
    
    def _reset_arm_position(self):
        """Reset arm to home position."""
        # Home position (all joints at 0 except slight elbow bend)
        home_positions = [0, 0, 0, -1.57, 0, 1.57, 0]  # Elbow down, wrist up
        
        for i, pos in enumerate(home_positions):
            if i < len(self.joint_indices):
                p.resetJointState(
                    self.robot_id,
                    self.joint_indices[i],
                    pos
                )
        
        print("[SIM]   Robot reset to home position")
    
    def step(self):
        """Step simulation forward."""
        p.stepSimulation()
        if not hasattr(self, '_step_count'):
            self._step_count = 0
        self._step_count += 1
        if self._step_count % 20 == 0:  # Print every 20 frames
            print(f"[SIM-DIAG] Physics stepped {self._step_count} times")
    
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
    
    def get_joint_indices(self) -> list[int]:
        """Get list of revolute joint indices."""
        return self.joint_indices
    
    def get_ee_link_index(self) -> int:
        """Get end effector link index."""
        return self.ee_link_index
    
    def close(self):
        """Disconnect from PyBullet."""
        p.disconnect(self.client)
        print("[SIM] Disconnected")
