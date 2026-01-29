"""Grasp controller - attach/detach with state tracking."""

import pybullet as p
from typing import Optional
from src.robot.simulator import RobotSimulator


class GraspController:
    """Manage object attachment with clear state tracking."""
    
    def __init__(self, sim: RobotSimulator):
        self.sim = sim
        
        # Grasp state
        self.holding = False
        self.attached_object_id: Optional[int] = None
        self.constraint_id: Optional[int] = None
    
    def attach(self, object_id: int) -> bool:
        """Attach object to end effector.
        
        Returns:
            True if successful, False otherwise
        """
        if self.holding:
            print(f"[GRASP] Already holding object {self.attached_object_id}")
            return False
        
        if not self.sim.is_valid_object(object_id):
            print(f"[GRASP] Invalid object {object_id}")
            return False
        
        try:
            # Create fixed constraint
            self.constraint_id = p.createConstraint(
                parentBodyUniqueId=self.sim.robot_id,
                parentLinkIndex=self.sim.ee_link_index,
                childBodyUniqueId=object_id,
                childLinkIndex=-1,
                jointType=p.JOINT_FIXED,
                jointAxis=[0, 0, 0],
                parentFramePosition=[0, 0, 0],
                childFramePosition=[0, 0, 0]
            )
            
            self.holding = True
            self.attached_object_id = object_id
            print(f"[GRASP] ✓ Attached object {object_id}")
            return True
            
        except Exception as e:
            print(f"[GRASP] Attach failed: {e}")
            return False
    
    def detach(self) -> bool:
        """Detach currently held object.
        
        Returns:
            True if successful, False otherwise
        """
        if not self.holding:
            print("[GRASP] Not holding anything")
            return False
        
        try:
            if self.constraint_id is not None:
                p.removeConstraint(self.constraint_id)
            
            print(f"[GRASP] ✓ Detached object {self.attached_object_id}")
            
            self.holding = False
            self.attached_object_id = None
            self.constraint_id = None
            return True
            
        except Exception as e:
            print(f"[GRASP] Detach failed: {e}")
            # Force clear state even if constraint removal failed
            self.holding = False
            self.attached_object_id = None
            self.constraint_id = None
            return False
    
    def is_holding(self) -> bool:
        """Check if holding an object."""
        return self.holding
    
    def get_attached_id(self) -> Optional[int]:
        """Get ID of attached object, or None."""
        return self.attached_object_id if self.holding else None

