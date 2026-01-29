"""Tests for ObjectDetector module."""

import unittest
import numpy as np
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

from vision.object_detector import (
    MockObjectDetector,
    ContourObjectDetector,
    YOLOObjectDetector,
    DetectedObject,
    DetectionResult,
    create_detector
)
from vision.camera_stream import CameraFrame, CameraConfig


class TestMockObjectDetector(unittest.TestCase):
    """Test MockObjectDetector."""
    
    def test_initialization(self):
        """Test detector initialization."""
        config = {"min_confidence": 0.5, "min_area_pixels": 1000}
        detector = MockObjectDetector(config, seed=42)
        
        self.assertEqual(detector.seed, 42)
        self.assertEqual(detector.min_confidence, 0.5)
    
    def test_detect_returns_result(self):
        """Test that detect() returns DetectionResult."""
        config = {"min_confidence": 0.5, "min_area_pixels": 100}
        detector = MockObjectDetector(config, seed=42)
        
        # Create mock frame
        frame = CameraFrame(
            frame_id=0,
            timestamp=0.0,
            image=np.zeros((480, 640, 3), dtype=np.uint8),
            width=640,
            height=480,
            fps=30.0
        )
        
        result = detector.detect(frame)
        self.assertIsInstance(result, DetectionResult)
        self.assertEqual(result.frame_id, 0)
        self.assertGreaterEqual(len(result.objects), 1)
        self.assertLessEqual(len(result.objects), 3)
    
    def test_detect_deterministic(self):
        """Test that mock detector is deterministic."""
        config = {"min_confidence": 0.5, "min_area_pixels": 100}
        
        # First run
        detector1 = MockObjectDetector(config, seed=42)
        frame1 = CameraFrame(
            frame_id=0,
            timestamp=0.0,
            image=np.zeros((480, 640, 3), dtype=np.uint8),
            width=640,
            height=480,
            fps=30.0
        )
        result1 = detector1.detect(frame1)
        
        # Second run with same seed
        detector2 = MockObjectDetector(config, seed=42)
        frame2 = CameraFrame(
            frame_id=0,
            timestamp=0.0,
            image=np.zeros((480, 640, 3), dtype=np.uint8),
            width=640,
            height=480,
            fps=30.0
        )
        result2 = detector2.detect(frame2)
        
        # Should produce same number of objects
        self.assertEqual(len(result1.objects), len(result2.objects))
        
        # Objects should have same labels (order may vary)
        labels1 = sorted([obj.label for obj in result1.objects])
        labels2 = sorted([obj.label for obj in result2.objects])
        self.assertEqual(labels1, labels2)
    
    def test_detect_objects_have_valid_properties(self):
        """Test that detected objects have valid properties."""
        config = {"min_confidence": 0.5, "min_area_pixels": 100}
        detector = MockObjectDetector(config, seed=42)
        
        frame = CameraFrame(
            frame_id=0,
            timestamp=0.0,
            image=np.zeros((480, 640, 3), dtype=np.uint8),
            width=640,
            height=480,
            fps=30.0
        )
        
        result = detector.detect(frame)
        
        for obj in result.objects:
            self.assertIsInstance(obj, DetectedObject)
            self.assertIsNotNone(obj.detection_id)
            self.assertIn(obj.label, ["lamp", "cup", "phone"])
            self.assertGreaterEqual(obj.confidence, 0.5)
            self.assertLessEqual(obj.confidence, 1.0)
            self.assertEqual(len(obj.bbox), 4)
            x, y, w, h = obj.bbox
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(x + w, 640)
            self.assertLessEqual(y + h, 480)
            self.assertEqual(obj.area, w * h)
            self.assertEqual(len(obj.center_point), 2)
            self.assertEqual(obj.frame_id, 0)
    
    def test_detect_filters_by_min_area(self):
        """Test that detector filters objects by minimum area."""
        config = {"min_confidence": 0.5, "min_area_pixels": 10000}  # Large min area
        detector = MockObjectDetector(config, seed=42)
        
        frame = CameraFrame(
            frame_id=0,
            timestamp=0.0,
            image=np.zeros((480, 640, 3), dtype=np.uint8),
            width=640,
            height=480,
            fps=30.0
        )
        
        result = detector.detect(frame)
        
        # All objects should meet min area requirement
        for obj in result.objects:
            self.assertGreaterEqual(obj.area, 10000)
    
    def test_detect_filters_by_min_confidence(self):
        """Test that detector filters objects by minimum confidence."""
        config = {"min_confidence": 0.9, "min_area_pixels": 100}  # High min confidence
        detector = MockObjectDetector(config, seed=42)
        
        frame = CameraFrame(
            frame_id=0,
            timestamp=0.0,
            image=np.zeros((480, 640, 3), dtype=np.uint8),
            width=640,
            height=480,
            fps=30.0
        )
        
        result = detector.detect(frame)
        
        # All objects should meet min confidence requirement
        for obj in result.objects:
            self.assertGreaterEqual(obj.confidence, 0.9)
    
    def test_detect_respects_max_detections(self):
        """Test that detector respects max_detections limit."""
        config = {"min_confidence": 0.5, "min_area_pixels": 100, "max_detections": 2}
        detector = MockObjectDetector(config, seed=42)
        
        frame = CameraFrame(
            frame_id=0,
            timestamp=0.0,
            image=np.zeros((480, 640, 3), dtype=np.uint8),
            width=640,
            height=480,
            fps=30.0
        )
        
        result = detector.detect(frame)
        self.assertLessEqual(len(result.objects), 2)


class TestContourObjectDetector(unittest.TestCase):
    """Test ContourObjectDetector."""
    
    @unittest.skipIf(not CV2_AVAILABLE, "cv2 not available")
    def test_detect_on_simple_image(self):
        """Test contour detector on simple test image."""
        config = {"min_confidence": 0.3, "min_area_pixels": 100}
        detector = ContourObjectDetector(config, seed=42)
        
        # Create image with a white rectangle (should be detected)
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.rectangle(image, (100, 100), (200, 200), (255, 255, 255), -1)
        
        frame = CameraFrame(
            frame_id=0,
            timestamp=0.0,
            image=image,
            width=640,
            height=480,
            fps=30.0
        )
        
        result = detector.detect(frame)
        self.assertIsInstance(result, DetectionResult)
        # Should detect at least one object (the white rectangle)
        self.assertGreaterEqual(len(result.objects), 1)
        
        # All objects should have label "unknown"
        for obj in result.objects:
            self.assertEqual(obj.label, "unknown")


class TestDetectorFactory(unittest.TestCase):
    """Test detector factory function."""
    
    def test_create_mock_detector(self):
        """Test creating mock detector."""
        config = {"mode": "mock", "detection": {"min_confidence": 0.5}}
        detector = create_detector(config, seed=42)
        self.assertIsInstance(detector, MockObjectDetector)
    
    def test_create_contour_detector(self):
        """Test creating contour detector."""
        config = {"mode": "contour", "detection": {"min_confidence": 0.5}}
        detector = create_detector(config, seed=42)
        self.assertIsInstance(detector, ContourObjectDetector)
    
    def test_create_yolo_detector(self):
        """Test creating YOLO detector (placeholder)."""
        config = {"mode": "yolo", "detection": {"min_confidence": 0.5}}
        detector = create_detector(config, seed=42)
        self.assertIsInstance(detector, YOLOObjectDetector)
    
    def test_create_default_detector(self):
        """Test creating detector with unknown mode (defaults to mock)."""
        config = {"mode": "unknown", "detection": {"min_confidence": 0.5}}
        detector = create_detector(config, seed=42)
        self.assertIsInstance(detector, MockObjectDetector)


if __name__ == "__main__":
    unittest.main()

