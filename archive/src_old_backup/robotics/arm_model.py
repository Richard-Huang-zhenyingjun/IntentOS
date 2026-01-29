"""
Robot arm model representation.
Stores joint metadata, limits, and end effector information.
Week 1: Read-only model loading from URDF.
"""

from dataclasses import dataclass
from typing import Dict, Any
import numpy as np
import pybullet as p
import pybullet_data


@dataclass
class ArmModel:
    """
    Immutable robot arm model.
    
    Attributes:
        body_id: PyBullet body ID
        joint_indices: List of controllable joint indices
        joint_lower: Lower joint limits (radians)
        joint_upper: Upper joint limits (radians)
        joint_names: Human-readable joint names
        ee_link_index: End effector link index
        ee_link_name: End effector link name
        num_joints: Total number of joints
    """
    body_id: int
    joint_indices: list[int]
    joint_lower: np.ndarray
    joint_upper: np.ndarray
    joint_names: list[str]
    ee_link_index: int
    ee_link_name: str
    
    @property
    def num_joints(self) -> int:
        """Number of controllable joints."""
        return len(self.joint_indices)
    
    @staticmethod
    def load(cfg: Dict[str, Any]) -> 'ArmModel':
        """
        Load robot arm from PyBullet's built-in URDF.
        
        Args:
            cfg: Robot configuration dict from robotics.yaml
            
        Returns:
            ArmModel instance with joint metadata
            
        Raises:
            ValueError: If URDF loading fails or no revolute joints found
        """
        # Set PyBullet data path for built-in models
        p.setAdditionalSearchPath(pybullet_data.getDataPath())
        
        # Load URDF
        urdf_path = cfg['model_name']
        base_pos = cfg['base_pose']['position']
        base_orn = cfg['base_pose']['orientation']
        
        body_id = p.loadURDF(
            urdf_path,
            basePosition=base_pos,
            baseOrientation=base_orn,
            useFixedBase=True,  # Robot base is fixed to world
            flags=p.URDF_USE_SELF_COLLISION
        )
        
        if body_id < 0:
            raise ValueError(f"Failed to load URDF: {urdf_path}")
        
        # Extract revolute joints (controllable)
        num_joints = p.getNumJoints(body_id)
        joint_indices = []
        joint_names = []
        joint_lower = []
        joint_upper = []
        
        for i in range(num_joints):
            joint_info = p.getJointInfo(body_id, i)
            joint_type = joint_info[2]
            
            # Only track revolute (type 0) and prismatic (type 1) joints
            if joint_type in [p.JOINT_REVOLUTE, p.JOINT_PRISMATIC]:
                joint_indices.append(i)
                joint_names.append(joint_info[1].decode('utf-8'))
                joint_lower.append(joint_info[8])   # lower limit
                joint_upper.append(joint_info[9])   # upper limit
        
        if not joint_indices:
            raise ValueError(f"No controllable joints found in {urdf_path}")
        
        # Find end effector link
        ee_link_name = cfg.get('ee_link_name', joint_names[-1])
        ee_link_index = joint_indices[-1]  # Default to last joint
        
        # Try to find exact match for EE link
        for i in range(num_joints):
            link_name = p.getJointInfo(body_id, i)[12].decode('utf-8')
            if link_name == ee_link_name:
                ee_link_index = i
                break
        
        print(f"✓ Loaded robot: {urdf_path}")
        print(f"  - {len(joint_indices)} controllable joints")
        print(f"  - Joint names: {', '.join(joint_names)}")
        print(f"  - End effector: link {ee_link_index} ({ee_link_name})")
        
        # Week 5: Apply default joint configuration if specified
        if 'default_joints' in cfg:
            default_q = cfg['default_joints']
            if len(default_q) == len(joint_indices):
                for idx, q_val in zip(joint_indices, default_q):
                    p.resetJointState(body_id, idx, q_val)
                print(f"  - Initialized to default pose: {default_q}")
        
        return ArmModel(
            body_id=body_id,
            joint_indices=joint_indices,
            joint_lower=np.array(joint_lower),
            joint_upper=np.array(joint_upper),
            joint_names=joint_names,
            ee_link_index=ee_link_index,
            ee_link_name=ee_link_name
        )
