"""
Grasp logic - object attachment/detachment using PyBullet constraints.
Week 6: Fixed constraint between end-effector and object.
"""

from typing import Optional
import numpy as np
import pybullet as p


def distance_3d(pos_a: np.ndarray, pos_b: np.ndarray) -> float:
    """Compute 3D Euclidean distance."""
    return np.linalg.norm(pos_a - pos_b)


class GraspLogic:
    """
    Manages object grasping using PyBullet constraints.
    
    Week 6: Uses fixed constraint to attach object to end-effector.
    Object follows gripper motion while attached.
    """
    
    def __init__(self, cfg: dict):
        """
        Initialize grasp logic.
        
        Args:
            cfg: Configuration dict
        """
        self.cfg = cfg
        self.constraint_id: Optional[int] = None
        self.held_object_id: Optional[int] = None
        
        # Config shortcuts
        self.attach_dist = cfg['grasp']['attach_dist_m']
        self.max_force = cfg['grasp']['constraint_max_force']
    
    def can_attach(self, world, sim) -> bool:
        """
        Check if object can be attached.
        
        Args:
            world: WorldModel instance
            sim: ArmSimulator instance
            
        Returns:
            True if attachment conditions met
        """
        # Already holding something?
        if self.held_object_id is not None:
            return False
        
        # Target object exists?
        if world.target_object_id is None:
            return False
        
        # Close enough?
        ee_pos = world.arm_state.ee_pos
        obj_pos = world.object_state.pos
        dist = distance_3d(ee_pos, obj_pos)
        
        if dist > self.attach_dist:
            return False
        
        return True
    
    def attach(self, sim, object_id: int) -> bool:
        """
        Attach object to end-effector using constraint.
        
        Args:
            sim: ArmSimulator instance
            object_id: Object to attach
            
        Returns:
            True if attachment succeeded
        """
        if self.constraint_id is not None:
            print("⚠️  Already holding object, cannot attach")
            return False
        
        try:
            # Create fixed constraint between EE and object
            self.constraint_id = p.createConstraint(
                parentBodyUniqueId=sim.robot.body_id,
                parentLinkIndex=sim.robot.ee_link_index,
                childBodyUniqueId=object_id,
                childLinkIndex=-1,  # Base of object
                jointType=p.JOINT_FIXED,
                jointAxis=[0, 0, 0],
                parentFramePosition=[0, 0, 0],
                childFramePosition=[0, 0, 0]
            )
            
            # Set constraint force
            p.changeConstraint(self.constraint_id, maxForce=self.max_force)
            
            self.held_object_id = object_id
            
            print(f"✓ Attached object {object_id} (constraint {self.constraint_id})")
            return True
            
        except Exception as e:
            print(f"⚠️  Attachment failed: {e}")
            return False
    
    def detach(self) -> bool:
        """
        Detach held object.
        
        Returns:
            True if detachment succeeded
        """
        if self.constraint_id is None:
            return False
        
        try:
            p.removeConstraint(self.constraint_id)
            print(f"✓ Detached object {self.held_object_id} (constraint {self.constraint_id})")
            
            self.constraint_id = None
            self.held_object_id = None
            return True
            
        except Exception as e:
            print(f"⚠️  Detachment failed: {e}")
            return False
    
    def is_holding(self) -> bool:
        """Check if currently holding an object."""
        return self.held_object_id is not None
    
    def get_held_object_id(self) -> Optional[int]:
        """Get held object ID, or None."""
        return self.held_object_id
    
    def reset(self) -> None:
        """Reset grasp logic (detach if needed)."""
        if self.constraint_id is not None:
            self.detach()




