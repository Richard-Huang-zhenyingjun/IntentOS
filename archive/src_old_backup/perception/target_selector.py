"""
Target selector - cursor to object selection pipeline.
Week 3: Cursor → ray test → dwell-to-lock → target object ID.
"""

from typing import Optional
from .selection_cursor import SelectionCursor
from .selection_state import SelectionTracker, SelectionState


class TargetSelector:
    """
    Selects target objects from cursor input.
    
    Pipeline:
    1. Receive SelectionCursor (gaze or mouse)
    2. Ray test against scene
    3. Track hover/lock state
    4. Output stable target ID
    """
    
    def __init__(self, sim, cfg: dict):
        """
        Initialize target selector.
        
        Args:
            sim: ArmSimulator instance (for ray testing)
            cfg: Configuration dict with selection parameters
        """
        self.sim = sim
        self.cfg = cfg
        
        # Selection tracking
        selection_cfg = cfg['selection']
        self.tracker = SelectionTracker(
            dwell_frames=selection_cfg['dwell_frames'],
            unlock_grace_frames=selection_cfg['unlock_grace_frames']
        )
        
        # Track cursor source for UI display
        self.last_cursor_source = "mouse"
    
    def update(self, cursor: Optional[SelectionCursor]) -> SelectionState:
        """
        Update target selection from cursor.
        
        Args:
            cursor: Current cursor position (gaze or mouse)
            
        Returns:
            Updated SelectionState
        """
        if cursor is None:
            # No cursor: treat as no hit
            return self.tracker.update(None)
        
        # Track cursor source
        self.last_cursor_source = cursor.source
        
        # Ray test at cursor position
        hit_object_id = self.sim.ray_test_object(cursor.u, cursor.v)
        
        # Update selection state
        return self.tracker.update(hit_object_id)
    
    def manual_unlock(self) -> None:
        """Manually unlock current target (U key)."""
        self.tracker.manual_unlock()
    
    def clear_forced_lock(self) -> None:
        """
        Phase 2: Manually clear forced lock (for U key or explicit unlock).
        
        This method ensures forced locks can be properly cleared.
        """
        self.tracker.clear_forced_lock()
    
    def force_lock(self, object_id: int) -> None:
        """
        STEP 2: Force lock a target (diagnostic hack).
        
        Bypasses normal selection pipeline to test proposal → confirm → execute.
        """
        self.tracker.force_lock(object_id)
    
    def get_locked_target(self) -> Optional[int]:
        """Get locked target ID, or None if not locked."""
        state = self.tracker.get_state()
        return state.locked_id if state.locked else None
    
    def get_current_target(self) -> Optional[int]:
        """Get current target (locked or hover)."""
        return self.tracker.get_state().get_target()
    
    def is_locked(self) -> bool:
        """Check if target is currently locked."""
        return self.tracker.get_state().is_locked()
    
    @property
    def using_gaze(self) -> bool:
        """Check if last cursor was from gaze."""
        return self.last_cursor_source == "gaze"

