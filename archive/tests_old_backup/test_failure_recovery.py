"""
Failure Recovery Tests - Week 7

Tests for:
- Object loss detection
- Hand loss detection
- Ambiguity during confirmation
- Recovery controller
- Pause/resume behavior
"""

import pytest
from vision.object_loss_detector import ObjectLossDetector
from vision.hand_loss_detector import HandLossDetector
from vision.ambiguity_during_confirm_detector import AmbiguityDuringConfirmDetector
from vision.recovery_controller import RecoveryController, PauseTrigger
from vision.object_tracker import ObjectTracker
from vision.candidate_ranker import RankedCandidates, ScoredCandidate
from vision.hand_detector import HandDetectionResult
from vision.tracking_schema import TrackedObject
from intent_core.schema import SystemState


class TestObjectLossDetection:
    """Test object loss during critical states"""
    
    def test_object_loss_during_scoped_triggers_pause(self):
        """INVARIANT: Object loss during SCOPED → pause"""
        config = {
            'object_loss': {
                'pause_on_loss': True,
                'loss_grace_frames': 2
            }
        }
        
        detector = ObjectLossDetector(config)
        
        # Create tracker
        tracker = ObjectTracker({'track_max_age_frames': 5}, seed=42)
        
        # Track an object
        from vision.camera_stream import DetectedObject
        detection = DetectedObject(
            detection_id="det_001",
            label="lamp",
            bbox=(100, 100, 50, 50),
            confidence=0.8
        )
        result = tracker.update([detection], timestamp=1.0)
        
        scoped_id = result.tracked_objects[0].track_id
        
        # Object present - no pause
        should_pause, reason = detector.check(
            scoped_object_id=scoped_id,
            tracker=tracker,
            system_state=SystemState.SCOPED,
            timestamp=1.0
        )
        assert should_pause == False
        
        # Object disappears - update tracker with no detections
        for i in range(6):  # More than track_max_age_frames
            tracker.update([], timestamp=2.0 + i)
        
        # Check again - object should be lost
        should_pause, reason = detector.check(
            scoped_object_id=scoped_id,
            tracker=tracker,
            system_state=SystemState.SCOPED,
            timestamp=8.0
        )
        
        # Should trigger pause (after grace period)
        assert should_pause == True
        assert "lost" in reason.lower()
    
    def test_object_loss_grace_period(self):
        """INVARIANT: Brief loss within grace period doesn't trigger pause"""
        config = {
            'object_loss': {
                'pause_on_loss': True,
                'loss_grace_frames': 3  # 3 frame grace period
            }
        }
        
        detector = ObjectLossDetector(config)
        
        # Create tracker
        tracker = ObjectTracker({'track_max_age_frames': 10}, seed=42)
        
        # Track an object
        from vision.camera_stream import DetectedObject
        detection = DetectedObject(
            detection_id="det_001",
            label="lamp",
            bbox=(100, 100, 50, 50),
            confidence=0.8
        )
        result = tracker.update([detection], timestamp=1.0)
        scoped_id = result.tracked_objects[0].track_id
        
        # Object disappears briefly (within grace period)
        tracker.update([], timestamp=2.0)  # Frame 1 missing
        
        should_pause1, _ = detector.check(
            scoped_object_id=scoped_id,
            tracker=tracker,
            system_state=SystemState.SCOPED,
            timestamp=2.0
        )
        assert should_pause1 == False  # Within grace period
        
        tracker.update([], timestamp=3.0)  # Frame 2 missing
        
        should_pause2, _ = detector.check(
            scoped_object_id=scoped_id,
            tracker=tracker,
            system_state=SystemState.SCOPED,
            timestamp=3.0
        )
        assert should_pause2 == False  # Still within grace period
    
    def test_object_loss_only_during_vulnerable_states(self):
        """INVARIANT: Object loss only checked during vulnerable states"""
        config = {
            'object_loss': {
                'pause_on_loss': True,
                'loss_grace_frames': 1
            }
        }
        
        detector = ObjectLossDetector(config)
        tracker = ObjectTracker({'track_max_age_frames': 5}, seed=42)
        
        # Object doesn't exist in tracker
        should_pause, _ = detector.check(
            scoped_object_id="nonexistent_id",
            tracker=tracker,
            system_state=SystemState.IDLE,  # Not vulnerable
            timestamp=1.0
        )
        
        # Should NOT pause during IDLE
        assert should_pause == False


class TestHandLossDetection:
    """Test hand loss during confirmation"""
    
    def test_hand_loss_during_confirming_triggers_pause(self):
        """INVARIANT: Hand loss during CONFIRMING → pause"""
        config = {
            'hand_loss': {
                'pause_during_confirm': True,
                'loss_grace_frames': 2
            }
        }
        
        detector = HandLossDetector(config)
        
        # Hand not detected
        hand_result = HandDetectionResult(
            detected=False,
            confidence=0.0,
            hand_position=None,
            failure_reason="Hand moved out of frame"
        )
        
        should_pause, reason = detector.check(
            hand_detection=hand_result,
            system_state=SystemState.CONFIRMING,
            timestamp=1.0
        )
        
        # First frame - within grace period
        assert should_pause == False
        
        # Continue no hand detection
        should_pause2, reason2 = detector.check(
            hand_detection=hand_result,
            system_state=SystemState.CONFIRMING,
            timestamp=2.0
        )
        assert should_pause2 == False  # Still in grace
        
        # Third frame - grace period expired
        should_pause3, reason3 = detector.check(
            hand_detection=hand_result,
            system_state=SystemState.CONFIRMING,
            timestamp=3.0
        )
        assert should_pause3 == True
        assert "hand" in reason3.lower()
    
    def test_hand_present_resets_grace_counter(self):
        """INVARIANT: Hand reappearing resets grace counter"""
        config = {
            'hand_loss': {
                'pause_during_confirm': True,
                'loss_grace_frames': 2
            }
        }
        
        detector = HandLossDetector(config)
        
        # Hand missing
        hand_missing = HandDetectionResult(
            detected=False,
            confidence=0.0,
            hand_position=None,
            failure_reason="Hand not visible"
        )
        
        detector.check(hand_missing, SystemState.CONFIRMING, 1.0)
        detector.check(hand_missing, SystemState.CONFIRMING, 2.0)
        
        # Hand reappears
        hand_present = HandDetectionResult(
            detected=True,
            confidence=0.9,
            hand_position=(320, 240),
            failure_reason=None
        )
        
        should_pause, _ = detector.check(hand_present, SystemState.CONFIRMING, 3.0)
        assert should_pause == False
        
        # Counter should be reset - hand goes missing again
        detector.check(hand_missing, SystemState.CONFIRMING, 4.0)
        should_pause2, _ = detector.check(hand_missing, SystemState.CONFIRMING, 5.0)
        
        # Should still be in grace period (counter was reset)
        assert should_pause2 == False


class TestAmbiguityDuringConfirm:
    """Test ambiguity detection during critical states"""
    
    def test_ambiguity_during_confirming_triggers_pause(self):
        """INVARIANT: Ambiguity during CONFIRMING → immediate pause"""
        config = {
            'ambiguity_during_confirm': {
                'pause_on_ambiguity': True
            }
        }
        
        detector = AmbiguityDuringConfirmDetector(config)
        
        # Create ambiguous ranking
        obj1 = TrackedObject(
            track_id="track_001",
            label="lamp",
            bbox=(100, 100, 50, 50),
            confidence=0.8,
            center_point=(125, 125),
            area=2500,
            age_frames=10,
            hits=10,
            confirmed=True
        )
        
        ranked = RankedCandidates(
            primary_choice=None,
            primary_candidate=None,
            runner_up=obj1,
            runner_up_candidate=None,
            ambiguity_detected=True,
            margin=0.05,
            is_clear_choice=False,
            candidates=[],
            num_candidates=2,
            reason="Two objects competing",
            timestamp=1.0,
            frame_id=1
        )
        
        should_pause, reason = detector.check(
            ranked_candidates=ranked,
            system_state=SystemState.CONFIRMING,
            timestamp=1.0
        )
        
        # Should pause immediately (no grace period for ambiguity)
        assert should_pause == True
        assert "ambiguity" in reason.lower()
    
    def test_ambiguity_during_idle_not_checked(self):
        """INVARIANT: Ambiguity only matters during vulnerable states"""
        config = {
            'ambiguity_during_confirm': {
                'pause_on_ambiguity': True
            }
        }
        
        detector = AmbiguityDuringConfirmDetector(config)
        
        # Ambiguous ranking
        ranked = RankedCandidates(
            primary_choice=None,
            primary_candidate=None,
            runner_up=None,
            runner_up_candidate=None,
            ambiguity_detected=True,
            margin=0.05,
            is_clear_choice=False,
            candidates=[],
            num_candidates=2,
            reason="Ambiguous",
            timestamp=1.0,
            frame_id=1
        )
        
        should_pause, _ = detector.check(
            ranked_candidates=ranked,
            system_state=SystemState.IDLE,  # Not vulnerable
            timestamp=1.0
        )
        
        # Should NOT pause during IDLE
        assert should_pause == False


class TestRecoveryController:
    """Test recovery controller orchestration"""
    
    def test_recovery_plan_clears_state_on_pause(self):
        """INVARIANT: Pause triggers state clearing"""
        config = {
            'object_loss': {
                'pause_on_loss': True,
                'loss_grace_frames': 1
            },
            'hand_loss': {
                'pause_during_confirm': True,
                'loss_grace_frames': 1
            },
            'ambiguity_during_confirm': {
                'pause_on_ambiguity': True
            },
            'recovery': {
                'require_rescope_after_pause': True,
                'clear_confirmation_on_pause': True
            }
        }
        
        controller = RecoveryController(config)
        
        # Create ambiguous situation during confirm
        ranked = RankedCandidates(
            primary_choice=None,
            primary_candidate=None,
            runner_up=None,
            runner_up_candidate=None,
            ambiguity_detected=True,
            margin=0.05,
            is_clear_choice=False,
            candidates=[],
            num_candidates=2,
            reason="Ambiguous",
            timestamp=1.0,
            frame_id=1
        )
        
        hand_result = HandDetectionResult(
            detected=True,
            confidence=0.9,
            hand_position=(320, 240),
            failure_reason=None
        )
        
        tracker = ObjectTracker({}, seed=42)
        
        plan = controller.check_and_plan(
            scoped_object_id="track_001",
            ranked_candidates=ranked,
            hand_detection=hand_result,
            tracker=tracker,
            system_state=SystemState.CONFIRMING,
            timestamp=1.0
        )
        
        # Should pause
        assert plan.should_pause == True
        assert plan.trigger == PauseTrigger.AMBIGUITY_DURING_CONFIRM
        
        # Should clear state
        assert plan.clear_scope == True
        assert plan.clear_confirmation == True
        assert plan.clear_execution == True
    
    def test_recovery_controller_priority_order(self):
        """INVARIANT: Failures checked in priority order"""
        config = {
            'object_loss': {
                'pause_on_loss': True,
                'loss_grace_frames': 0
            },
            'hand_loss': {
                'pause_during_confirm': True,
                'loss_grace_frames': 0
            },
            'ambiguity_during_confirm': {
                'pause_on_ambiguity': True
            },
            'recovery': {
                'require_rescope_after_pause': True,
                'clear_confirmation_on_pause': True
            }
        }
        
        controller = RecoveryController(config)
        
        # Create scenario with multiple failures
        # 1. Object loss
        # 2. Hand loss
        # 3. Ambiguity
        
        ranked = RankedCandidates(
            primary_choice=None,
            primary_candidate=None,
            runner_up=None,
            runner_up_candidate=None,
            ambiguity_detected=True,
            margin=0.05,
            is_clear_choice=False,
            candidates=[],
            num_candidates=2,
            reason="Ambiguous",
            timestamp=1.0,
            frame_id=1
        )
        
        hand_result = HandDetectionResult(
            detected=False,
            confidence=0.0,
            hand_position=None,
            failure_reason="Hand lost"
        )
        
        tracker = ObjectTracker({'track_max_age_frames': 1}, seed=42)
        
        # Object doesn't exist (lost)
        plan = controller.check_and_plan(
            scoped_object_id="nonexistent_track",
            ranked_candidates=ranked,
            hand_detection=hand_result,
            tracker=tracker,
            system_state=SystemState.EXECUTING,
            timestamp=1.0
        )
        
        # Should trigger first failure in priority order (object loss)
        assert plan.should_pause == True
        # Priority order: object_loss, hand_loss, ambiguity
        assert plan.trigger == PauseTrigger.OBJECT_LOSS
    
    def test_clear_pause_resets_all_detectors(self):
        """INVARIANT: clear_pause resets all failure detectors"""
        config = {
            'object_loss': {'pause_on_loss': True, 'loss_grace_frames': 1},
            'hand_loss': {'pause_during_confirm': True, 'loss_grace_frames': 1},
            'ambiguity_during_confirm': {'pause_on_ambiguity': True},
            'recovery': {
                'require_rescope_after_pause': True,
                'clear_confirmation_on_pause': True
            }
        }
        
        controller = RecoveryController(config)
        
        # Trigger a pause
        ranked = RankedCandidates(
            primary_choice=None,
            primary_candidate=None,
            runner_up=None,
            runner_up_candidate=None,
            ambiguity_detected=True,
            margin=0.05,
            is_clear_choice=False,
            candidates=[],
            num_candidates=2,
            reason="Ambiguous",
            timestamp=1.0,
            frame_id=1
        )
        
        hand_result = HandDetectionResult(detected=True, confidence=0.9, 
                                         hand_position=(320, 240), failure_reason=None)
        tracker = ObjectTracker({}, seed=42)
        
        plan = controller.check_and_plan(
            scoped_object_id="track_001",
            ranked_candidates=ranked,
            hand_detection=hand_result,
            tracker=tracker,
            system_state=SystemState.CONFIRMING,
            timestamp=1.0
        )
        
        assert controller.currently_paused == True
        
        # Clear pause
        controller.clear_pause()
        
        # Should reset
        assert controller.currently_paused == False
        assert controller.pause_reason is None


class TestRecoveryInvariants:
    """Test high-level recovery invariants"""
    
    def test_pause_always_clears_confirmation(self):
        """INVARIANT: Pause → confirmation cleared (must re-confirm)"""
        config = {
            'object_loss': {'pause_on_loss': True, 'loss_grace_frames': 0},
            'hand_loss': {'pause_during_confirm': True, 'loss_grace_frames': 0},
            'ambiguity_during_confirm': {'pause_on_ambiguity': True},
            'recovery': {
                'require_rescope_after_pause': True,
                'clear_confirmation_on_pause': True
            }
        }
        
        controller = RecoveryController(config)
        
        # Any failure during confirmation
        ranked = RankedCandidates(
            primary_choice=None,
            primary_candidate=None,
            runner_up=None,
            runner_up_candidate=None,
            ambiguity_detected=True,
            margin=0.05,
            is_clear_choice=False,
            candidates=[],
            num_candidates=2,
            reason="Ambiguous",
            timestamp=1.0,
            frame_id=1
        )
        
        hand_result = HandDetectionResult(detected=True, confidence=0.9, 
                                         hand_position=(320, 240), failure_reason=None)
        tracker = ObjectTracker({}, seed=42)
        
        plan = controller.check_and_plan(
            scoped_object_id="track_001",
            ranked_candidates=ranked,
            hand_detection=hand_result,
            tracker=tracker,
            system_state=SystemState.CONFIRMING,
            timestamp=1.0
        )
        
        # Must clear confirmation
        assert plan.clear_confirmation == True
    
    def test_no_execution_during_any_pause_condition(self):
        """META-INVARIANT: No execution during any pause condition"""
        config = {
            'object_loss': {'pause_on_loss': True, 'loss_grace_frames': 0},
            'hand_loss': {'pause_during_confirm': True, 'loss_grace_frames': 0},
            'ambiguity_during_confirm': {'pause_on_ambiguity': True},
            'recovery': {
                'require_rescope_after_pause': True,
                'clear_confirmation_on_pause': True
            }
        }
        
        controller = RecoveryController(config)
        
        # Create any failure condition
        ranked = RankedCandidates(
            primary_choice=None,
            primary_candidate=None,
            runner_up=None,
            runner_up_candidate=None,
            ambiguity_detected=True,
            margin=0.05,
            is_clear_choice=False,
            candidates=[],
            num_candidates=2,
            reason="Ambiguous",
            timestamp=1.0,
            frame_id=1
        )
        
        hand_result = HandDetectionResult(detected=True, confidence=0.9, 
                                         hand_position=(320, 240), failure_reason=None)
        tracker = ObjectTracker({}, seed=42)
        
        plan = controller.check_and_plan(
            scoped_object_id="track_001",
            ranked_candidates=ranked,
            hand_detection=hand_result,
            tracker=tracker,
            system_state=SystemState.EXECUTING,
            timestamp=1.0
        )
        
        # Must clear execution
        if plan.should_pause:
            assert plan.clear_execution == True
    
    def test_recovery_requires_rescope(self):
        """INVARIANT: After pause, must re-establish scope"""
        config = {
            'object_loss': {'pause_on_loss': True, 'loss_grace_frames': 0},
            'hand_loss': {'pause_during_confirm': True, 'loss_grace_frames': 0},
            'ambiguity_during_confirm': {'pause_on_ambiguity': True},
            'recovery': {
                'require_rescope_after_pause': True,
                'clear_confirmation_on_pause': True
            }
        }
        
        controller = RecoveryController(config)
        
        # Create object loss scenario
        ranked = RankedCandidates(
            primary_choice=None,
            primary_candidate=None,
            runner_up=None,
            runner_up_candidate=None,
            ambiguity_detected=False,
            margin=0.0,
            is_clear_choice=False,
            candidates=[],
            num_candidates=0,
            reason="No candidates",
            timestamp=1.0,
            frame_id=1
        )
        
        hand_result = HandDetectionResult(detected=True, confidence=0.9, 
                                         hand_position=(320, 240), failure_reason=None)
        
        # Tracker with missing object
        tracker = ObjectTracker({'track_max_age_frames': 1}, seed=42)
        
        plan = controller.check_and_plan(
            scoped_object_id="nonexistent_track",  # Object doesn't exist
            ranked_candidates=ranked,
            hand_detection=hand_result,
            tracker=tracker,
            system_state=SystemState.EXECUTING,
            timestamp=1.0
        )
        
        # Should pause and require rescope
        assert plan.should_pause == True
        assert plan.clear_scope == True, "Recovery must require re-scoping"
        assert plan.clear_confirmation == True, "Recovery must clear confirmation"
        assert plan.clear_execution == True, "Recovery must clear execution"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

