#!/usr/bin/env python3
"""
Test script for camera scope controller.
Run this to verify camera scope controller works.
"""

import sys
from pathlib import Path
import yaml

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.vision.camera_stream import CameraStream, CameraConfig
from src.vision.object_detector import create_detector
from src.vision.focus_selector import FocusSelector
from src.vision.camera_scope_controller import CameraScopeController
from src.intent_core.schema import SystemState


def test_camera_scope_controller():
    """Test camera scope controller end-to-end."""
    print("Testing Camera Scope Controller...")
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
                "weight_center": 0.6,
                "weight_size": 0.2,
                "weight_confidence": 0.2
            },
            "camera_scope_controller": {
                "min_scope_confidence": 0.6
            }
        }
    
    # Create components
    detector = create_detector(vision_config, seed=42)
    selector = FocusSelector(vision_config.get("focus_selection", {}))
    controller = CameraScopeController(vision_config.get("camera_scope_controller", {}))
    
    print(f"✅ Detector: {type(detector).__name__}")
    print(f"✅ Focus selector created")
    print(f"✅ Camera scope controller created")
    print(f"   Min scope confidence: {controller.min_scope_confidence}")
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
    print("Processing 5 frames through complete pipeline...")
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
        
        print(f"\nFrame {i} (ID={frame.frame_id}):")
        print(f"  Objects detected: {len(detection_result.objects)}")
        print(f"  Focus candidates: {focus_result.candidates_considered}")
        print(f"  Scope signal:")
        print(f"    Suggested state: {scope_signal.suggested_state.value}")
        print(f"    Object: {scope_signal.object_label or 'None'}")
        print(f"    Confidence: {scope_signal.confidence:.2f}")
        print(f"    Ambiguity: {scope_signal.ambiguity_detected}")
        print(f"    Reason: {scope_signal.focus_reason}")
        
        # Verify signal properties
        if scope_signal.suggested_state == SystemState.SCOPED:
            assert scope_signal.scoped_object_id is not None
            assert scope_signal.object_label is not None
            assert scope_signal.confidence >= controller.min_scope_confidence
        elif scope_signal.suggested_state == SystemState.PAUSED:
            assert scope_signal.ambiguity_detected
        elif scope_signal.suggested_state == SystemState.IDLE:
            # IDLE can be for various reasons
            pass
    
    camera.stop()
    
    # Check controller state
    state = controller.get_state()
    print()
    print("Controller Statistics:")
    print(f"  Frames processed: {state.frames_processed}")
    print(f"  Scopes created: {state.scopes_created}")
    print(f"  Ambiguities detected: {state.ambiguities_detected}")
    
    print()
    print("✅ Camera scope controller test passed!")
    return True


def test_signal_states():
    """Test different signal states."""
    print("\nTesting Signal States...")
    print("="*60)
    
    controller = CameraScopeController({"min_scope_confidence": 0.6})
    
    from src.vision.focus_selector import FocusResult
    from src.vision.object_detector import DetectedObject
    
    # Test 1: Ambiguity → PAUSED
    focus_ambiguity = FocusResult(
        primary_object=None,
        ambiguity_detected=True,
        reason="ambiguous",
        candidates_considered=2,
        runner_up_object=None,
        score_margin=0.1,
        timestamp=0.0
    )
    
    signal1 = controller.process_frame(focus_ambiguity, frame_id=0, timestamp=1.0)
    print(f"Ambiguity → State: {signal1.suggested_state.value} ✅")
    assert signal1.suggested_state == SystemState.PAUSED
    
    # Test 2: No object → IDLE
    focus_no_obj = FocusResult(
        primary_object=None,
        ambiguity_detected=False,
        reason="no objects",
        candidates_considered=0,
        runner_up_object=None,
        score_margin=0.0,
        timestamp=0.0
    )
    
    signal2 = controller.process_frame(focus_no_obj, frame_id=1, timestamp=2.0)
    print(f"No object → State: {signal2.suggested_state.value} ✅")
    assert signal2.suggested_state == SystemState.IDLE
    
    # Test 3: Low confidence → IDLE
    obj_low = DetectedObject(
        detection_id="test-1",
        label="lamp",
        bbox=(100, 100, 80, 80),
        confidence=0.5,  # Below threshold
        center_point=(140, 140),
        area=6400,
        frame_id=2
    )
    
    focus_low = FocusResult(
        primary_object=obj_low,
        ambiguity_detected=False,
        reason="selected lamp",
        candidates_considered=1,
        runner_up_object=None,
        score_margin=0.0,
        timestamp=0.0
    )
    
    signal3 = controller.process_frame(focus_low, frame_id=2, timestamp=3.0)
    print(f"Low confidence → State: {signal3.suggested_state.value} ✅")
    assert signal3.suggested_state == SystemState.IDLE
    
    # Test 4: Confident scope → SCOPED
    obj_high = DetectedObject(
        detection_id="test-2",
        label="cup",
        bbox=(200, 200, 80, 80),
        confidence=0.8,  # Above threshold
        center_point=(240, 240),
        area=6400,
        frame_id=3
    )
    
    focus_high = FocusResult(
        primary_object=obj_high,
        ambiguity_detected=False,
        reason="selected cup",
        candidates_considered=1,
        runner_up_object=None,
        score_margin=0.0,
        timestamp=0.0
    )
    
    signal4 = controller.process_frame(focus_high, frame_id=3, timestamp=4.0)
    print(f"Confident scope → State: {signal4.suggested_state.value} ✅")
    assert signal4.suggested_state == SystemState.SCOPED
    
    print()
    print("✅ All signal state tests passed!")


if __name__ == "__main__":
    print("Camera Scope Controller Test")
    print("="*60)
    print()
    
    # Test end-to-end
    e2e_ok = test_camera_scope_controller()
    
    # Test signal states
    states_ok = test_signal_states()
    
    print()
    print("="*60)
    if e2e_ok and states_ok:
        print("✅ All tests passed!")
        print()
        print("Next steps:")
        print("  1. Camera scope controller is ready")
        print("  2. Integrate with SystemOrchestrator")
        print("  3. Add visual overlay")
    else:
        print("❌ Some tests failed")
    print("="*60)

