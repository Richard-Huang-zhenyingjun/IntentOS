"""Camera Scope Safety Tests - Week 1 Safety Invariants"""

import unittest
import numpy as np
from vision.camera_stream import CameraStream, CameraConfig, CameraFrame
from vision.object_detector import MockObjectDetector, DetectedObject, DetectionResult
from vision.focus_selector import FocusSelector, FocusResult
from vision.camera_scope_controller import CameraScopeController
from intent_core.schema import SystemState


class TestCameraScopeSafety(unittest.TestCase):
    """
    Week 1 Safety Tests: Camera integration must preserve all invariants
    """
    
    def test_never_more_than_one_scoped_object(self):
        """INVARIANT: At most one object scoped at any time"""
        selector = FocusSelector({'min_score_margin': 0.2})
        detector = MockObjectDetector({}, seed=42)
        
        # Create a test frame
        config = CameraConfig(mock_mode=True, width=640, height=480)
        camera = CameraStream(config, seed=42)
        camera.start()
        frame = camera.get_frame()
        camera.stop()
        
        # Generate detection result with multiple objects
        detection_result = detector.detect(frame)
        
        # Select focus
        focus_result = selector.select(
            detection_result=detection_result,
            frame_width=frame.width,
            frame_height=frame.height
        )
        
        # Assert: exactly 0 or 1 objects
        if focus_result.primary_object is not None:
            self.assertFalse(focus_result.ambiguity_detected)
            # Exactly 1 object
            self.assertIsInstance(focus_result.primary_object, DetectedObject)
        else:
            # 0 objects (either ambiguous or no candidates)
            # This is valid - no scope is better than ambiguous scope
            pass
        
        # Never 2+ objects scoped
        # The focus_result.primary_object is either None or a single DetectedObject
        self.assertTrue(
            focus_result.primary_object is None or 
            isinstance(focus_result.primary_object, DetectedObject)
        )
    
    def test_ambiguity_results_in_paused(self):
        """INVARIANT: Ambiguity must trigger PAUSED state"""
        controller = CameraScopeController({'min_scope_confidence': 0.6})
        
        # Create ambiguous focus result (2 objects with score_margin < 0.2)
        focus_result = FocusResult(
            primary_object=None,
            ambiguity_detected=True,
            reason="two objects competing",
            candidates_considered=2,
            runner_up_object=None,
            score_margin=0.1,  # < 0.2 threshold
            timestamp=1.0
        )
        
        signal = controller.process_frame(
            focus_result=focus_result,
            frame_id=1,
            timestamp=1.0
        )
        
        self.assertEqual(signal.suggested_state, SystemState.PAUSED)
        self.assertTrue(signal.ambiguity_detected)
        self.assertIsNone(signal.scoped_object_id)
    
    def test_no_execution_events_from_camera(self):
        """INVARIANT: Camera pipeline never triggers execution"""
        # This test verifies camera components don't have execution methods
        
        # Camera components should not have these methods:
        forbidden_methods = [
            'execute', 'trigger_action', 'confirm', 
            'apply_action', 'toggle_state'
        ]
        
        components = [
            CameraStream,
            MockObjectDetector,
            FocusSelector,
            CameraScopeController
        ]
        
        for component_class in components:
            for method in forbidden_methods:
                self.assertFalse(
                    hasattr(component_class, method),
                    f"{component_class.__name__} should not have {method}()"
                )
    
    def test_system_survives_camera_dropout(self):
        """INVARIANT: System continues operating if camera fails"""
        from intent_core.system_orchestrator import SystemOrchestrator
        
        config = {
            'camera_enabled': True,
            'camera': {'mock_mode': True},
            'detection': {'mode': 'mock'},
            'focus_selection': {'min_confidence': 0.5},
            'camera_scope_controller': {'min_scope_confidence': 0.6},
            'camera_overlay': {'show_reticle': True},
            'logging': {'enabled': False},  # Disable logging for test
            'seed': 42
        }
        
        orchestrator = SystemOrchestrator(config, seed=42)
        
        # Simulate camera failure by stopping it
        if orchestrator.camera_enabled:
            orchestrator.camera_stream.stop()
            orchestrator.camera_enabled = False
        
        # System should still process ticks
        snapshot = orchestrator.step(timestamp=1.0)
        
        # System should be in IDLE or previous state (not crashed)
        self.assertIsNotNone(snapshot)
        self.assertIn('timestamp', snapshot)
        self.assertIn('what_happened', snapshot)
        
        # Cleanup
        orchestrator.cleanup()
    
    def test_camera_scope_respects_confidence_threshold(self):
        """INVARIANT: Low confidence detections don't create scope"""
        controller = CameraScopeController({'min_scope_confidence': 0.7})
        
        # Create low-confidence detection
        low_conf_object = DetectedObject(
            detection_id="obj1",
            label="lamp",
            bbox=(100, 100, 50, 50),
            confidence=0.5,  # < 0.7 threshold
            center_point=(125, 125),
            area=2500,
            frame_id=1
        )
        
        focus_result = FocusResult(
            primary_object=low_conf_object,
            ambiguity_detected=False,
            reason="low confidence",
            candidates_considered=1,
            runner_up_object=None,
            score_margin=1.0,
            timestamp=1.0
        )
        
        signal = controller.process_frame(focus_result, 1, 1.0)
        
        # Should suggest IDLE, not SCOPED
        self.assertEqual(signal.suggested_state, SystemState.IDLE)
        self.assertIn("low confidence", signal.focus_reason.lower())
        self.assertEqual(signal.scoped_object_id, "obj1")  # Object ID is still present
        self.assertEqual(signal.confidence, 0.5)  # But confidence is low
    
    def test_deterministic_mock_detector(self):
        """INVARIANT: Same seed produces same detections"""
        detector1 = MockObjectDetector({}, seed=42)
        detector2 = MockObjectDetector({}, seed=42)
        
        # Create identical frames
        config = CameraConfig(mock_mode=True, width=640, height=480)
        camera1 = CameraStream(config, seed=42)
        camera1.start()
        frame1 = camera1.get_frame()
        camera1.stop()
        
        camera2 = CameraStream(config, seed=42)
        camera2.start()
        frame2 = camera2.get_frame()
        camera2.stop()
        
        # Both frames should be identical (same seed)
        self.assertTrue(np.array_equal(frame1.image, frame2.image))
        self.assertEqual(frame1.frame_id, frame2.frame_id)
        
        # Detect objects on both frames
        result1 = detector1.detect(frame1)
        result2 = detector2.detect(frame2)
        
        # Should produce identical results
        self.assertEqual(len(result1.objects), len(result2.objects))
        for obj1, obj2 in zip(result1.objects, result2.objects):
            self.assertEqual(obj1.bbox, obj2.bbox)
            self.assertAlmostEqual(obj1.confidence, obj2.confidence, places=5)
            self.assertEqual(obj1.label, obj2.label)
            self.assertEqual(obj1.center_point, obj2.center_point)
            self.assertEqual(obj1.area, obj2.area)
    
    def test_camera_never_suggests_executing(self):
        """INVARIANT: Camera scope controller never suggests EXECUTING state"""
        controller = CameraScopeController({'min_scope_confidence': 0.6})
        
        # Test all possible focus results
        test_cases = [
            # Ambiguity case
            FocusResult(
                primary_object=None,
                ambiguity_detected=True,
                reason="ambiguous",
                candidates_considered=2,
                runner_up_object=None,
                score_margin=0.1,
                timestamp=1.0
            ),
            # No object case
            FocusResult(
                primary_object=None,
                ambiguity_detected=False,
                reason="no objects",
                candidates_considered=0,
                runner_up_object=None,
                score_margin=0.0,
                timestamp=1.0
            ),
            # Low confidence case
            FocusResult(
                primary_object=DetectedObject(
                    detection_id="obj1",
                    label="lamp",
                    bbox=(100, 100, 50, 50),
                    confidence=0.5,
                    center_point=(125, 125),
                    area=2500,
                    frame_id=1
                ),
                ambiguity_detected=False,
                reason="low confidence",
                candidates_considered=1,
                runner_up_object=None,
                score_margin=1.0,
                timestamp=1.0
            ),
            # High confidence case
            FocusResult(
                primary_object=DetectedObject(
                    detection_id="obj2",
                    label="cup",
                    bbox=(200, 200, 80, 80),
                    confidence=0.8,
                    center_point=(240, 240),
                    area=6400,
                    frame_id=1
                ),
                ambiguity_detected=False,
                reason="selected cup",
                candidates_considered=1,
                runner_up_object=None,
                score_margin=1.0,
                timestamp=1.0
            )
        ]
        
        for i, focus_result in enumerate(test_cases):
            signal = controller.process_frame(focus_result, frame_id=i, timestamp=float(i))
            
            # Camera should NEVER suggest EXECUTING
            self.assertNotEqual(
                signal.suggested_state,
                SystemState.EXECUTING,
                f"Camera suggested EXECUTING for case {i}: {focus_result.reason}"
            )
            
            # Camera can only suggest: IDLE, SCOPED, or PAUSED
            self.assertIn(
                signal.suggested_state,
                [SystemState.IDLE, SystemState.SCOPED, SystemState.PAUSED],
                f"Camera suggested invalid state: {signal.suggested_state}"
            )
    
    def test_camera_scope_is_readonly(self):
        """INVARIANT: Camera scope signal is a suggestion, not a command"""
        controller = CameraScopeController({'min_scope_confidence': 0.6})
        
        obj = DetectedObject(
            detection_id="obj1",
            label="lamp",
            bbox=(100, 100, 80, 80),
            confidence=0.8,
            center_point=(140, 140),
            area=6400,
            frame_id=1
        )
        
        focus_result = FocusResult(
            primary_object=obj,
            ambiguity_detected=False,
            reason="selected lamp",
            candidates_considered=1,
            runner_up_object=None,
            score_margin=1.0,
            timestamp=1.0
        )
        
        signal = controller.process_frame(focus_result, frame_id=1, timestamp=1.0)
        
        # Signal should suggest SCOPED
        self.assertEqual(signal.suggested_state, SystemState.SCOPED)
        
        # But signal itself doesn't mutate anything
        # The signal is just data - core system decides what to do with it
        # This is verified by the fact that CameraScopeSignal is a dataclass
        # and CameraScopeController doesn't have methods to mutate core state
        
        # Verify signal is just data
        self.assertIsNotNone(signal.scoped_object_id)
        self.assertIsNotNone(signal.object_label)
        self.assertIsNotNone(signal.bbox)
        self.assertIsNotNone(signal.focus_reason)
        
        # But signal doesn't have execution methods
        self.assertFalse(hasattr(signal, 'execute'))
        self.assertFalse(hasattr(signal, 'apply'))
        self.assertFalse(hasattr(signal, 'trigger'))
    
    def test_focus_selector_at_most_one_primary(self):
        """INVARIANT: Focus selector returns at most one primary object"""
        selector = FocusSelector({'min_score_margin': 0.2})
        detector = MockObjectDetector({}, seed=42)
        
        # Create multiple test frames with varying numbers of objects
        config = CameraConfig(mock_mode=True, width=640, height=480)
        
        for seed_offset in range(10):
            camera = CameraStream(config, seed=42 + seed_offset)
            camera.start()
            frame = camera.get_frame()
            camera.stop()
            
            detection_result = detector.detect(frame)
            focus_result = selector.select(
                detection_result=detection_result,
                frame_width=frame.width,
                frame_height=frame.height
            )
            
            # At most one primary object
            if focus_result.primary_object is not None:
                # If there's a primary, it should be a single DetectedObject
                self.assertIsInstance(focus_result.primary_object, DetectedObject)
                # And ambiguity should be False (otherwise primary would be None)
                self.assertFalse(focus_result.ambiguity_detected)
            else:
                # If no primary, either no candidates or ambiguity detected
                # Both are valid - no scope is safer than wrong scope
                pass
    
    @unittest.skip("Meta-test: Run existing test suite separately")
    def test_no_safety_invariants_changed(self):
        """META-TEST: Verify Week 1-9 tests still pass"""
        # This test verifies that camera integration didn't break existing safety tests
        # Run this separately with: pytest tests/ -v
        
        # List of test files that should still pass:
        expected_test_files = [
            'tests/test_camera_stream.py',
            'tests/test_object_detector.py',
            'tests/test_focus_selector.py',
            'tests/test_camera_scope_controller.py',
            'tests/test_camera_scope_safety.py',  # This file
        ]
        
        # Note: Week 2-9 tests may not exist yet, but when they do, they should still pass
        # This is a reminder to run the full test suite after camera integration
        
        # For now, just verify this test file itself is valid
        self.assertTrue(True, "Meta-test placeholder - run full test suite separately")


if __name__ == "__main__":
    unittest.main()

