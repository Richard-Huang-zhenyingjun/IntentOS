"""
Recovery Controller Tests (Week 8)

Tests for recovery controller mechanisms:
- Pause triggers (hand loss, object loss, ambiguity, etc.)
- Recovery plans (what to clear, what to require)
- Recovery actions (step-by-step instructions)
- State validation (only check vulnerable states)
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from vision.recovery_controller import RecoveryController, PauseTrigger, RecoveryAction
from intent_core.schema import SystemState
from vision.object_loss_detector import ObjectLossDetector
from vision.hand_loss_detector import HandLossDetector


class TestRecoveryController:
    """Week 8 tests: recovery controller"""
    
    def test_recovery_controller_initialization(self):
        """RecoveryController should initialize correctly"""
        config = {
            'recovery': {
                'require_rescope_after_pause': True,
                'clear_confirmation_on_pause': True
            },
            'hand_loss': {
                'pause_during_confirm': True,
                'loss_grace_frames': 2
            },
            'object_loss': {
                'pause_on_loss': True,
                'loss_grace_frames': 3
            },
            'ambiguity_during_confirm': {
                'pause_on_ambiguity': True
            }
        }
        
        controller = RecoveryController(config)
        
        assert controller.require_rescope is True
        assert controller.clear_confirmation is True
        assert controller.currently_paused is False
        assert controller.pause_reason is None
    
    def test_hand_loss_during_confirming_triggers_pause(self):
        """INVARIANT: Hand loss during CONFIRMING → PAUSED"""
        config = {
            'recovery': {
                'require_rescope_after_pause': True,
                'clear_confirmation_on_pause': True
            },
            'hand_loss': {
                'pause_during_confirm': True,
                'loss_grace_frames': 2
            }
        }
        
        controller = RecoveryController(config)
        
        # Setup detectors
        hand_detector = HandLossDetector(config)
        controller.hand_loss_detector = hand_detector
        
        # Mock hand detection (no hand)
        from vision.hand_detector import HandDetectionResult
        no_hand = HandDetectionResult(
            landmarks=None,
            detected=False,
            confidence=0.0,
            frame_id=1,
            timestamp=1.0,
            failure_reason="No hand detected"
        )
        
        # Simulate frames with no hand during CONFIRMING
        plan = None
        for i in range(3):
            plan = controller.check(
                system_state=SystemState.CONFIRMING,
                scoped_object_id="lamp_001",
                ranked_candidates=None,
                hand_detection=no_hand,
                tracker=None,
                state_estimate=None,
                confidence_tracker=None,
                timestamp=1.0 + i * 0.1
            )
        
        # Should trigger pause after grace period
        assert plan.should_pause is True
        assert plan.trigger == PauseTrigger.HAND_LOSS
        assert plan.clear_confirmation is True
        assert RecoveryAction.WAIT_FOR_HAND in plan.recovery_actions
    
    def test_object_loss_during_executing_triggers_pause(self):
        """INVARIANT: Object loss during EXECUTING → PAUSED"""
        config = {
            'recovery': {},
            'object_loss': {
                'pause_on_loss': True,
                'loss_grace_frames': 3
            }
        }
        
        controller = RecoveryController(config)
        
        # Setup detector
        object_detector = ObjectLossDetector(config)
        controller.object_loss_detector = object_detector
        
        # Mock tracker (no object)
        class MockTracker:
            max_age = 10
            
            def get_track(self, track_id):
                return None
        
        tracker = MockTracker()
        
        # Simulate frames during EXECUTING
        plan = None
        for i in range(4):
            plan = controller.check(
                system_state=SystemState.EXECUTING,
                scoped_object_id="lamp_001",
                ranked_candidates=None,
                hand_detection=None,
                tracker=tracker,
                state_estimate=None,
                confidence_tracker=None,
                timestamp=1.0 + i * 0.1
            )
        
        # Should trigger pause after grace period
        assert plan.should_pause is True
        assert plan.trigger == PauseTrigger.OBJECT_LOSS
        assert RecoveryAction.RESCOPE_OBJECT in plan.recovery_actions
    
    def test_ambiguity_during_confirming_triggers_pause(self):
        """INVARIANT: Ambiguity during CONFIRMING → PAUSED"""
        config = {
            'recovery': {},
            'ambiguity_during_confirm': {
                'pause_on_ambiguity': True
            }
        }
        
        controller = RecoveryController(config)
        
        # Setup detector
        from vision.ambiguity_during_confirm_detector import AmbiguityDuringConfirmDetector
        ambiguity_detector = AmbiguityDuringConfirmDetector(config)
        controller.ambiguity_detector = ambiguity_detector
        
        # Mock ambiguous ranking
        from vision.candidate_ranker import RankedCandidates
        ambiguous = RankedCandidates(
            primary_choice=None,
            primary_candidate=None,
            runner_up=None,
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
        
        plan = controller.check(
            system_state=SystemState.CONFIRMING,
            scoped_object_id="lamp_001",
            ranked_candidates=ambiguous,
            hand_detection=None,
            tracker=None,
            state_estimate=None,
            confidence_tracker=None,
            timestamp=1.0
        )
        
        assert plan.should_pause is True
        assert plan.trigger == PauseTrigger.AMBIGUITY_DURING_CONFIRM
        assert RecoveryAction.WAIT_FOR_CLARITY in plan.recovery_actions
    
    def test_pause_clears_confirmation_and_execution(self):
        """INVARIANT: Pause clears confirmation and execution permission"""
        config = {
            'recovery': {
                'require_rescope_after_pause': True,
                'clear_confirmation_on_pause': True
            }
        }
        
        controller = RecoveryController(config)
        
        # Mock detector that triggers
        class MockDetector:
            def check(self, **kwargs):
                return (True, "Test pause")
        
        controller.object_loss_detector = MockDetector()
        
        plan = controller.check(
            system_state=SystemState.CONFIRMING,
            scoped_object_id="lamp_001",
            ranked_candidates=None,
            hand_detection=None,
            tracker=None,
            state_estimate=None,
            confidence_tracker=None,
            timestamp=1.0
        )
        
        assert plan.should_pause is True
        assert plan.clear_confirmation is True
        assert plan.clear_execution is True
        assert plan.clear_scope is True
    
    def test_recovery_plan_includes_explanation(self):
        """INVARIANT: Recovery plan always includes human-readable explanation"""
        config = {'recovery': {}}
        controller = RecoveryController(config)
        
        class MockDetector:
            def check(self, **kwargs):
                return (True, "Hand lost")
        
        controller.hand_loss_detector = MockDetector()
        
        plan = controller.check(
            system_state=SystemState.CONFIRMING,
            scoped_object_id="lamp_001",
            ranked_candidates=None,
            hand_detection=None,
            tracker=None,
            state_estimate=None,
            confidence_tracker=None,
            timestamp=1.0
        )
        
        assert plan.should_pause is True
        assert len(plan.recovery_explanation) > 0
        assert "1." in plan.recovery_explanation  # Step-by-step format
        assert len(plan.recovery_actions) > 0
    
    def test_no_pause_during_idle_state(self):
        """INVARIANT: Recovery only checks during vulnerable states"""
        config = {'recovery': {}}
        controller = RecoveryController(config)
        
        class MockDetector:
            def check(self, **kwargs):
                return (True, "Would trigger pause")
        
        controller.object_loss_detector = MockDetector()
        
        plan = controller.check(
            system_state=SystemState.IDLE,  # Not vulnerable
            scoped_object_id="lamp_001",
            ranked_candidates=None,
            hand_detection=None,
            tracker=None,
            state_estimate=None,
            confidence_tracker=None,
            timestamp=1.0
        )
        
        # Should not pause during IDLE (no scoped object to lose)
        # But plan might still be created, just should_pause should be False
        assert plan.should_pause is False
    
    def test_recovery_start_and_complete(self):
        """Recovery lifecycle: start → steps → complete"""
        config = {'recovery': {}}
        controller = RecoveryController(config)
        
        # Start recovery
        result = controller.start_recovery()
        assert result is True
        assert controller.recovery_in_progress is True
        
        # Complete step
        controller.complete_recovery_step(RecoveryAction.WAIT_FOR_HAND)
        assert RecoveryAction.WAIT_FOR_HAND.value in controller.recovery_steps_completed
        
        # Validate recovery
        required = [RecoveryAction.WAIT_FOR_HAND, RecoveryAction.RECONFIRM_ACTION]
        controller.complete_recovery_step(RecoveryAction.RECONFIRM_ACTION)
        
        is_complete, message = controller.validate_recovery(required)
        assert is_complete is True
        
        # Clear pause
        controller.clear_pause()
        assert controller.recovery_in_progress is False
        assert controller.currently_paused is False
    
    def test_multiple_pause_triggers_prioritize_first(self):
        """If multiple triggers fire, use first (priority order)"""
        config = {
            'recovery': {},
            'object_loss': {'pause_on_loss': True, 'loss_grace_frames': 0},
            'hand_loss': {'pause_during_confirm': True, 'loss_grace_frames': 0}
        }
        
        controller = RecoveryController(config)
        
        # Mock both detectors triggering
        class MockObjectDetector:
            def check(self, **kwargs):
                return (True, "Object lost")
        
        class MockHandDetector:
            def check(self, **kwargs):
                return (True, "Hand lost")
        
        controller.object_loss_detector = MockObjectDetector()
        controller.hand_loss_detector = MockHandDetector()
        
        # Mock tracker
        class MockTracker:
            max_age = 10
            def get_track(self, track_id):
                return None
        
        plan = controller.check(
            system_state=SystemState.CONFIRMING,
            scoped_object_id="lamp_001",
            ranked_candidates=None,
            hand_detection=None,
            tracker=MockTracker(),
            state_estimate=None,
            confidence_tracker=None,
            timestamp=1.0
        )
        
        assert plan.should_pause is True
        # Should take first trigger (object loss checked first)
        assert plan.trigger == PauseTrigger.OBJECT_LOSS
    
    def test_recovery_statistics_tracking(self):
        """RecoveryController should track statistics"""
        config = {'recovery': {}}
        controller = RecoveryController(config)
        
        # Mock detector
        class MockDetector:
            def check(self, **kwargs):
                return (True, "Test pause")
        
        controller.object_loss_detector = MockDetector()
        
        # Trigger multiple pauses
        for i in range(3):
            plan = controller.check(
                system_state=SystemState.CONFIRMING,
                scoped_object_id="lamp_001",
                ranked_candidates=None,
                hand_detection=None,
                tracker=None,
                state_estimate=None,
                confidence_tracker=None,
                timestamp=float(i)
            )
            
            if plan.should_pause:
                controller.clear_pause()  # Reset for next trigger
        
        stats = controller.get_statistics()
        
        assert stats['total_checks'] >= 3
        assert stats['pause_events'] >= 3
        assert 'pause_rate' in stats
        assert 'pause_triggers' in stats
    
    def test_confidence_drop_detection(self):
        """Test confidence drop detection (NEW Week 8 trigger)"""
        config = {
            'recovery': {
                'confidence_drop_threshold': 0.3
            }
        }
        
        controller = RecoveryController(config)
        
        # Mock confidence tracker with dropped confidence
        class MockConfidenceTracker:
            def get_current_confidence(self):
                return 0.25  # Below threshold
            
            def has_dropped_significantly(self, threshold):
                return True
        
        # This would be checked in the enhanced check() method
        # For now, verify config is loaded
        assert controller.confidence_drop_threshold == 0.3
    
    def test_attention_timeout_detection(self):
        """Test attention timeout detection (NEW Week 8 trigger)"""
        config = {
            'recovery': {
                'attention_timeout_seconds': 10.0
            }
        }
        
        controller = RecoveryController(config)
        
        assert controller.attention_timeout_seconds == 10.0
    
    def test_recovery_plan_evidence_included(self):
        """RecoveryPlan should include evidence for debugging"""
        config = {'recovery': {}}
        controller = RecoveryController(config)
        
        class MockDetector:
            def check(self, **kwargs):
                return (True, "Test pause with evidence")
        
        controller.object_loss_detector = MockDetector()
        
        plan = controller.check(
            system_state=SystemState.CONFIRMING,
            scoped_object_id="lamp_001",
            ranked_candidates=None,
            hand_detection=None,
            tracker=None,
            state_estimate=None,
            confidence_tracker=None,
            timestamp=5.5
        )
        
        assert plan.should_pause is True
        assert 'scoped_object_id' in plan.evidence
        assert plan.evidence['scoped_object_id'] == "lamp_001"
        assert plan.evidence['system_state'] == SystemState.CONFIRMING.value
        assert plan.evidence['timestamp'] == 5.5
    
    def test_clear_pause_resets_all_detectors(self):
        """clear_pause() should reset all detector states"""
        config = {
            'recovery': {},
            'object_loss': {'pause_on_loss': True, 'loss_grace_frames': 1},
            'hand_loss': {'pause_during_confirm': True, 'loss_grace_frames': 1}
        }
        
        controller = RecoveryController(config)
        
        # Setup detectors
        object_detector = ObjectLossDetector(config)
        hand_detector = HandLossDetector(config)
        
        controller.object_loss_detector = object_detector
        controller.hand_loss_detector = hand_detector
        
        # Trigger some internal state
        object_detector.frames_missing = 5
        hand_detector.frames_missing = 3
        
        # Clear pause
        controller.clear_pause()
        
        # Detectors should be reset
        assert object_detector.frames_missing == 0
        assert hand_detector.frames_missing == 0
        assert controller.currently_paused is False


class TestRecoveryActions:
    """Test recovery action definitions"""
    
    def test_recovery_action_enum_values(self):
        """RecoveryAction enum should have all required values"""
        assert RecoveryAction.RESCOPE_OBJECT.value == "rescope_object"
        assert RecoveryAction.RECONFIRM_ACTION.value == "reconfirm_action"
        assert RecoveryAction.WAIT_FOR_CLARITY.value == "wait_for_clarity"
        assert RecoveryAction.WAIT_FOR_HAND.value == "wait_for_hand"
        assert RecoveryAction.WAIT_FOR_STABILITY.value == "wait_for_stability"


class TestPauseTriggers:
    """Test pause trigger definitions"""
    
    def test_pause_trigger_enum_values(self):
        """PauseTrigger enum should have all required values"""
        assert PauseTrigger.OBJECT_LOSS.value == "object_loss"
        assert PauseTrigger.HAND_LOSS.value == "hand_loss"
        assert PauseTrigger.AMBIGUITY_DURING_CONFIRM.value == "ambiguity_during_confirm"
        assert PauseTrigger.OSCILLATION.value == "oscillation"
        assert PauseTrigger.CONFIDENCE_DROP.value == "confidence_drop"
        assert PauseTrigger.ATTENTION_TIMEOUT.value == "attention_timeout"
        assert PauseTrigger.STATE_UNCERTAINTY.value == "state_uncertainty"
        assert PauseTrigger.SCOPE_DRIFT.value == "scope_drift"
        assert PauseTrigger.MANUAL.value == "manual"


class TestRecoveryPlanValidation:
    """Test recovery plan structure and validation"""
    
    def test_recovery_plan_is_frozen(self):
        """RecoveryPlan should be frozen (immutable)"""
        from vision.recovery_controller import RecoveryPlan
        
        plan = RecoveryPlan(
            should_pause=True,
            trigger=PauseTrigger.OBJECT_LOSS,
            reason="Test",
            clear_scope=True,
            clear_confirmation=True,
            clear_execution=True,
            clear_undo=False,
            recovery_actions=[RecoveryAction.RESCOPE_OBJECT],
            recovery_explanation="Test explanation",
            evidence={},
            timestamp=1.0,
            system_state_at_pause='confirming'
        )
        
        # Should not be able to modify (frozen)
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            plan.should_pause = False
    
    def test_recovery_plan_includes_all_required_fields(self):
        """RecoveryPlan should have all required fields"""
        from vision.recovery_controller import RecoveryPlan
        
        plan = RecoveryPlan(
            should_pause=True,
            trigger=PauseTrigger.HAND_LOSS,
            reason="Hand disappeared",
            clear_scope=False,
            clear_confirmation=True,
            clear_execution=True,
            clear_undo=False,
            recovery_actions=[RecoveryAction.WAIT_FOR_HAND, RecoveryAction.RECONFIRM_ACTION],
            recovery_explanation="1. Wait for hand\n2. Re-confirm action",
            evidence={'frames_missing': 5},
            timestamp=10.5,
            system_state_at_pause='confirming'
        )
        
        assert plan.should_pause is True
        assert plan.trigger == PauseTrigger.HAND_LOSS
        assert plan.reason == "Hand disappeared"
        assert plan.clear_scope is False
        assert plan.clear_confirmation is True
        assert plan.clear_execution is True
        assert plan.clear_undo is False
        assert len(plan.recovery_actions) == 2
        assert plan.recovery_explanation.startswith("1.")
        assert 'frames_missing' in plan.evidence
        assert plan.timestamp == 10.5
        assert plan.system_state_at_pause == 'confirming'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])




