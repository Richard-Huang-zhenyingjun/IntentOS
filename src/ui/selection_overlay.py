"""
Selection overlay - visual feedback for gaze/mouse selection.
Week 3: Draw target markers, selection state, and action proposals.
"""

from typing import Optional, List, Tuple
import pybullet as p
import numpy as np
from utils.safe_pybullet import safe_debug_text


class SelectionOverlay:
    """
    Visual feedback for target selection and action proposals.
    
    Uses PyBullet debug drawing (addUserDebugText, addUserDebugLine).
    """
    
    def __init__(self):
        """Initialize overlay (tracks debug item IDs for reuse)."""
        # STEP 0 FIX: Store IDs for reuse instead of clearing/recreating
        self.hover_indicator_id: Optional[int] = None
        self.lock_indicator_id: Optional[int] = None
        self.proposal_text_id: Optional[int] = None
        self.available_actions_id: Optional[int] = None
    
    def clear(self) -> None:
        """Remove all debug items (cleanup on reset)."""
        # STEP 0 FIX: Remove items if they exist
        for item_id in [self.hover_indicator_id, self.lock_indicator_id, 
                        self.proposal_text_id, self.available_actions_id]:
            if item_id is not None:
                try:
                    p.removeUserDebugItem(item_id)
                except:
                    pass
        self.hover_indicator_id = None
        self.lock_indicator_id = None
        self.proposal_text_id = None
        self.available_actions_id = None
    
    def draw_hover_indicator(self, pose: Optional[Tuple[List[float], List[float]]], hover_frames: int, dwell_frames: int) -> None:
        """
        Draw hover indicator above object.
        
        Args:
            pose: (position, orientation) tuple - ALREADY VALIDATED, or None to clear
            hover_frames: Current hover frame count
            dwell_frames: Required frames to lock
        """
        # STEP 0 FIX: Clear lock indicator when showing hover
        if self.lock_indicator_id is not None:
            try:
                p.removeUserDebugItem(self.lock_indicator_id)
            except:
                pass
            self.lock_indicator_id = None
        
        if pose is None:
            # STEP 0 FIX: Clear hover indicator if no object
            if self.hover_indicator_id is not None:
                try:
                    p.removeUserDebugItem(self.hover_indicator_id)
                except:
                    pass
                self.hover_indicator_id = None
            return
        
        # Render using validated pose (no PyBullet calls with IDs)
        pos, _ = pose
        text_pos = [pos[0], pos[1], pos[2] + 0.15]
        
        progress = min(1.0, hover_frames / dwell_frames)
        text = f"HOVER {int(progress * 100)}%"
        
        # STEP B: Use safe debug text wrapper
        self.hover_indicator_id = safe_debug_text(
            text=text,
            position=text_pos,
            color=(1.0, 1.0, 0.0),  # Yellow
            size=1.2,
            lifetime=0,
            replace_id=self.hover_indicator_id
        )
    
    def draw_lock_indicator(self, pose: Optional[Tuple[List[float], List[float]]]) -> None:
        """
        Draw lock indicator above target object.
        
        Args:
            pose: (position, orientation) tuple - ALREADY VALIDATED, or None to clear
        """
        # STEP 0 FIX: Clear hover indicator when showing lock
        if self.hover_indicator_id is not None:
            try:
                p.removeUserDebugItem(self.hover_indicator_id)
            except:
                pass
            self.hover_indicator_id = None
        
        if pose is None:
            # STEP 0 FIX: Clear lock indicator if no object
            if self.lock_indicator_id is not None:
                try:
                    p.removeUserDebugItem(self.lock_indicator_id)
                except:
                    pass
                self.lock_indicator_id = None
            return
        
        # Render using validated pose (no PyBullet calls with IDs)
        pos, _ = pose
        text_pos = [pos[0], pos[1], pos[2] + 0.15]
        
        # STEP B: Use safe debug text wrapper
        self.lock_indicator_id = safe_debug_text(
            text="🔒 LOCKED TARGET",
            position=text_pos,
            color=(0.0, 1.0, 0.0),  # Green
            size=1.5,
            lifetime=0,
            replace_id=self.lock_indicator_id
        )
    
    def draw_proposal_text(self, text: str, position: List[float] = [0.0, 0.0, 0.8]) -> None:
        """
        Draw action proposal text in world space.
        
        Args:
            text: Proposal text (e.g., "Proposed: MOVE_ARM_UP")
            position: 3D world position for text
        """
        # STEP B: Use safe debug text wrapper
        self.proposal_text_id = safe_debug_text(
            text=text,
            position=position,
            color=(0.0, 0.8, 1.0),  # Cyan
            size=1.8,
            lifetime=0,
            replace_id=self.proposal_text_id
        )
    
    def draw_available_actions(self, actions: List[str], position: List[float] = [0.0, 0.0, 0.7]) -> None:
        """
        Draw available actions list.
        
        Args:
            actions: List of action names
            position: 3D world position for text
        """
        if not actions:
            text = "Available: NONE"
        else:
            text = f"Available: {', '.join(actions)}"
        
        # STEP B: Use safe debug text wrapper
        self.available_actions_id = safe_debug_text(
            text=text,
            position=position,
            color=(1.0, 1.0, 1.0),  # White
            size=1.3,
            lifetime=0,
            replace_id=self.available_actions_id
        )

