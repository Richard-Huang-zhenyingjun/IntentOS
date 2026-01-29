"""
Selection state tracker - dwell-to-lock with stability.
Week 3: Hover → dwell → lock mechanism (paper's stable selection stage).
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SelectionState:
    """
    Current selection state.
    
    Attributes:
        current_hover_id: Object being hovered (may not be locked)
        locked_id: Object locked as target (stable selection)
        hover_frames: Consecutive frames hovering current object
        no_hit_frames: Consecutive frames with no hit (for unlock)
        locked: Whether selection is locked
    """
    current_hover_id: Optional[int] = None
    locked_id: Optional[int] = None
    hover_frames: int = 0
    no_hit_frames: int = 0
    locked: bool = False
    
    def is_locked(self) -> bool:
        """Check if target is locked."""
        return self.locked and self.locked_id is not None
    
    def get_target(self) -> Optional[int]:
        """Get current target (locked if available, else hover)."""
        return self.locked_id if self.locked else self.current_hover_id
    
    def reset(self) -> None:
        """Clear all selection state."""
        self.current_hover_id = None
        self.locked_id = None
        self.hover_frames = 0
        self.no_hit_frames = 0
        self.locked = False


class SelectionTracker:
    """
    Tracks selection state with dwell-to-lock logic.
    
    Paper-aligned behavior:
    1. User hovers over object for N frames → locks
    2. Lock persists until no-hit for M frames → unlocks
    3. Manual unlock available (U key)
    """
    
    def __init__(self, dwell_frames: int = 18, unlock_grace_frames: int = 10):
        """
        Initialize selection tracker.
        
        Args:
            dwell_frames: Frames to hover before lock (~0.6s at 30fps)
            unlock_grace_frames: Frames of no-hit before unlock (~0.3s)
        """
        self.dwell_frames = dwell_frames
        self.unlock_grace_frames = unlock_grace_frames
        self.state = SelectionState()
        self._is_forced_lock = False  # Phase 2: Track forced lock state
    
    def update(self, hit_object_id: Optional[int]) -> SelectionState:
        """
        Update selection state based on ray hit.
        
        Args:
            hit_object_id: Object ID from ray test, or None
            
        Returns:
            Updated SelectionState
        """
        # Phase 2: FORCED LOCKS - Never subject to auto-unlock
        if self.state.locked and self._is_forced_lock:
            return self.state  # Early return - forced locks never auto-unlock
        
        # NORMAL LOCKS: Continue with existing unlock logic
        if self.state.locked:
            if hit_object_id is None or hit_object_id != self.state.locked_id:
                self.state.no_hit_frames += 1
                if self.state.no_hit_frames >= self.unlock_grace_frames:
                    self._unlock()
            else:
                self.state.no_hit_frames = 0  # Reset grace counter
            
            return self.state
        
        # Not locked: update hover state
        if hit_object_id is None:
            # No hit: clear hover
            self.state.current_hover_id = None
            self.state.hover_frames = 0
        elif hit_object_id == self.state.current_hover_id:
            # Same object: increment hover
            self.state.hover_frames += 1
            
            # Check for lock condition
            if self.state.hover_frames >= self.dwell_frames:
                self._lock(hit_object_id)
        else:
            # Different object: reset hover
            self.state.current_hover_id = hit_object_id
            self.state.hover_frames = 1
        
        return self.state
    
    def _lock(self, object_id: int) -> None:
        """Lock target object."""
        self.state.locked_id = object_id
        self.state.locked = True
        self.state.no_hit_frames = 0
        print(f"🔒 Target locked: object {object_id}")
    
    def _unlock(self) -> None:
        """Unlock target object."""
        if self.state.locked_id is not None:
            print(f"🔓 Target unlocked: object {self.state.locked_id}")
        self.state.locked_id = None
        self.state.locked = False
        self.state.no_hit_frames = 0
        # Phase 2: Clear forced lock flag when unlocking
        self._is_forced_lock = False
    
    def manual_unlock(self) -> None:
        """Manually unlock current target (U key)."""
        if self.state.locked:
            self._unlock()
            self.state.current_hover_id = None
            self.state.hover_frames = 0
    
    def clear_forced_lock(self) -> None:
        """
        Phase 2: Manually clear forced lock (for U key or explicit unlock).
        
        This method ensures forced locks can be properly cleared.
        """
        if self._is_forced_lock:
            self._unlock()
            self._is_forced_lock = False
            print(f"[SELECTOR] Forced lock cleared")
    
    def force_lock(self, object_id: int) -> None:
        """
        STEP 2: Force lock a target (diagnostic hack).
        
        Bypasses normal selection pipeline to test proposal → confirm → execute.
        Phase 2: Marks lock as forced to prevent auto-unlock.
        """
        self._lock(object_id)
        self._is_forced_lock = True  # Phase 2: Mark as forced lock
        self.state.current_hover_id = object_id
        self.state.hover_frames = self.dwell_frames  # Set to locked threshold
        print(f"[SELECTOR] Forced lock applied to object {object_id}")
    
    def get_state(self) -> SelectionState:
        """Get current selection state."""
        return self.state

