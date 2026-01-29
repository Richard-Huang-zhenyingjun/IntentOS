"""Scope Stability - N-frame confirmation before stable scope."""

from dataclasses import dataclass
from typing import Optional
from vision.tracking_schema import TrackedObject


@dataclass
class StableScopeResult:
    """
    Result of scope stability check
    
    Scope is only "stable" after being the primary focus for N consecutive frames
    """
    # Stable scope (only set if stable)
    scoped_track_id: Optional[str]
    scoped_label: Optional[str]
    scoped_bbox: Optional[tuple]
    scoped_confidence: float
    
    # Stability status
    stable: bool
    stability_counter: int
    required_frames: int
    
    # Current candidate (may not be stable yet)
    candidate_track_id: Optional[str]
    candidate_label: Optional[str]
    
    # Reason
    reason: str
    ambiguity: bool
    timestamp: float


class ScopeStability:
    """
    Require N consecutive frames of same primary focus before declaring stable scope
    
    This prevents flicker and rapid re-scoping as camera moves slightly
    
    Rules:
    - Same track_id for N frames → stable=True
    - Track changes → reset counter
    - Ambiguity → reset counter
    - Timeout → reset if unstable too long
    """
    
    def __init__(self, config: dict):
        self.config = config
        
        # Config
        self.required_frames = config.get('scope_stable_frames', 5)
        self.reset_threshold = config.get('scope_unstable_reset_threshold', 2)
        self.max_wait_seconds = config.get('max_stability_wait_seconds', 3.0)
        
        # State
        self.current_candidate_id: Optional[str] = None
        self.current_candidate_label: Optional[str] = None
        self.stability_counter = 0
        
        # Stable scope (only set when counter >= required)
        self.stable_scope_id: Optional[str] = None
        self.stable_scope_label: Optional[str] = None
        self.stable_scope_bbox: Optional[tuple] = None
        self.stable_scope_confidence = 0.0
        
        # Timing
        self.candidate_first_seen: Optional[float] = None
        self.stable_scope_locked_at: Optional[float] = None
    
    def step(self,
             primary: Optional[TrackedObject],
             ambiguity: bool,
             timestamp: float) -> StableScopeResult:
        """
        Update stability state with new primary focus
        
        Returns:
            StableScopeResult with stable=True only if counter >= required_frames
        """
        
        # Case 1: Ambiguity detected → reset everything
        if ambiguity:
            self._reset_candidate()
            self._clear_stable_scope()
            return StableScopeResult(
                scoped_track_id=None,
                scoped_label=None,
                scoped_bbox=None,
                scoped_confidence=0.0,
                stable=False,
                stability_counter=0,
                required_frames=self.required_frames,
                candidate_track_id=None,
                candidate_label=None,
                reason="ambiguity detected - waiting for clarity",
                ambiguity=True,
                timestamp=timestamp
            )
        
        # Case 2: No primary object → reset candidate
        if primary is None:
            self._reset_candidate()
            # But keep stable scope if we had one (graceful degradation)
            return StableScopeResult(
                scoped_track_id=self.stable_scope_id,
                scoped_label=self.stable_scope_label,
                scoped_bbox=self.stable_scope_bbox,
                scoped_confidence=self.stable_scope_confidence,
                stable=self.stable_scope_id is not None,
                stability_counter=0,
                required_frames=self.required_frames,
                candidate_track_id=None,
                candidate_label=None,
                reason="no primary focus - maintaining last stable scope" if self.stable_scope_id else "no primary focus",
                ambiguity=False,
                timestamp=timestamp
            )
        
        # Case 3: Primary exists
        primary_id = primary.track_id
        
        # Check if same as current candidate
        if primary_id == self.current_candidate_id:
            # Continue building stability
            self.stability_counter += 1
            
            # Check timeout
            if self.candidate_first_seen and (timestamp - self.candidate_first_seen) > self.max_wait_seconds:
                # Been waiting too long - reset
                self._reset_candidate()
                return StableScopeResult(
                    scoped_track_id=self.stable_scope_id,
                    scoped_label=self.stable_scope_label,
                    scoped_bbox=self.stable_scope_bbox,
                    scoped_confidence=self.stable_scope_confidence,
                    stable=self.stable_scope_id is not None,
                    stability_counter=0,
                    required_frames=self.required_frames,
                    candidate_track_id=None,
                    candidate_label=None,
                    reason="stability timeout - reset candidate",
                    ambiguity=False,
                    timestamp=timestamp
                )
            
            # Check if reached threshold
            if self.stability_counter >= self.required_frames:
                # Lock in stable scope
                self.stable_scope_id = primary_id
                self.stable_scope_label = primary.label
                self.stable_scope_bbox = primary.bbox
                self.stable_scope_confidence = primary.confidence
                self.stable_scope_locked_at = timestamp
                
                return StableScopeResult(
                    scoped_track_id=self.stable_scope_id,
                    scoped_label=self.stable_scope_label,
                    scoped_bbox=self.stable_scope_bbox,
                    scoped_confidence=self.stable_scope_confidence,
                    stable=True,
                    stability_counter=self.stability_counter,
                    required_frames=self.required_frames,
                    candidate_track_id=primary_id,
                    candidate_label=primary.label,
                    reason=f"stable scope locked: {primary.label}",
                    ambiguity=False,
                    timestamp=timestamp
                )
            else:
                # Still building stability
                return StableScopeResult(
                    scoped_track_id=self.stable_scope_id,
                    scoped_label=self.stable_scope_label,
                    scoped_bbox=self.stable_scope_bbox,
                    scoped_confidence=self.stable_scope_confidence,
                    stable=self.stable_scope_id is not None,
                    stability_counter=self.stability_counter,
                    required_frames=self.required_frames,
                    candidate_track_id=primary_id,
                    candidate_label=primary.label,
                    reason=f"building stability: {self.stability_counter}/{self.required_frames}",
                    ambiguity=False,
                    timestamp=timestamp
                )
        
        else:
            # Different primary than candidate
            # Reset candidate to new primary
            self.current_candidate_id = primary_id
            self.current_candidate_label = primary.label
            self.stability_counter = 1
            self.candidate_first_seen = timestamp
            
            # Keep stable scope if we had one (don't clear on first deviation)
            return StableScopeResult(
                scoped_track_id=self.stable_scope_id,
                scoped_label=self.stable_scope_label,
                scoped_bbox=self.stable_scope_bbox,
                scoped_confidence=self.stable_scope_confidence,
                stable=self.stable_scope_id is not None,
                stability_counter=1,
                required_frames=self.required_frames,
                candidate_track_id=primary_id,
                candidate_label=primary.label,
                reason=f"new candidate: {primary.label} (counter reset)",
                ambiguity=False,
                timestamp=timestamp
            )
    
    def _reset_candidate(self):
        """Clear current candidate"""
        self.current_candidate_id = None
        self.current_candidate_label = None
        self.stability_counter = 0
        self.candidate_first_seen = None
    
    def _clear_stable_scope(self):
        """Clear stable scope"""
        self.stable_scope_id = None
        self.stable_scope_label = None
        self.stable_scope_bbox = None
        self.stable_scope_confidence = 0.0
        self.stable_scope_locked_at = None
    
    def force_clear(self):
        """Hard reset (for recovery/undo)"""
        self._reset_candidate()
        self._clear_stable_scope()




