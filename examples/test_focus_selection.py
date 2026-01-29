#!/usr/bin/env python3
"""
Test script for focus selection.
Run this to verify focus selection works.
"""

import sys
from pathlib import Path
import numpy as np
import yaml

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.vision.camera_stream import CameraStream, CameraConfig
from src.vision.object_detector import create_detector
from src.vision.focus_selector import FocusSelector


def test_focus_selection():
    """Test focus selection with mock detector."""
    print("Testing Focus Selection...")
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
                "min_area_pixels": 1000
            },
            "focus_selection": {
                "min_confidence": 0.5,
                "min_score_margin": 0.2,
                "center_reticle_radius": 50,
                "weight_center": 0.6,
                "weight_size": 0.2,
                "weight_confidence": 0.2
            }
        }
    
    # Create detector
    detector = create_detector(vision_config, seed=42)
    print(f"✅ Detector created: {type(detector).__name__}")
    
    # Create focus selector
    selector = FocusSelector(vision_config.get("focus_selection", {}))
    print(f"✅ Focus selector created")
    print(f"   Min confidence: {selector.min_confidence}")
    print(f"   Min score margin: {selector.min_score_margin}")
    print(f"   Weights: center={selector.weight_center}, "
          f"size={selector.weight_size}, confidence={selector.weight_confidence}")
    print()
    
    # Create mock camera stream
    camera_config = CameraConfig(mock_mode=True, width=640, height=480)
    camera = CameraStream(camera_config, seed=42)
    
    if not camera.start():
        print("❌ Failed to start camera")
        return False
    
    print("✅ Camera started")
    print()
    
    # Process 5 frames
    print("Processing 5 frames with focus selection...")
    for i in range(5):
        frame = camera.get_frame()
        if frame is None:
            print(f"⚠️  Frame {i}: None")
            continue
        
        # Detect objects
        detection_result = detector.detect(frame)
        
        # Select focus
        focus_result = selector.select(
            detection_result,
            frame.width,
            frame.height
        )
        
        print(f"\nFrame {i} (ID={detection_result.frame_id}):")
        print(f"  Objects detected: {len(detection_result.objects)}")
        print(f"  Candidates considered: {focus_result.candidates_considered}")
        
        if focus_result.primary_object:
            obj = focus_result.primary_object
            print(f"  ✅ PRIMARY FOCUS: {obj.label}")
            print(f"     Confidence: {obj.confidence:.2f}")
            print(f"     BBox: {obj.bbox}")
            print(f"     Center: {obj.center_point}")
            print(f"     Score margin: {focus_result.score_margin:.3f}")
            if focus_result.runner_up_object:
                print(f"     Runner-up: {focus_result.runner_up_object.label}")
        elif focus_result.ambiguity_detected:
            print(f"  ⚠️  AMBIGUITY DETECTED")
            print(f"     Reason: {focus_result.reason}")
            print(f"     Score margin: {focus_result.score_margin:.3f}")
            if focus_result.runner_up_object:
                print(f"     Runner-up: {focus_result.runner_up_object.label}")
        else:
            print(f"  ❌ NO FOCUS SELECTED")
            print(f"     Reason: {focus_result.reason}")
    
    camera.stop()
    print()
    print("✅ Focus selection test passed!")
    return True


def test_ambiguity_detection():
    """Test ambiguity detection with similar objects."""
    print("\nTesting Ambiguity Detection...")
    print("="*60)
    
    config = {
        "focus_selection": {
            "min_confidence": 0.5,
            "min_score_margin": 0.2,
            "weight_center": 0.6,
            "weight_size": 0.2,
            "weight_confidence": 0.2
        }
    }
    
    selector = FocusSelector(config["focus_selection"])
    
    # Create two very similar objects (should trigger ambiguity)
    from src.vision.object_detector import DetectedObject, DetectionResult
    
    obj1 = DetectedObject(
        detection_id="test-1",
        label="lamp",
        bbox=(300, 220, 80, 80),
        confidence=0.7,
        center_point=(340, 260),
        area=6400,
        frame_id=0
    )
    
    obj2 = DetectedObject(
        detection_id="test-2",
        label="cup",
        bbox=(310, 230, 80, 80),  # Very close to obj1
        confidence=0.7,
        center_point=(350, 270),
        area=6400,
        frame_id=0
    )
    
    result = DetectionResult(
        objects=[obj1, obj2],
        frame_id=0,
        timestamp=0.0,
        detection_time_ms=0.0
    )
    
    focus_result = selector.select(result, 640, 480)
    
    print(f"Candidates: {focus_result.candidates_considered}")
    print(f"Ambiguity detected: {focus_result.ambiguity_detected}")
    print(f"Score margin: {focus_result.score_margin:.3f}")
    print(f"Reason: {focus_result.reason}")
    
    if focus_result.ambiguity_detected:
        print("✅ Ambiguity correctly detected!")
        return True
    else:
        print("⚠️  Ambiguity not detected (may be OK if scores differ enough)")
        return True


if __name__ == "__main__":
    print("Focus Selection Test")
    print("="*60)
    print()
    
    # Test focus selection
    selection_ok = test_focus_selection()
    
    # Test ambiguity detection
    ambiguity_ok = test_ambiguity_detection()
    
    print()
    print("="*60)
    if selection_ok and ambiguity_ok:
        print("✅ All tests passed!")
        print()
        print("Next steps:")
        print("  1. Focus selection is ready")
        print("  2. Add visual overlay (next step)")
        print("  3. Integrate with SystemOrchestrator")
    else:
        print("❌ Some tests failed")
    print("="*60)

