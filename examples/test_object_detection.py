#!/usr/bin/env python3
"""
Test script for object detection.
Run this to verify object detection works.
"""

import sys
from pathlib import Path
import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.vision.camera_stream import CameraStream, CameraConfig
from src.vision.object_detector import create_detector
import yaml


def test_mock_detector():
    """Test mock object detector."""
    print("Testing MockObjectDetector...")
    print("="*60)
    
    # Load config
    config_path = Path(__file__).parent.parent / "configs" / "vision.yaml"
    if config_path.exists():
        with open(config_path) as f:
            vision_config = yaml.safe_load(f)
    else:
        vision_config = {
            "detection": {
                "mode": "mock",
                "min_confidence": 0.5,
                "min_area_pixels": 1000,
                "max_detections": 10
            }
        }
    
    # Create detector
    detector = create_detector(vision_config, seed=42)
    print(f"✅ Detector created: {type(detector).__name__}")
    
    # Create mock camera stream
    camera_config = CameraConfig(mock_mode=True, width=640, height=480)
    camera = CameraStream(camera_config, seed=42)
    
    if not camera.start():
        print("❌ Failed to start camera")
        return False
    
    print("✅ Camera started")
    print()
    
    # Process 5 frames
    print("Processing 5 frames...")
    for i in range(5):
        frame = camera.get_frame()
        if frame is None:
            print(f"⚠️  Frame {i}: None")
            continue
        
        # Detect objects
        result = detector.detect(frame)
        
        print(f"\nFrame {i} (ID={result.frame_id}):")
        print(f"  Detection time: {result.detection_time_ms:.2f} ms")
        print(f"  Objects detected: {len(result.objects)}")
        
        for j, obj in enumerate(result.objects):
            x, y, w, h = obj.bbox
            print(f"    Object {j+1}:")
            print(f"      Label: {obj.label}")
            print(f"      Confidence: {obj.confidence:.2f}")
            print(f"      BBox: ({x}, {y}) {w}x{h}")
            print(f"      Center: {obj.center_point}")
            print(f"      Area: {obj.area} pixels")
    
    camera.stop()
    print()
    print("✅ Mock detector test passed!")
    return True


def test_determinism():
    """Test that mock detector is deterministic."""
    print("\nTesting Determinism...")
    print("="*60)
    
    config = {
        "detection": {
            "mode": "mock",
            "min_confidence": 0.5,
            "min_area_pixels": 1000
        }
    }
    
    # First run
    detector1 = create_detector(config, seed=42)
    camera1 = CameraStream(CameraConfig(mock_mode=True), seed=42)
    camera1.start()
    frame1 = camera1.get_frame()
    result1 = detector1.detect(frame1)
    camera1.stop()
    
    # Second run with same seed
    detector2 = create_detector(config, seed=42)
    camera2 = CameraStream(CameraConfig(mock_mode=True), seed=42)
    camera2.start()
    frame2 = camera2.get_frame()
    result2 = detector2.detect(frame2)
    camera2.stop()
    
    # Compare results
    if len(result1.objects) == len(result2.objects):
        print(f"✅ Same number of objects: {len(result1.objects)}")
        
        # Check labels match
        labels1 = sorted([obj.label for obj in result1.objects])
        labels2 = sorted([obj.label for obj in result2.objects])
        if labels1 == labels2:
            print(f"✅ Same labels: {labels1}")
        else:
            print(f"⚠️  Labels differ: {labels1} vs {labels2}")
        
        return True
    else:
        print(f"❌ Different number of objects: {len(result1.objects)} vs {len(result2.objects)}")
        return False


if __name__ == "__main__":
    print("Object Detection Test")
    print("="*60)
    print()
    
    # Test mock detector
    mock_ok = test_mock_detector()
    
    # Test determinism
    det_ok = test_determinism()
    
    print()
    print("="*60)
    if mock_ok and det_ok:
        print("✅ All tests passed!")
        print()
        print("Next steps:")
        print("  1. Object detection is ready")
        print("  2. Add visual scoping logic (next step)")
        print("  3. Integrate with SystemOrchestrator")
    else:
        print("❌ Some tests failed")
    print("="*60)

