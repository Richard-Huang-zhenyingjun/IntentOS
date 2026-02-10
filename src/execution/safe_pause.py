"""
Context-aware safe pause for re-authorization.

When the system needs to pause mid-task:
1. If holding an object → move to bin, release, then home
2. If not holding → just go home
3. Open gripper
4. Stop at safe home position

This prevents dropping objects mid-air when trust triggers re-auth.
"""
import logging
import numpy as np
from typing import Optional, List
from src.interfaces.primitive import Primitive, PrimitiveType

logger = logging.getLogger(__name__)


class SafePauseHelper:
    """
    Generates safe pause primitives based on current execution context.
    
    The orchestrator calls this when re-auth is triggered.
    Returns a list of primitives to execute before pausing.
    """
    
    def __init__(self, config: dict):
        clean_cfg = config.get('planning', {}).get('clean_table', {})
        self.safe_home = tuple(clean_cfg.get('safe_home_xyz', [0.3, 0.0, 0.8]))
        self.bin_zone_center = tuple(
            config.get('world', {}).get('messy_table', {}).get(
                'bin_zone_center', [0.4, 0.0, 0.75]
            )
        )
        self.bin_hover_height = clean_cfg.get('bin_hover_height', 0.12)
        self.bin_drop_offset = clean_cfg.get('bin_drop_height_offset', 0.03)
    
    def generate_safe_pause_primitives(
        self,
        is_grasping: bool,
        current_ee_position: Optional[tuple] = None,
    ) -> List[Primitive]:
        """
        Generate primitives for a safe pause.
        
        Args:
            is_grasping: Whether the gripper currently holds an object
            current_ee_position: Current end-effector position (for context)
            
        Returns:
            List of primitives to execute before transitioning to pause state
        """
        primitives = []
        
        if is_grasping:
            # Holding an object — safely deposit it
            logger.info("[SAFE_PAUSE] Generating deposit-then-home sequence")
            
            # Move to bin hover
            bin_hover = np.array([
                self.bin_zone_center[0],
                self.bin_zone_center[1],
                self.bin_zone_center[2] + self.bin_hover_height,
            ])
            primitives.append(Primitive(
                type=PrimitiveType.MOVE_TO,
                target_xyz=bin_hover,
                metadata={"description": "safe_pause: move to bin hover"},
            ))
            
            # Move to bin drop
            bin_drop = np.array([
                self.bin_zone_center[0],
                self.bin_zone_center[1],
                self.bin_zone_center[2] + self.bin_drop_offset,
            ])
            primitives.append(Primitive(
                type=PrimitiveType.MOVE_TO,
                target_xyz=bin_drop,
                metadata={"description": "safe_pause: move to bin drop"},
            ))
            
            # Release
            primitives.append(Primitive(
                type=PrimitiveType.RELEASE,
                target_xyz=bin_drop,
                metadata={"description": "safe_pause: release object"},
            ))
        else:
            logger.info("[SAFE_PAUSE] Generating home sequence (no object held)")
        
        # Always end at safe home
        safe_home_xyz = np.array(self.safe_home)
        primitives.append(Primitive(
            type=PrimitiveType.MOVE_TO,
            target_xyz=safe_home_xyz,
            metadata={"description": "safe_pause: return to home"},
        ))
        
        return primitives

