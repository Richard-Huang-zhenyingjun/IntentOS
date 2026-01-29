"""Object Detection - Stateless object detection from camera frames."""

import cv2
import numpy as np
import uuid
import time
from dataclasses import dataclass
from typing import List, Tuple, Optional
import logging

from vision.camera_stream import CameraFrame

logger = logging.getLogger(__name__)


@dataclass
class DetectedObject:
    """Single detected object."""
    detection_id: str  # UUID for this detection
    label: str  # "lamp", "cup", "phone", "unknown"
    bbox: Tuple[int, int, int, int]  # (x, y, width, height)
    confidence: float  # 0.0 - 1.0
    center_point: Tuple[int, int]  # computed from bbox
    area: int  # width * height
    frame_id: int  # which frame this came from


@dataclass
class DetectionResult:
    """Result of object detection on a frame."""
    objects: List[DetectedObject]
    frame_id: int
    timestamp: float
    detection_time_ms: float  # how long detection took


class ObjectDetector:
    """
    Base class for object detectors.
    
    All detectors are stateless - no memory between calls.
    Each detection is independent.
    """
    
    def __init__(self, config: dict, seed: int = 42):
        """
        Initialize detector.
        
        Args:
            config: Detection configuration
            seed: Random seed for deterministic testing
        """
        self.config = config
        self.seed = seed
        self.min_confidence = config.get("min_confidence", 0.5)
        self.min_area_pixels = config.get("min_area_pixels", 1000)
        self.max_detections = config.get("max_detections", 10)
    
    def detect(self, frame: CameraFrame) -> DetectionResult:
        """
        Detect objects in a frame (stateless).
        
        Args:
            frame: Camera frame to process
            
        Returns:
            DetectionResult with detected objects
        """
        raise NotImplementedError("Subclasses must implement detect()")


class MockObjectDetector(ObjectDetector):
    """
    Deterministic mock detector for testing.
    
    Returns 1-3 synthetic objects with known labels.
    Positions vary slightly each frame (simulates detection jitter).
    """
    
    # Known labels for mock mode
    MOCK_LABELS = ["lamp", "cup", "phone"]
    
    def __init__(self, config: dict, seed: int = 42):
        super().__init__(config, seed)
        np.random.seed(seed)
        self._frame_counter = 0
    
    def detect(self, frame: CameraFrame) -> DetectionResult:
        """Generate deterministic mock detections."""
        start_time = time.time()
        
        # Use seeded RNG based on frame_id for determinism
        rng = np.random.RandomState(self.seed + frame.frame_id)
        
        # Generate 1-3 objects
        num_objects = rng.randint(1, 4)
        objects = []
        
        for i in range(num_objects):
            # Select label
            label = self.MOCK_LABELS[i % len(self.MOCK_LABELS)]
            
            # Generate bounding box (vary slightly each frame)
            base_x = (frame.frame_id * 17 + i * 100) % (frame.width - 150)
            base_y = (frame.frame_id * 23 + i * 80) % (frame.height - 150)
            
            # Add small random jitter (simulates real detection noise)
            x = base_x + rng.randint(-10, 11)
            y = base_y + rng.randint(-10, 11)
            
            # Ensure within bounds
            x = max(0, min(x, frame.width - 100))
            y = max(0, min(y, frame.height - 100))
            
            # Box size varies slightly
            width = 80 + rng.randint(-20, 21)
            height = 80 + rng.randint(-20, 21)
            width = max(50, min(width, frame.width - x))
            height = max(50, min(height, frame.height - y))
            
            # Confidence varies slightly
            confidence = 0.7 + rng.uniform(-0.15, 0.2)
            confidence = max(self.min_confidence, min(confidence, 1.0))
            
            # Filter by min area
            area = width * height
            if area < self.min_area_pixels:
                continue
            
            # Create detected object
            center_x = x + width // 2
            center_y = y + height // 2
            
            obj = DetectedObject(
                detection_id=str(uuid.uuid4()),
                label=label,
                bbox=(x, y, width, height),
                confidence=confidence,
                center_point=(center_x, center_y),
                area=area,
                frame_id=frame.frame_id
            )
            
            objects.append(obj)
            
            # Limit max detections
            if len(objects) >= self.max_detections:
                break
        
        detection_time = (time.time() - start_time) * 1000  # Convert to ms
        
        return DetectionResult(
            objects=objects,
            frame_id=frame.frame_id,
            timestamp=frame.timestamp,
            detection_time_ms=detection_time
        )


class ContourObjectDetector(ObjectDetector):
    """
    Simple contour-based detection - no ML required.
    
    Uses basic computer vision:
    1. Convert to grayscale
    2. Apply threshold
    3. Find contours
    4. Filter by size
    5. Return as DetectedObject with label="unknown"
    """
    
    def __init__(self, config: dict, seed: int = 42):
        super().__init__(config, seed)
        self.threshold_value = config.get("threshold_value", 127)
        self.blur_kernel = config.get("blur_kernel", 5)
    
    def detect(self, frame: CameraFrame) -> DetectionResult:
        """Detect objects using contour detection."""
        start_time = time.time()
        
        # Convert to grayscale
        gray = cv2.cvtColor(frame.image, cv2.COLOR_BGR2GRAY)
        
        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (self.blur_kernel, self.blur_kernel), 0)
        
        # Apply threshold
        _, thresh = cv2.threshold(blurred, self.threshold_value, 255, cv2.THRESH_BINARY)
        
        # Find contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        objects = []
        
        for contour in contours:
            # Get bounding box
            x, y, w, h = cv2.boundingRect(contour)
            area = w * h
            
            # Filter by minimum area
            if area < self.min_area_pixels:
                continue
            
            # Calculate confidence based on contour area vs bounding box area
            contour_area = cv2.contourArea(contour)
            if area > 0:
                confidence = min(contour_area / area, 1.0)
            else:
                confidence = 0.5
            
            # Filter by minimum confidence
            if confidence < self.min_confidence:
                continue
            
            # Create detected object
            center_x = x + w // 2
            center_y = y + h // 2
            
            obj = DetectedObject(
                detection_id=str(uuid.uuid4()),
                label="unknown",  # Contour detector doesn't classify
                bbox=(x, y, w, h),
                confidence=confidence,
                center_point=(center_x, center_y),
                area=area,
                frame_id=frame.frame_id
            )
            
            objects.append(obj)
            
            # Limit max detections
            if len(objects) >= self.max_detections:
                break
        
        detection_time = (time.time() - start_time) * 1000  # Convert to ms
        
        return DetectionResult(
            objects=objects,
            frame_id=frame.frame_id,
            timestamp=frame.timestamp,
            detection_time_ms=detection_time
        )


class YOLOObjectDetector(ObjectDetector):
    """
    YOLO-based detection - Placeholder for Week 2+.
    
    Not implemented in Week 1.
    """
    
    def __init__(self, config: dict, seed: int = 42):
        super().__init__(config, seed)
        logger.warning("YOLOObjectDetector: Not implemented in Week 1")
    
    def detect(self, frame: CameraFrame) -> DetectionResult:
        """Placeholder - not implemented."""
        logger.warning("YOLOObjectDetector: Not implemented - use MockObjectDetector for Week 1")
        return DetectionResult(
            objects=[],
            frame_id=frame.frame_id,
            timestamp=frame.timestamp,
            detection_time_ms=0.0
        )


def create_detector(config: dict, seed: int = 42) -> ObjectDetector:
    """
    Factory function to create detector based on config.
    
    Args:
        config: Detection configuration dict
        seed: Random seed for deterministic testing
        
    Returns:
        ObjectDetector instance
    """
    mode = config.get("mode", "mock")
    detector_config = config.get("detection", {})
    
    if mode == "mock":
        return MockObjectDetector(detector_config, seed=seed)
    elif mode == "contour":
        return ContourObjectDetector(detector_config, seed=seed)
    elif mode == "yolo":
        return YOLOObjectDetector(detector_config, seed=seed)
    else:
        logger.warning(f"Unknown detector mode '{mode}', using mock detector")
        return MockObjectDetector(detector_config, seed=seed)

