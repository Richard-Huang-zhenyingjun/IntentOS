"""Tests for CameraScopeController module."""

import unittest
from vision.camera_scope_controller import (
    CameraScopeController,
    CameraScopeSignal,
    CameraScopeState
)
from vision.focus_selector import FocusResult
from vision.object_detector import DetectedObject
from intent_core.schema import SystemState


class TestCameraScopeController(unittest.TestCase):
    """Test CameraScopeController functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'min_scope_confidence': 0.6
        }
        self.controller = CameraScopeController(self.config)
    
    def test_initialization(self):
        """Test controller initialization."""
        self.assertEqual(self.controller.min_scope_confidence, 0.6)
        state = self.controller.get_state()
        self.assertEqual(state.frames_processed, 0)
        self.assertEqual(state.scopes_created, 0)
        self.assertEqual(state.ambiguities_detected, 0)
        self.assertIsNone(state.current_scope)
    
    def test_process_ambiguity(self):
        """Test processing ambiguity case."""
        focus_result = FocusResult(
            primary_object=None,
            ambiguity_detected=True,
            reason="ambiguous selection: top two candidates too close",
            candidates_considered=2,
            runner_up_object=None,
            score_margin=0.1,
            timestamp=0.0
        )
        
        signal = self.controller.process_frame(focus_result, frame_id=0, timestamp=1.0)
        
        self.assertIsInstance(signal, CameraScopeSignal)
        self.assertIsNone(signal.scoped_object_id)
        self.assertTrue(signal.ambiguity_detected)
        self.assertEqual(signal.suggested_state, SystemState.PAUSED)
        self.assertIn("ambiguous", signal.focus_reason.lower())
        
        # Check state updated
        state = self.controller.get_state()
        self.assertEqual(state.frames_processed, 1)
        self.assertEqual(state.ambiguities_detected, 1)
        self.assertEqual(state.scopes_created, 0)
    
    def test_process_no_object(self):
        """Test processing no object case."""
        focus_result = FocusResult(
            primary_object=None,
            ambiguity_detected=False,
            reason="no objects detected above confidence threshold",
            candidates_considered=0,
            runner_up_object=None,
            score_margin=0.0,
            timestamp=0.0
        )
        
        signal = self.controller.process_frame(focus_result, frame_id=0, timestamp=1.0)
        
        self.assertIsInstance(signal, CameraScopeSignal)
        self.assertIsNone(signal.scoped_object_id)
        self.assertFalse(signal.ambiguity_detected)
        self.assertEqual(signal.suggested_state, SystemState.IDLE)
        self.assertIn("no objects", signal.focus_reason.lower())
        
        # Check state updated
        state = self.controller.get_state()
        self.assertEqual(state.frames_processed, 1)
        self.assertEqual(state.ambiguities_detected, 0)
        self.assertEqual(state.scopes_created, 0)
    
    def test_process_low_confidence(self):
        """Test processing low confidence object."""
        obj = DetectedObject(
            detection_id="test-1",
            label="lamp",
            bbox=(100, 100, 80, 80),
            confidence=0.5,  # Below min_scope_confidence (0.6)
            center_point=(140, 140),
            area=6400,
            frame_id=0
        )
        
        focus_result = FocusResult(
            primary_object=obj,
            ambiguity_detected=False,
            reason="selected lamp",
            candidates_considered=1,
            runner_up_object=None,
            score_margin=0.0,
            timestamp=0.0
        )
        
        signal = self.controller.process_frame(focus_result, frame_id=0, timestamp=1.0)
        
        self.assertIsInstance(signal, CameraScopeSignal)
        self.assertEqual(signal.scoped_object_id, "test-1")
        self.assertEqual(signal.object_label, "lamp")
        self.assertEqual(signal.confidence, 0.5)
        self.assertFalse(signal.ambiguity_detected)
        self.assertEqual(signal.suggested_state, SystemState.IDLE)  # Low confidence → IDLE
        self.assertIn("low confidence", signal.focus_reason.lower())
        
        # Check state updated
        state = self.controller.get_state()
        self.assertEqual(state.frames_processed, 1)
        self.assertEqual(state.scopes_created, 0)  # Not counted as scope (low confidence)
    
    def test_process_confident_scope(self):
        """Test processing confident scope."""
        obj = DetectedObject(
            detection_id="test-1",
            label="lamp",
            bbox=(100, 100, 80, 80),
            confidence=0.8,  # Above min_scope_confidence (0.6)
            center_point=(140, 140),
            area=6400,
            frame_id=0
        )
        
        focus_result = FocusResult(
            primary_object=obj,
            ambiguity_detected=False,
            reason="selected lamp",
            candidates_considered=1,
            runner_up_object=None,
            score_margin=0.0,
            timestamp=0.0
        )
        
        signal = self.controller.process_frame(focus_result, frame_id=0, timestamp=1.0)
        
        self.assertIsInstance(signal, CameraScopeSignal)
        self.assertEqual(signal.scoped_object_id, "test-1")
        self.assertEqual(signal.object_label, "lamp")
        self.assertEqual(signal.confidence, 0.8)
        self.assertEqual(signal.bbox, (100, 100, 80, 80))
        self.assertFalse(signal.ambiguity_detected)
        self.assertEqual(signal.suggested_state, SystemState.SCOPED)  # Confident → SCOPED
        self.assertIn("focused on", signal.focus_reason.lower())
        
        # Check state updated
        state = self.controller.get_state()
        self.assertEqual(state.frames_processed, 1)
        self.assertEqual(state.scopes_created, 1)  # Counted as scope
    
    def test_get_state_readonly(self):
        """Test that get_state returns a copy (read-only)."""
        # Process a frame
        obj = DetectedObject(
            detection_id="test-1",
            label="lamp",
            bbox=(100, 100, 80, 80),
            confidence=0.8,
            center_point=(140, 140),
            area=6400,
            frame_id=0
        )
        
        focus_result = FocusResult(
            primary_object=obj,
            ambiguity_detected=False,
            reason="selected lamp",
            candidates_considered=1,
            runner_up_object=None,
            score_margin=0.0,
            timestamp=0.0
        )
        
        self.controller.process_frame(focus_result, frame_id=0, timestamp=1.0)
        
        # Get state
        state1 = self.controller.get_state()
        
        # Modify returned state (should not affect internal state)
        state1.frames_processed = 999
        
        # Get state again (should be unchanged)
        state2 = self.controller.get_state()
        self.assertEqual(state2.frames_processed, 1)  # Still 1, not 999
    
    def test_reset(self):
        """Test reset functionality."""
        # Process some frames
        focus_result = FocusResult(
            primary_object=None,
            ambiguity_detected=False,
            reason="no objects",
            candidates_considered=0,
            runner_up_object=None,
            score_margin=0.0,
            timestamp=0.0
        )
        
        self.controller.process_frame(focus_result, frame_id=0, timestamp=1.0)
        self.controller.process_frame(focus_result, frame_id=1, timestamp=2.0)
        
        # Verify state changed
        state_before = self.controller.get_state()
        self.assertEqual(state_before.frames_processed, 2)
        
        # Reset
        self.controller.reset()
        
        # Verify state reset
        state_after = self.controller.get_state()
        self.assertEqual(state_after.frames_processed, 0)
        self.assertEqual(state_after.scopes_created, 0)
        self.assertEqual(state_after.ambiguities_detected, 0)
        self.assertIsNone(state_after.current_scope)
    
    def test_multiple_frames(self):
        """Test processing multiple frames."""
        # Frame 1: No object
        focus_result1 = FocusResult(
            primary_object=None,
            ambiguity_detected=False,
            reason="no objects",
            candidates_considered=0,
            runner_up_object=None,
            score_margin=0.0,
            timestamp=0.0
        )
        
        signal1 = self.controller.process_frame(focus_result1, frame_id=0, timestamp=1.0)
        self.assertEqual(signal1.suggested_state, SystemState.IDLE)
        
        # Frame 2: Ambiguity
        focus_result2 = FocusResult(
            primary_object=None,
            ambiguity_detected=True,
            reason="ambiguous",
            candidates_considered=2,
            runner_up_object=None,
            score_margin=0.1,
            timestamp=0.0
        )
        
        signal2 = self.controller.process_frame(focus_result2, frame_id=1, timestamp=2.0)
        self.assertEqual(signal2.suggested_state, SystemState.PAUSED)
        
        # Frame 3: Confident scope
        obj = DetectedObject(
            detection_id="test-1",
            label="lamp",
            bbox=(100, 100, 80, 80),
            confidence=0.8,
            center_point=(140, 140),
            area=6400,
            frame_id=2
        )
        
        focus_result3 = FocusResult(
            primary_object=obj,
            ambiguity_detected=False,
            reason="selected lamp",
            candidates_considered=1,
            runner_up_object=None,
            score_margin=0.0,
            timestamp=0.0
        )
        
        signal3 = self.controller.process_frame(focus_result3, frame_id=2, timestamp=3.0)
        self.assertEqual(signal3.suggested_state, SystemState.SCOPED)
        
        # Check final state
        state = self.controller.get_state()
        self.assertEqual(state.frames_processed, 3)
        self.assertEqual(state.ambiguities_detected, 1)
        self.assertEqual(state.scopes_created, 1)
        self.assertEqual(state.last_update, 3.0)


if __name__ == "__main__":
    unittest.main()

