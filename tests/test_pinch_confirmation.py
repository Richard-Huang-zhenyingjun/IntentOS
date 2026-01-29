"""Week 4 Tests: Pinch gesture confirmation."""

import unittest
from vision.pinch_stability import PinchStability, PinchState
from vision.pinch_detector import PinchObservation
from vision.gesture_confirm_controller import GestureConfirmController
from intent_core.schema import SystemState, IntentType
from affordances.affordance_schema import AffordanceSet, AffordanceOption, AffordanceType, AffordanceRisk, ObjectCategory


class TestPinchConfirmation(unittest.TestCase):
    """Week 4 tests: pinch gesture confirmation"""
    
    def test_short_pinch_no_confirm(self):
        """INVARIANT: Pinch < stable_frames does not confirm"""
        config = {'stable_frames_required': 6}
        stability = PinchStability(config)
        
        # Create pinch observation
        obs = PinchObservation(
            pinching=True,
            distance=0.02,
            distance_pixels=20,
            confidence=0.9,
            timestamp=1.0,
            frame_id=1,
            thumb_pos=(0.4, 0.5),
            index_pos=(0.42, 0.5),
            threshold_used=0.04
        )
        
        # Hold for 5 frames (< 6 required)
        for i in range(5):
            state = stability.step(obs, timestamp=float(i))
            self.assertFalse(state.just_confirmed)
            self.assertFalse(state.stable)
    
    def test_stable_pinch_confirms(self):
        """INVARIANT: Pinch >= stable_frames triggers confirmation"""
        config = {'stable_frames_required': 6}
        stability = PinchStability(config)
        
        obs = PinchObservation(
            pinching=True,
            distance=0.02,
            distance_pixels=20,
            confidence=0.9,
            timestamp=1.0,
            frame_id=1,
            thumb_pos=(0.4, 0.5),
            index_pos=(0.42, 0.5),
            threshold_used=0.04
        )
        
        # Hold for 6 frames
        state = None
        for i in range(6):
            state = stability.step(obs, timestamp=float(i))
        
        # 6th frame should confirm
        self.assertTrue(state.just_confirmed)
        self.assertTrue(state.stable)
        self.assertTrue(state.confirmed)
    
    def test_confirmation_edge_triggered(self):
        """INVARIANT: Confirmation happens once per gesture"""
        config = {'stable_frames_required': 3}
        stability = PinchStability(config)
        
        obs = PinchObservation(
            pinching=True,
            distance=0.02,
            distance_pixels=20,
            confidence=0.9,
            timestamp=1.0,
            frame_id=1,
            thumb_pos=(0.4, 0.5),
            index_pos=(0.42, 0.5),
            threshold_used=0.04
        )
        
        # Hold for 10 frames
        confirmations = 0
        for i in range(10):
            state = stability.step(obs, timestamp=float(i))
            if state.just_confirmed:
                confirmations += 1
        
        # Should only confirm once
        self.assertEqual(confirmations, 1)
    
    def test_pinch_no_scope_blocks(self):
        """INVARIANT: Pinch without scope is blocked"""
        config = {'require_stable_scope': True}
        controller = GestureConfirmController(config)
        
        # Create confirmed pinch state
        pinch_state = PinchState(
            stable=True,
            confirmed=True,
            frames_held=6,
            frames_released=0,
            just_confirmed=True,
            timestamp=1.0,
            reason="CONFIRMED"
        )
        
        # No scope
        signal = controller.process(
            pinch_state=pinch_state,
            system_state=SystemState.IDLE,
            scoped_object_id=None,  # No scope
            affordances=None,
            scope_age_frames=0,
            ambiguity_detected=False,
            frame_id=1,
            timestamp=1.0
        )
        
        self.assertFalse(signal.confirmed)
        self.assertTrue(signal.blocked)
        self.assertIn("scoped object", signal.block_reason.lower())
    
    def test_pinch_during_ambiguity_blocks(self):
        """INVARIANT: Pinch during ambiguity is blocked"""
        config = {'block_during_ambiguity': True}
        controller = GestureConfirmController(config)
        
        pinch_state = PinchState(
            stable=True,
            confirmed=True,
            frames_held=6,
            frames_released=0,
            just_confirmed=True,
            timestamp=1.0,
            reason="CONFIRMED"
        )
        
        # Create affordance set
        affordances = AffordanceSet(
            object_id="track_001",
            object_label="lamp",
            category=ObjectCategory.LAMP,
            category_confidence=0.9,
            options=[
                AffordanceOption(
                    affordance_type=AffordanceType.TOGGLE_POWER,
                    title="Toggle Power",
                    description="Turn lamp on/off",
                    risk=AffordanceRisk.LOW,
                    requires_confirmation=True,
                    reason="test",
                    confidence=0.9
                )
            ],
            blocked=False,
            block_reason="",
            timestamp=1.0,
            frame_id=1
        )
        
        signal = controller.process(
            pinch_state=pinch_state,
            system_state=SystemState.SCOPED,
            scoped_object_id="track_001",
            affordances=affordances,
            scope_age_frames=10,
            ambiguity_detected=True,  # Ambiguity present
            frame_id=1,
            timestamp=1.0
        )
        
        self.assertFalse(signal.confirmed)
        self.assertTrue(signal.blocked)
        self.assertIn("ambiguity", signal.block_reason.lower())
    
    def test_pinch_while_paused_blocks(self):
        """INVARIANT: Pinch during PAUSED state is blocked"""
        config = {'block_during_pause': True}
        controller = GestureConfirmController(config)
        
        pinch_state = PinchState(
            stable=True,
            confirmed=True,
            frames_held=6,
            frames_released=0,
            just_confirmed=True,
            timestamp=1.0,
            reason="CONFIRMED"
        )
        
        signal = controller.process(
            pinch_state=pinch_state,
            system_state=SystemState.PAUSED,  # System paused
            scoped_object_id="track_001",
            affordances=None,
            scope_age_frames=10,
            ambiguity_detected=False,
            frame_id=1,
            timestamp=1.0
        )
        
        self.assertFalse(signal.confirmed)
        self.assertTrue(signal.blocked)
        self.assertIn("paused", signal.block_reason.lower())
    
    def test_valid_pinch_generates_confirm_intent(self):
        """INVARIANT: Valid pinch creates CONFIRM intent"""
        config = {}
        controller = GestureConfirmController(config)
        
        pinch_state = PinchState(
            stable=True,
            confirmed=True,
            frames_held=6,
            frames_released=0,
            just_confirmed=True,
            timestamp=1.0,
            reason="CONFIRMED"
        )
        
        affordances = AffordanceSet(
            object_id="track_001",
            object_label="lamp",
            category=ObjectCategory.LAMP,
            category_confidence=0.9,
            options=[
                AffordanceOption(
                    affordance_type=AffordanceType.TOGGLE_POWER,
                    title="Toggle Power",
                    description="Turn lamp on/off",
                    risk=AffordanceRisk.LOW,
                    requires_confirmation=True,
                    reason="test",
                    confidence=0.9
                )
            ],
            blocked=False,
            block_reason="",
            timestamp=1.0,
            frame_id=1
        )
        
        signal = controller.process(
            pinch_state=pinch_state,
            system_state=SystemState.SCOPED,
            scoped_object_id="track_001",
            affordances=affordances,
            scope_age_frames=10,
            ambiguity_detected=False,
            frame_id=1,
            timestamp=1.0
        )
        
        self.assertTrue(signal.confirmed)
        self.assertFalse(signal.blocked)
        self.assertIsNotNone(signal.intent)
        self.assertEqual(signal.intent.type, IntentType.CONFIRM)
        self.assertEqual(signal.intent.source, "gesture_pinch")
    
    def test_pinch_release_resets(self):
        """INVARIANT: Releasing pinch resets confirmation state"""
        config = {'stable_frames_required': 3, 'release_frames_required': 2}
        stability = PinchStability(config)
        
        obs = PinchObservation(
            pinching=True,
            distance=0.02,
            distance_pixels=20,
            confidence=0.9,
            timestamp=1.0,
            frame_id=1,
            thumb_pos=(0.4, 0.5),
            index_pos=(0.42, 0.5),
            threshold_used=0.04
        )
        
        # Hold for 3 frames to confirm
        for i in range(3):
            state = stability.step(obs, timestamp=float(i))
        
        self.assertTrue(state.confirmed)
        
        # Release for 2 frames
        no_obs = None
        for i in range(2):
            state = stability.step(no_obs, timestamp=float(i + 3))
        
        # Should be reset
        self.assertFalse(state.confirmed)
        self.assertEqual(state.frames_held, 0)
    
    def test_pinch_timeout_resets(self):
        """INVARIANT: Holding pinch too long triggers timeout"""
        config = {'stable_frames_required': 3, 'max_hold_time_seconds': 1.0}
        stability = PinchStability(config)
        
        obs = PinchObservation(
            pinching=True,
            distance=0.02,
            distance_pixels=20,
            confidence=0.9,
            timestamp=0.0,
            frame_id=1,
            thumb_pos=(0.4, 0.5),
            index_pos=(0.42, 0.5),
            threshold_used=0.04
        )
        
        # Confirm first
        state = None
        for i in range(3):
            state = stability.step(obs, timestamp=float(i) * 0.1)
        
        self.assertTrue(state.confirmed)
        
        # Continue holding past timeout
        state = stability.step(obs, timestamp=1.5)  # Past 1.0 second timeout
        
        # Should reset due to timeout
        self.assertFalse(state.confirmed)
        self.assertIn("timeout", state.reason.lower())
    
    def test_pinch_no_affordances_blocks(self):
        """INVARIANT: Pinch without affordances is blocked"""
        config = {'require_affordances': True}
        controller = GestureConfirmController(config)
        
        pinch_state = PinchState(
            stable=True,
            confirmed=True,
            frames_held=6,
            frames_released=0,
            just_confirmed=True,
            timestamp=1.0,
            reason="CONFIRMED"
        )
        
        # No affordances
        signal = controller.process(
            pinch_state=pinch_state,
            system_state=SystemState.SCOPED,
            scoped_object_id="track_001",
            affordances=None,  # No affordances
            scope_age_frames=10,
            ambiguity_detected=False,
            frame_id=1,
            timestamp=1.0
        )
        
        self.assertFalse(signal.confirmed)
        self.assertTrue(signal.blocked)
        self.assertIn("affordance", signal.block_reason.lower())
    
    def test_pinch_scope_too_new_blocks(self):
        """INVARIANT: Pinch with scope too new is blocked"""
        config = {'min_scope_age_frames': 5}
        controller = GestureConfirmController(config)
        
        pinch_state = PinchState(
            stable=True,
            confirmed=True,
            frames_held=6,
            frames_released=0,
            just_confirmed=True,
            timestamp=1.0,
            reason="CONFIRMED"
        )
        
        affordances = AffordanceSet(
            object_id="track_001",
            object_label="lamp",
            category=ObjectCategory.LAMP,
            category_confidence=0.9,
            options=[
                AffordanceOption(
                    affordance_type=AffordanceType.TOGGLE_POWER,
                    title="Toggle Power",
                    description="Turn lamp on/off",
                    risk=AffordanceRisk.LOW,
                    requires_confirmation=True,
                    reason="test",
                    confidence=0.9
                )
            ],
            blocked=False,
            block_reason="",
            timestamp=1.0,
            frame_id=1
        )
        
        # Scope only 2 frames old (< 5 required)
        signal = controller.process(
            pinch_state=pinch_state,
            system_state=SystemState.SCOPED,
            scoped_object_id="track_001",
            affordances=affordances,
            scope_age_frames=2,  # Too new
            ambiguity_detected=False,
            frame_id=1,
            timestamp=1.0
        )
        
        self.assertFalse(signal.confirmed)
        self.assertTrue(signal.blocked)
        self.assertIn("too new", signal.block_reason.lower() or "new" in signal.block_reason.lower())
    
    def test_pinch_during_executing_blocks(self):
        """INVARIANT: Pinch during EXECUTING state is blocked"""
        config = {}
        controller = GestureConfirmController(config)
        
        pinch_state = PinchState(
            stable=True,
            confirmed=True,
            frames_held=6,
            frames_released=0,
            just_confirmed=True,
            timestamp=1.0,
            reason="CONFIRMED"
        )
        
        signal = controller.process(
            pinch_state=pinch_state,
            system_state=SystemState.EXECUTING,  # Already executing
            scoped_object_id="track_001",
            affordances=None,
            scope_age_frames=10,
            ambiguity_detected=False,
            frame_id=1,
            timestamp=1.0
        )
        
        self.assertFalse(signal.confirmed)
        self.assertTrue(signal.blocked)
        self.assertIn("executing", signal.block_reason.lower())
    
    def test_pinch_not_just_confirmed_ignored(self):
        """INVARIANT: Only just_confirmed=True triggers processing"""
        config = {}
        controller = GestureConfirmController(config)
        
        # Pinch state that's stable but not just_confirmed
        pinch_state = PinchState(
            stable=True,
            confirmed=True,
            frames_held=10,
            frames_released=0,
            just_confirmed=False,  # Not just confirmed
            timestamp=1.0,
            reason="holding: 10 frames"
        )
        
        signal = controller.process(
            pinch_state=pinch_state,
            system_state=SystemState.SCOPED,
            scoped_object_id="track_001",
            affordances=None,
            scope_age_frames=10,
            ambiguity_detected=False,
            frame_id=1,
            timestamp=1.0
        )
        
        # Should not generate intent (not blocked, just ignored)
        self.assertFalse(signal.confirmed)
        self.assertFalse(signal.blocked)
        self.assertIsNone(signal.intent)


if __name__ == "__main__":
    unittest.main()




