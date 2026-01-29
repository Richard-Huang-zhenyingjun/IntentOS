#!/usr/bin/env python3
"""
Test script for camera overlay rendering.
Run this to verify camera overlay works.
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
from src.vision.camera_scope_controller import CameraScopeController
from src.ui.camera_overlay import CameraOverlay
from src.intent_core.schema import SystemState
import cv2


def test_camera_overlay():
    """Test camera overlay rendering."""
    print("Testing Camera Overlay...")
    print("="*60)
    
    # Load config
    config_path = Path(__file__).parent.parent / "configs" / "vision.yaml"
    if config_path.exists():
        with open(config_path) as f:
            vision_config = yaml.safe_load(f)
    else:
        vision_config = {
            "detection": {"mode": "mock"},
            "focus_selection": {"min_confidence": 0.5},
            "camera_scope_controller": {"min_scope_confidence": 0.6},
            "camera_overlay": {
                "show_reticle": True,
                "show_all_detections": False,
                "reticle_radius": 50
            }
        }
    
    # Create components
    detector = create_detector(vision_config, seed=42)
    selector = FocusSelector(vision_config.get("focus_selection", {}))
    controller = CameraScopeController(vision_config.get("camera_scope_controller", {}))
    overlay = CameraOverlay(vision_config.get("camera_overlay", {}))
    
    print(f"✅ Detector: {type(detector).__name__}")
    print(f"✅ Focus selector created")
    print(f"✅ Camera scope controller created")
    print(f"✅ Camera overlay created")
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
    print("Processing 5 frames with overlay rendering...")
    for i in range(5):
        frame = camera.get_frame()
        if frame is None:
            print(f"⚠️  Frame {i}: None")
            continue
        
        # Step 1: Detect objects
        detection_result = detector.detect(frame)
        
        # Step 2: Select focus
        focus_result = selector.select(
            detection_result,
            frame.width,
            frame.height
        )
        
        # Step 3: Generate scope signal
        scope_signal = controller.process_frame(
            focus_result,
            frame.frame_id,
            frame.timestamp
        )
        
        # Step 4: Render overlay
        annotated_frame = overlay.render(
            frame.image,
            scope_signal,
            detection_result,
            scope_signal.suggested_state
        )
        
        print(f"\nFrame {i} (ID={frame.frame_id}):")
        print(f"  Objects detected: {len(detection_result.objects)}")
        print(f"  Scope signal: {scope_signal.suggested_state.value}")
        print(f"  Overlay rendered: {annotated_frame.shape}")
        
        # Optionally save frame (uncomment to save)
        # cv2.imwrite(f"test_frame_{i}.jpg", annotated_frame)
    
    camera.stop()
    print()
    print("✅ Camera overlay test passed!")
    return True


def test_overlay_components():
    """Test individual overlay components."""
    print("\nTesting Overlay Components...")
    print("="*60)
    
    overlay_config = {
        "show_reticle": True,
        "show_all_detections": True,
        "reticle_radius": 50
    }
    overlay = CameraOverlay(overlay_config)
    
    # Create test frame
    test_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    test_frame[:] = (50, 50, 50)  # Dark gray background
    
    # Test 1: Empty frame (no detections)
    print("Test 1: Empty frame")
    annotated1 = overlay.render(test_frame, None, None, SystemState.IDLE)
    assert annotated1.shape == test_frame.shape
    print("  ✅ Empty frame rendered")
    
    # Test 2: With detection result
    from src.vision.object_detector import DetectedObject, DetectionResult
    
    obj = DetectedObject(
        detection_id="test-1",
        label="lamp",
        bbox=(100, 100, 80, 80),
        confidence=0.8,
        center_point=(140, 140),
        area=6400,
        frame_id=0
    )
    
    detection_result = DetectionResult(
        objects=[obj],
        frame_id=0,
        timestamp=0.0,
        detection_time_ms=10.0
    )
    
    print("Test 2: With detection result")
    annotated2 = overlay.render(test_frame, None, detection_result, SystemState.IDLE)
    assert annotated2.shape == test_frame.shape
    print("  ✅ Detection result rendered")
    
    # Test 3: With scope signal
    from src.vision.camera_scope_controller import CameraScopeSignal
    
    scope_signal = CameraScopeSignal(
        scoped_object_id="test-1",
        object_label="lamp",
        bbox=(100, 100, 80, 80),
        confidence=0.8,
        focus_reason="focused on lamp",
        ambiguity_detected=False,
        frame_id=0,
        timestamp=0.0,
        suggested_state=SystemState.SCOPED
    )
    
    print("Test 3: With scope signal")
    annotated3 = overlay.render(test_frame, scope_signal, detection_result, SystemState.SCOPED)
    assert annotated3.shape == test_frame.shape
    print("  ✅ Scope signal rendered")
    
    # Test 4: Different states
    print("Test 4: Different system states")
    for state in [SystemState.IDLE, SystemState.SCOPED, SystemState.PAUSED]:
        annotated = overlay.render(test_frame, None, None, state)
        assert annotated.shape == test_frame.shape
    print("  ✅ All states rendered")
    
    print()
    print("✅ All overlay component tests passed!")
    return True


if __name__ == "__main__":
    print("Camera Overlay Test")
    print("="*60)
    print()
    
    # Test overlay
    overlay_ok = test_camera_overlay()
    
    # Test components
    components_ok = test_overlay_components()
    
    print()
    print("="*60)
    if overlay_ok and components_ok:
        print("✅ All tests passed!")
        print()
        print("Next steps:")
        print("  1. Camera overlay is ready")
        print("  2. Integrate with WorkspaceUI")
        print("  3. Add logging for replay")
    else:
        print("❌ Some tests failed")
    print("="*60)

