"""World state snapshot - arm + object state combined."""

from dataclasses import dataclass
from typing import Optional
import numpy as np
from src.robot.simulator import ArmState, ObjectState


@dataclass
class WorldState:
    """Complete world state snapshot."""
    # Arm
    arm: Optional[ArmState]
    
    # Object
    object: Optional[ObjectState]
    target_id: Optional[int]
    
    # Grasp
    holding: bool
    attached_id: Optional[int]
    
    @property
    def ee_position(self) -> Optional[np.ndarray]:
        """Get end effector position."""
        return self.arm.ee_position if self.arm else None
    
    @property
    def object_position(self) -> Optional[np.ndarray]:
        """Get object position."""
        return self.object.position if self.object and self.object.visible else None
    
    def distance_to_object(self) -> Optional[float]:
        """Compute distance from EE to object."""
        if self.ee_position is None or self.object_position is None:
            return None
        return np.linalg.norm(self.ee_position - self.object_position)

