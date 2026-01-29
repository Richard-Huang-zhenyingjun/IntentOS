"""Hand Detector - Detect hand landmarks for gesture recognition."""

from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np
import cv2


@dataclass
class HandLandmarks:
    """
    Hand landmark positions (normalized coordinates)
    
    Coordinates are normalized to [0, 1] relative to frame size
    """
    # Key fingertips (for pinch detection)
    thumb_tip: Tuple[float, float]  # (x, y)
    index_tip: Tuple[float, float]  # (x, y)
    
    # Additional landmarks (for future gestures)
    middle_tip: Optional[Tuple[float, float]] = None
    ring_tip: Optional[Tuple[float, float]] = None
    pinky_tip: Optional[Tuple[float, float]] = None
    
    # Metadata
    confidence: float = 1.0  # Detection confidence
    handedness: str = "unknown"  # "left", "right", "unknown"
    timestamp: float = 0.0
    
    def get_distance(self, point1_name: str, point2_name: str) -> float:
        """Calculate Euclidean distance between two landmarks"""
        point1 = getattr(self, point1_name)
        point2 = getattr(self, point2_name)
        
        if point1 is None or point2 is None:
            return float('inf')
        
        dx = point1[0] - point2[0]
        dy = point1[1] - point2[1]
        return np.sqrt(dx**2 + dy**2)


@dataclass
class HandDetectionResult:
    """Result of hand detection for one frame"""
    landmarks: Optional[HandLandmarks]
    detected: bool
    confidence: float
    frame_id: int
    timestamp: float
    failure_reason: Optional[str] = None


class HandDetector:
    """
    Detect hand landmarks in camera frames
    
    Week 4: Wrapper around MediaPipe Hands
    Design: Replaceable backend (can swap MediaPipe for custom model)
    """
    
    def __init__(self, config: dict, seed: int = 42):
        self.config = config
        self.seed = seed
        
        # Backend selection
        self.backend = config.get('backend', 'mediapipe')
        
        # Thresholds
        self.min_detection_confidence = config.get('min_detection_confidence', 0.7)
        self.min_tracking_confidence = config.get('min_tracking_confidence', 0.5)
        self.max_num_hands = config.get('max_num_hands', 1)
        
        # Initialize backend
        if self.backend == 'mediapipe':
            self._init_mediapipe()
        elif self.backend == 'mock':
            self._init_mock()
        else:
            raise ValueError(f"Unknown backend: {self.backend}")
        
        # State
        self.frame_count = 0
        self.total_detections = 0
        self.failed_detections = 0
    
    def _init_mediapipe(self):
        """Initialize MediaPipe Hands"""
        try:
            import mediapipe as mp
            self.mp_hands = mp.solutions.hands
            self.hands = self.mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=self.max_num_hands,
                min_detection_confidence=self.min_detection_confidence,
                min_tracking_confidence=self.min_tracking_confidence
            )
            self.mp_available = True
        except ImportError:
            print("WARNING: MediaPipe not available, falling back to mock")
            self._init_mock()
            self.mp_available = False
    
    def _init_mock(self):
        """Initialize mock detector (for testing)"""
        self.mock_mode = True
        self.mock_rng = np.random.RandomState(self.seed)
        self.mp_available = False
    
    def detect(self, frame: np.ndarray, frame_id: int, timestamp: float) -> HandDetectionResult:
        """
        Detect hand landmarks in frame
        
        Args:
            frame: BGR image (numpy array)
            frame_id: Frame identifier
            timestamp: Timestamp
        
        Returns:
            HandDetectionResult with landmarks or None
        """
        self.frame_count += 1
        
        if self.backend == 'mock' or (self.backend == 'mediapipe' and not self.mp_available):
            return self._detect_mock(frame, frame_id, timestamp)
        else:
            return self._detect_mediapipe(frame, frame_id, timestamp)
    
    def _detect_mediapipe(self, frame: np.ndarray, frame_id: int, timestamp: float) -> HandDetectionResult:
        """Detect using MediaPipe"""
        if not self.mp_available:
            return HandDetectionResult(
                landmarks=None,
                detected=False,
                confidence=0.0,
                frame_id=frame_id,
                timestamp=timestamp,
                failure_reason="MediaPipe not available"
            )
        
        # Convert BGR to RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Process
        try:
            results = self.hands.process(rgb_frame)
        except Exception as e:
            self.failed_detections += 1
            return HandDetectionResult(
                landmarks=None,
                detected=False,
                confidence=0.0,
                frame_id=frame_id,
                timestamp=timestamp,
                failure_reason=f"MediaPipe error: {str(e)}"
            )
        
        # No hands detected
        if not results.multi_hand_landmarks:
            self.failed_detections += 1
            return HandDetectionResult(
                landmarks=None,
                detected=False,
                confidence=0.0,
                frame_id=frame_id,
                timestamp=timestamp,
                failure_reason="No hands detected"
            )
        
        # Get first hand (we only track one)
        hand_landmarks = results.multi_hand_landmarks[0]
        handedness = results.multi_handedness[0].classification[0].label.lower()
        confidence = results.multi_handedness[0].classification[0].score
        
        # Extract key landmarks (MediaPipe landmark indices)
        # See: https://google.github.io/mediapipe/solutions/hands.html
        THUMB_TIP = 4
        INDEX_TIP = 8
        MIDDLE_TIP = 12
        RING_TIP = 16
        PINKY_TIP = 20
        
        landmarks_obj = HandLandmarks(
            thumb_tip=(
                hand_landmarks.landmark[THUMB_TIP].x,
                hand_landmarks.landmark[THUMB_TIP].y
            ),
            index_tip=(
                hand_landmarks.landmark[INDEX_TIP].x,
                hand_landmarks.landmark[INDEX_TIP].y
            ),
            middle_tip=(
                hand_landmarks.landmark[MIDDLE_TIP].x,
                hand_landmarks.landmark[MIDDLE_TIP].y
            ),
            ring_tip=(
                hand_landmarks.landmark[RING_TIP].x,
                hand_landmarks.landmark[RING_TIP].y
            ),
            pinky_tip=(
                hand_landmarks.landmark[PINKY_TIP].x,
                hand_landmarks.landmark[PINKY_TIP].y
            ),
            confidence=confidence,
            handedness=handedness,
            timestamp=timestamp
        )
        
        self.total_detections += 1
        
        return HandDetectionResult(
            landmarks=landmarks_obj,
            detected=True,
            confidence=confidence,
            frame_id=frame_id,
            timestamp=timestamp
        )
    
    def _detect_mock(self, frame: np.ndarray, frame_id: int, timestamp: float) -> HandDetectionResult:
        """
        Mock detector for deterministic testing
        
        Simulates hand presence/absence and pinch gestures
        """
        # Simulate hand presence (80% of frames)
        if self.mock_rng.random() < 0.8:
            # Simulate pinch (30% of time when hand present)
            is_pinching = self.mock_rng.random() < 0.3
            
            if is_pinching:
                # Close together
                thumb = (0.45 + self.mock_rng.random() * 0.02, 0.5)
                index = (0.47 + self.mock_rng.random() * 0.02, 0.5)
            else:
                # Far apart
                thumb = (0.4, 0.5)
                index = (0.6, 0.5)
            
            landmarks = HandLandmarks(
                thumb_tip=thumb,
                index_tip=index,
                confidence=0.9,
                handedness="right",
                timestamp=timestamp
            )
            
            self.total_detections += 1
            
            return HandDetectionResult(
                landmarks=landmarks,
                detected=True,
                confidence=0.9,
                frame_id=frame_id,
                timestamp=timestamp
            )
        else:
            # No hand
            self.failed_detections += 1
            return HandDetectionResult(
                landmarks=None,
                detected=False,
                confidence=0.0,
                frame_id=frame_id,
                timestamp=timestamp,
                failure_reason="Mock: no hand"
            )
    
    def get_statistics(self) -> dict:
        """Get detection statistics"""
        return {
            'frame_count': self.frame_count,
            'total_detections': self.total_detections,
            'failed_detections': self.failed_detections,
            'detection_rate': self.total_detections / max(1, self.frame_count)
        }
    
    def cleanup(self):
        """Release resources"""
        if hasattr(self, 'hands') and self.hands:
            self.hands.close()




