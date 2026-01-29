"""Tracking Schema - Persistent object tracks across frames."""

from dataclasses import dataclass, field
from typing import Tuple, Optional, Deque, List
from collections import deque
import uuid


@dataclass
class Track:
    """
    Persistent track for an object across frames
    
    Lifecycle:
    - NEW: Just created, needs confirmation (hits < track_min_hits)
    - CONFIRMED: Seen enough times, eligible for scope
    - LOST: Not seen recently, being aged out
    - DELETED: Removed from tracker
    """
    track_id: str  # Persistent UUID
    label: str  # Object category
    
    # Current state
    bbox: Tuple[int, int, int, int]  # (x, y, width, height)
    confidence: float  # Current detection confidence
    confidence_ema: float  # Smoothed confidence
    
    # Temporal metadata
    created_at: float  # Timestamp when track created
    last_seen_at: float  # Timestamp of last detection
    last_updated_frame: int  # Frame ID of last update
    
    # Lifecycle counters
    age_frames: int = 0  # Total frames since creation
    hits: int = 0  # Successful detection matches
    missed_frames: int = 0  # Consecutive frames without detection
    
    # History for velocity/prediction (Week 4+)
    bbox_history: Deque[Tuple[float, Tuple[int, int, int, int]]] = field(
        default_factory=lambda: deque(maxlen=30)
    )
    confidence_history: Deque[float] = field(default_factory=lambda: deque(maxlen=10))
    
    # Status flags
    confirmed: bool = False  # hits >= track_min_hits
    
    def update_bbox(self, bbox: Tuple[int, int, int, int], confidence: float, 
                   timestamp: float, frame_id: int, ema_alpha: float):
        """Update track with new detection"""
        self.bbox = bbox
        self.confidence = confidence
        self.confidence_ema = ema_alpha * confidence + (1 - ema_alpha) * self.confidence_ema
        self.last_seen_at = timestamp
        self.last_updated_frame = frame_id
        self.hits += 1
        self.missed_frames = 0
        
        # Update history
        self.bbox_history.append((timestamp, bbox))
        self.confidence_history.append(confidence)
    
    def mark_missed(self):
        """Mark track as not detected this frame"""
        self.missed_frames += 1
        self.age_frames += 1
    
    def should_delete(self, max_age: int) -> bool:
        """Check if track should be removed"""
        return self.missed_frames > max_age
    
    def get_velocity(self) -> Optional[Tuple[float, float]]:
        """Estimate velocity from recent history (pixels/second)"""
        if len(self.bbox_history) < 2:
            return None
        
        # Compare current to oldest in history
        t_new, bbox_new = self.bbox_history[-1]
        t_old, bbox_old = self.bbox_history[0]
        
        dt = t_new - t_old
        if dt < 0.1:  # Too close in time
            return None
        
        # Center point movement
        cx_new = bbox_new[0] + bbox_new[2] / 2
        cy_new = bbox_new[1] + bbox_new[3] / 2
        cx_old = bbox_old[0] + bbox_old[2] / 2
        cy_old = bbox_old[1] + bbox_old[3] / 2
        
        vx = (cx_new - cx_old) / dt
        vy = (cy_new - cy_old) / dt
        
        return (vx, vy)


@dataclass
class TrackedObject:
    """
    Output format for tracked object (simplified from Track)
    Used by FocusSelector and downstream components
    """
    track_id: str
    label: str
    bbox: Tuple[int, int, int, int]
    confidence: float  # Smoothed confidence
    center_point: Tuple[int, int]
    area: int
    
    # Temporal metadata
    age_frames: int
    hits: int
    confirmed: bool
    
    # Optional velocity (for prediction)
    velocity: Optional[Tuple[float, float]] = None
    
    @classmethod
    def from_track(cls, track: Track):
        """Convert Track to TrackedObject"""
        cx = track.bbox[0] + track.bbox[2] // 2
        cy = track.bbox[1] + track.bbox[3] // 2
        area = track.bbox[2] * track.bbox[3]
        
        return cls(
            track_id=track.track_id,
            label=track.label,
            bbox=track.bbox,
            confidence=track.confidence_ema,
            center_point=(cx, cy),
            area=area,
            age_frames=track.age_frames,
            hits=track.hits,
            confirmed=track.confirmed,
            velocity=track.get_velocity()
        )


@dataclass
class TrackingResult:
    """Complete tracking output for one frame"""
    tracked_objects: List[TrackedObject]
    num_active_tracks: int
    num_confirmed_tracks: int
    num_new_tracks: int
    num_deleted_tracks: int
    frame_id: int
    timestamp: float




