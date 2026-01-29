"""
Gaze estimator - webcam-based attention approximation.
Week 3: Uses MediaPipe face mesh to estimate gaze direction.
Approximation: nose tip position as gaze proxy (good enough for selection).
"""

from typing import Optional
import cv2
import numpy as np
from .selection_cursor import SelectionCursor

# Try to import MediaPipe with compatibility for different versions
try:
    import mediapipe as mp
    # Try old API (mediapipe < 0.10)
    try:
        FaceMesh = mp.solutions.face_mesh.FaceMesh
        MEDIAPIPE_AVAILABLE = True
        MEDIAPIPE_API = "legacy"
    except AttributeError:
        # New API not yet implemented in this version
        # For Week 3, we'll use mouse fallback if MediaPipe unavailable
        MEDIAPIPE_AVAILABLE = False
        MEDIAPIPE_API = "none"
        print("⚠️  MediaPipe face_mesh API not available, using mouse fallback only")
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    MEDIAPIPE_API = "none"
    print("⚠️  MediaPipe not installed, using mouse fallback only")


class GazeEstimator:
    """
    Webcam-based gaze estimator using MediaPipe face mesh.
    
    Week 3 approximation: Uses nose tip (landmark 1) as gaze direction proxy.
    This is sufficient for object selection - clinical accuracy not needed.
    
    Note: Falls back to returning None if MediaPipe unavailable (use mouse fallback).
    """
    
    def __init__(self, camera_id: int = 0, width: int = 640, height: int = 480):
        """
        Initialize gaze estimator.
        
        Args:
            camera_id: Webcam device ID
            width: Camera frame width
            height: Camera frame height
        """
        self.camera_id = camera_id
        self.width = width
        self.height = height
        
        self.cap: Optional[cv2.VideoCapture] = None
        self.face_mesh = None
        
        if MEDIAPIPE_AVAILABLE and MEDIAPIPE_API == "legacy":
            self.face_mesh = FaceMesh(
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5
            )
        
        self._running = False
    
    def start(self) -> bool:
        """
        Start camera capture.
        
        Returns:
            True if camera opened successfully
        """
        self.cap = cv2.VideoCapture(self.camera_id)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        
        if not self.cap.isOpened():
            print(f"⚠️  Failed to open camera {self.camera_id}")
            return False
        
        self._running = True
        print(f"✓ Gaze estimator started (camera {self.camera_id})")
        return True
    
    def read_cursor(self) -> Optional[SelectionCursor]:
        """
        Read current gaze cursor from webcam.
        
        Returns:
            SelectionCursor if face detected, else None
        """
        if not self._running or self.cap is None or self.face_mesh is None:
            return None
        
        ret, frame = self.cap.read()
        if not ret:
            return None
        
        # Convert BGR to RGB for MediaPipe
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(frame_rgb)
        
        if not results.multi_face_landmarks:
            return None  # No face detected
        
        # Get first face
        face_landmarks = results.multi_face_landmarks[0]
        
        # Use nose tip (landmark 1) as gaze proxy
        nose_tip = face_landmarks.landmark[1]
        
        # Normalize to [0, 1] (MediaPipe landmarks already normalized)
        u = nose_tip.x
        v = nose_tip.y
        
        # Confidence: simple heuristic based on nose visibility
        confidence = 1.0 - abs(nose_tip.z)  # z ~ 0 means visible
        confidence = max(0.0, min(1.0, confidence))
        
        return SelectionCursor.from_gaze(u, v, confidence)
    
    def close(self) -> None:
        """Release camera resources."""
        if self.cap is not None:
            self.cap.release()
            self._running = False
            print("✓ Gaze estimator closed")

