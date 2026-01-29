"""Pinch Detector - Detect pinch gestures from hand landmarks."""

from dataclasses import dataclass
from typing import Optional
import numpy as np
from vision.hand_detector import HandLandmarks


@dataclass
class PinchObservation:
    """
    Single-frame pinch observation (raw, unstable)
    
    This is NOT a confirmed pinch - just an observation
    Stability filtering happens in PinchStability
    """
    pinching: bool  # Is pinch detected this frame?
    distance: float  # Normalized distance between thumb & index
    distance_pixels: float  # Absolute pixel distance (for debugging)
    confidence: float  # Inherited from hand detection
    timestamp: float
    frame_id: int
    
    # Debug info
    thumb_pos: tuple
    index_pos: tuple
    threshold_used: float


class PinchDetector:
    """
    Detect pinch gesture from hand landmarks
    
    Week 4: Simple distance-based detection
    Week 6+: Could add finger orientation, palm direction, etc.
    
    Design principle: Conservative (prefer false negative over false positive)
    """
    
    def __init__(self, config: dict):
        self.config = config
        
        # Distance threshold (normalized to frame diagonal)
        self.distance_threshold = config.get('distance_threshold', 0.04)
        
        # Alternative: absolute pixel threshold
        self.distance_threshold_pixels = config.get('distance_threshold_pixels', None)
        
        # Confidence
        self.min_confidence = config.get('min_confidence', 0.7)
        
        # Stats
        self.total_observations = 0
        self.pinch_observations = 0
    
    def observe(self, 
                landmarks: Optional[HandLandmarks],
                frame_width: int,
                frame_height: int,
                frame_id: int,
                timestamp: float) -> Optional[PinchObservation]:
        """
        Observe pinch state for current frame
        
        Args:
            landmarks: Hand landmarks (or None if no hand)
            frame_width, frame_height: Frame dimensions
            frame_id: Frame identifier
            timestamp: Current timestamp
        
        Returns:
            PinchObservation or None if no hand detected
        """
        self.total_observations += 1
        
        # No hand → no pinch
        if landmarks is None:
            return None
        
        # Low confidence → no pinch
        if landmarks.confidence < self.min_confidence:
            return None
        
        # Calculate distance
        thumb = landmarks.thumb_tip
        index = landmarks.index_tip
        
        # Normalized distance
        dx_norm = thumb[0] - index[0]
        dy_norm = thumb[1] - index[1]
        distance_norm = np.sqrt(dx_norm**2 + dy_norm**2)
        
        # Pixel distance (for debugging/logging)
        dx_px = dx_norm * frame_width
        dy_px = dy_norm * frame_height
        distance_px = np.sqrt(dx_px**2 + dy_px**2)
        
        # Determine if pinching
        if self.distance_threshold_pixels is not None:
            # Use absolute pixel threshold
            pinching = distance_px < self.distance_threshold_pixels
            threshold = self.distance_threshold_pixels
        else:
            # Use normalized threshold
            pinching = distance_norm < self.distance_threshold
            threshold = self.distance_threshold
        
        if pinching:
            self.pinch_observations += 1
        
        return PinchObservation(
            pinching=pinching,
            distance=distance_norm,
            distance_pixels=distance_px,
            confidence=landmarks.confidence,
            timestamp=timestamp,
            frame_id=frame_id,
            thumb_pos=thumb,
            index_pos=index,
            threshold_used=threshold
        )
    
    def get_statistics(self) -> dict:
        """Get detection statistics"""
        return {
            'total_observations': self.total_observations,
            'pinch_observations': self.pinch_observations,
            'pinch_rate': self.pinch_observations / max(1, self.total_observations)
        }




