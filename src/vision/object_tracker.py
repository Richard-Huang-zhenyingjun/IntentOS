"""Object Tracker - Multi-object tracker with persistent IDs."""

from typing import List, Dict
import uuid
from vision.object_detector import DetectedObject
from vision.tracking_schema import Track, TrackedObject, TrackingResult
from vision.tracking_utils import match_detections_to_tracks


class ObjectTracker:
    """
    Multi-object tracker with persistent IDs
    
    Responsibilities:
    - Maintain tracks across frames
    - Match new detections to existing tracks
    - Create new tracks for unmatched detections
    - Delete stale tracks
    - Output TrackedObject list with stable IDs
    """
    
    def __init__(self, config: dict, seed: int = 42):
        self.config = config
        self.seed = seed
        
        # Track management
        self.tracks: Dict[str, Track] = {}  # track_id -> Track
        self.next_track_num = 0
        
        # Config parameters
        self.max_age = config.get('track_max_age_frames', 10)
        self.min_hits = config.get('track_min_hits', 3)
        self.new_track_threshold = config.get('track_new_confidence_threshold', 0.6)
        self.ema_alpha = config.get('confidence_ema_alpha', 0.4)
        
        # Statistics
        self.total_tracks_created = 0
        self.total_tracks_deleted = 0
        self.current_frame_id = 0
    
    def update(self, 
               detections: List[DetectedObject],
               timestamp: float) -> TrackingResult:
        """
        Update tracks with new detections
        
        Pipeline:
        1. Match detections to existing tracks
        2. Update matched tracks
        3. Create new tracks for unmatched detections
        4. Age out missed tracks
        5. Return tracked objects
        """
        self.current_frame_id += 1
        
        active_tracks = [t for t in self.tracks.values() if not t.should_delete(self.max_age)]
        
        # 1. Match detections to tracks
        matches, unmatched_dets, unmatched_trks = match_detections_to_tracks(
            detections=detections,
            tracks=active_tracks,
            config=self.config
        )
        
        # 2. Update matched tracks
        for det_idx, track_idx in matches:
            detection = detections[det_idx]
            track = active_tracks[track_idx]
            
            track.update_bbox(
                bbox=detection.bbox,
                confidence=detection.confidence,
                timestamp=timestamp,
                frame_id=self.current_frame_id,
                ema_alpha=self.ema_alpha
            )
            
            # Confirm track if enough hits
            if track.hits >= self.min_hits:
                track.confirmed = True
        
        # 3. Mark unmatched tracks as missed
        for track_idx in unmatched_trks:
            track = active_tracks[track_idx]
            track.mark_missed()
        
        # 4. Create new tracks for unmatched detections
        num_new = 0
        for det_idx in unmatched_dets:
            detection = detections[det_idx]
            
            # Only create track if confidence is high enough
            if detection.confidence >= self.new_track_threshold:
                new_track = self._create_track(detection, timestamp)
                self.tracks[new_track.track_id] = new_track
                num_new += 1
        
        # 5. Delete old tracks
        num_deleted = 0
        for track_id in list(self.tracks.keys()):
            if self.tracks[track_id].should_delete(self.max_age):
                del self.tracks[track_id]
                num_deleted += 1
                self.total_tracks_deleted += 1
        
        # 6. Convert to TrackedObject format
        tracked_objects = [
            TrackedObject.from_track(track)
            for track in self.tracks.values()
            if track.confirmed  # Only output confirmed tracks
        ]
        
        return TrackingResult(
            tracked_objects=tracked_objects,
            num_active_tracks=len(self.tracks),
            num_confirmed_tracks=sum(1 for t in self.tracks.values() if t.confirmed),
            num_new_tracks=num_new,
            num_deleted_tracks=num_deleted,
            frame_id=self.current_frame_id,
            timestamp=timestamp
        )
    
    def _create_track(self, detection: DetectedObject, timestamp: float) -> Track:
        """Create new track from detection"""
        track_id = f"track_{self.total_tracks_created:04d}"
        self.total_tracks_created += 1
        
        return Track(
            track_id=track_id,
            label=detection.label,
            bbox=detection.bbox,
            confidence=detection.confidence,
            confidence_ema=detection.confidence,
            created_at=timestamp,
            last_seen_at=timestamp,
            last_updated_frame=self.current_frame_id,
            age_frames=0,
            hits=1,
            missed_frames=0
        )
    
    def get_track(self, track_id: str) -> Track:
        """Get track by ID"""
        return self.tracks.get(track_id)
    
    def get_all_tracks(self) -> List[Track]:
        """Get all active tracks"""
        return list(self.tracks.values())
    
    def reset(self):
        """Reset tracker state"""
        self.tracks.clear()
        self.total_tracks_created = 0
        self.total_tracks_deleted = 0
        self.current_frame_id = 0




