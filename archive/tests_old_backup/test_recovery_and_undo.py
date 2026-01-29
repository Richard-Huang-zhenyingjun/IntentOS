"""
Comprehensive Recovery and Undo Tests (Week 8)

Tests for:
- Recovery system (pause triggers, recovery plans, RECOVERING state)
- Hardened undo (time windows, state validation, symmetrical execution)
- Fault injection integration
- Narrative logging
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from intent_core.schema import SystemState, SystemContext, IntentType, Intent
from vision.recovery_controller import (
    RecoveryController,
    RecoveryPlan,
    PauseTrigger,
    RecoveryAction
)
from execution.action_history import ActionHistory, ActionRecord
from execution.undo_controller import UndoController
from execution.smart_world_sim import SmartWorldSim
from execution.action_schema import ExecutionResult


class TestRecoveryController:
    """Test recovery controller mechanisms"""
    
    def test_recovery_controller_initialization(self):
        """RecoveryController should initialize correctly"""
        config = {
            'object_loss': {'pause_on_loss': True, 'loss_grace_frames': 3},
            'hand_loss': {'pause_during_confirm': True, 'loss_grace_frames': 2},
            'ambiguity_during_confirm': {'pause_on_ambiguity': True},
            'recovery': {
                'require_rescope_after_pause': True,
                'clear_confirmation_on_pause': True
            }
        }
        
        controller = RecoveryController(config)
        
        assert controller.require_rescope is True
        assert controller.clear_confirmation is True
        assert controller.currently_paused is False
    
    def test_recovery_plan_creation_for_object_loss(self):
        """Recovery plan should be created for object loss"""
        config = {
            'object_loss': {'pause_on_loss': True, 'loss_grace_frames': 1},
            'recovery': {
                'require_rescope_after_pause': True,
                'clear_confirmation_on_pause': True
            }
        }
        
        controller = RecoveryController(config)
        
        # Manually create object loss detector
        from vision.object_loss_detector import ObjectLossDetector
        from vision.object_tracker import ObjectTracker
        
        loss_detector = ObjectLossDetector(config)
        controller.object_loss_detector = loss_detector
        
        tracker = ObjectTracker({'track_max_age_frames': 10}, seed=42)
        
        # Simulate object loss
        for _ in range(3):  # Exceed grace frames
            loss_detector.check(
                scoped_object_id='track_001',
                tracker=tracker,
                system_state=SystemState.CONFIRMING,
                timestamp=1.0
            )
        
        should_pause, reason = loss_detector.check(
            scoped_object_id='track_001',
            tracker=tracker,
            system_state=SystemState.CONFIRMING,
            timestamp=1.1
        )
        
        assert should_pause is True
        assert 'lost' in reason.lower()
    
    def test_recovery_plan_structure(self):
        """RecoveryPlan should have complete structure"""
        plan = RecoveryPlan(
            should_pause=True,
            trigger=PauseTrigger.OBJECT_LOSS,
            reason="Object disappeared",
            clear_scope=True,
            clear_confirmation=True,
            clear_execution=True,
            clear_undo=False,
            recovery_actions=[RecoveryAction.RESCOPE_OBJECT, RecoveryAction.RECONFIRM_ACTION],
            recovery_explanation="Bring object back into view",
            evidence={'object_id': 'track_001'},
            timestamp=5.0,
            system_state_at_pause='confirming'
        )
        
        assert plan.should_pause is True
        assert plan.trigger == PauseTrigger.OBJECT_LOSS
        assert plan.clear_scope is True
        assert plan.clear_confirmation is True
        assert plan.clear_execution is True
        assert plan.clear_undo is False
        assert len(plan.recovery_actions) == 2
        assert plan.recovery_actions[0] == RecoveryAction.RESCOPE_OBJECT
    
    def test_recovery_controller_statistics(self):
        """RecoveryController should track statistics"""
        config = {}
        controller = RecoveryController(config)
        
        stats = controller.get_statistics()
        
        assert 'total_checks' in stats
        assert 'pause_events' in stats
        assert 'pause_rate' in stats
        assert 'pause_triggers' in stats


class TestSystemContext:
    """Test SystemContext dataclass"""
    
    def test_system_context_initialization(self):
        """SystemContext should initialize with defaults"""
        context = SystemContext()
        
        assert context.pause_trigger is None
        assert context.pause_reason is None
        assert context.pause_timestamp is None
        assert context.recovery_required is False
        assert context.recovery_steps_completed == []
        assert context.recovery_instructions == []
        assert context.undo_available is False
        assert context.undo_expires_at is None
        assert context.undo_action_id is None
    
    def test_system_context_with_pause_data(self):
        """SystemContext should store pause data"""
        context = SystemContext()
        
        context.pause_trigger = PauseTrigger.HAND_LOSS.value
        context.pause_reason = "Hand lost during confirmation"
        context.pause_timestamp = 10.5
        context.recovery_required = True
        context.recovery_instructions = ["Wait for hand", "Re-confirm"]
        
        assert context.pause_trigger == "hand_loss"
        assert context.recovery_required is True
        assert len(context.recovery_instructions) == 2
    
    def test_system_context_with_undo_data(self):
        """SystemContext should store undo data"""
        context = SystemContext()
        
        context.undo_available = True
        context.undo_expires_at = 20.0
        context.undo_action_id = "action_123"
        
        assert context.undo_available is True
        assert context.undo_expires_at == 20.0
        assert context.undo_action_id == "action_123"


class TestEnhancedActionHistory:
    """Test enhanced action history with strict validation"""
    
    def test_action_record_validation_on_init(self):
        """ActionRecord should validate on initialization"""
        # Valid reversible action
        record = ActionRecord(
            action_id="action_001",
            user_id="user_001",
            session_id="session_001",
            object_id="lamp_001",
            object_label="lamp",
            category="lamp",
            action_type="toggle_power",
            before_state={'power': 'off'},
            after_state={'power': 'on'},
            reversible=True,
            timestamp=1.0,
            expires_at=11.0,
            undo_window=10.0
        )
        
        assert record.reversible is True
        assert record.before_state is not None
        assert record.after_state is not None
    
    def test_action_record_validation_fails_for_invalid_reversible(self):
        """ActionRecord should fail validation for invalid reversible action"""
        with pytest.raises(ValueError, match="Reversible actions must have before_state"):
            ActionRecord(
                action_id="action_001",
                user_id="user_001",
                session_id="session_001",
                object_id="lamp_001",
                object_label="lamp",
                category="lamp",
                action_type="toggle_power",
                before_state=None,  # Invalid!
                after_state={'power': 'on'},
                reversible=True,
                timestamp=1.0,
                expires_at=11.0,
                undo_window=10.0
            )
    
    def test_action_record_is_expired(self):
        """is_expired() should correctly determine expiry"""
        record = ActionRecord(
            action_id="action_001",
            user_id="user_001",
            session_id="session_001",
            object_id="lamp_001",
            object_label="lamp",
            category="lamp",
            action_type="toggle_power",
            before_state={'power': 'off'},
            after_state={'power': 'on'},
            reversible=True,
            timestamp=1.0,
            expires_at=11.0,
            undo_window=10.0
        )
        
        assert record.is_expired(5.0) is False  # Not expired
        assert record.is_expired(10.0) is False  # Not expired
        assert record.is_expired(11.0) is False  # At expiry (not yet expired)
        assert record.is_expired(11.1) is True  # Expired
    
    def test_action_record_can_undo(self):
        """can_undo() should validate undo eligibility"""
        record = ActionRecord(
            action_id="action_001",
            user_id="user_001",
            session_id="session_001",
            object_id="lamp_001",
            object_label="lamp",
            category="lamp",
            action_type="toggle_power",
            before_state={'power': 'off'},
            after_state={'power': 'on'},
            reversible=True,
            timestamp=1.0,
            expires_at=11.0,
            undo_window=10.0
        )
        
        # Valid undo
        can_undo, reason = record.can_undo(5.0)
        assert can_undo is True
        assert reason == ""
        
        # Expired
        can_undo, reason = record.can_undo(15.0)
        assert can_undo is False
        assert "expired" in reason.lower()
        
        # Already undone
        record.undone = True
        can_undo, reason = record.can_undo(5.0)
        assert can_undo is False
        assert "already undone" in reason.lower()
    
    def test_action_history_enhanced_indexing(self):
        """ActionHistory should have enhanced indexing"""
        config = {
            'max_history_size': 100,
            'undo_window_seconds': 10.0,
            'allow_multiple_undo': False,
            'auto_cleanup_expired': True
        }
        
        history = ActionHistory(config)
        
        # Add records
        record1 = ActionRecord(
            action_id="action_001",
            user_id="user_001",
            session_id="session_001",
            object_id="lamp_001",
            object_label="lamp",
            category="lamp",
            action_type="toggle_power",
            before_state={'power': 'off'},
            after_state={'power': 'on'},
            reversible=True,
            timestamp=1.0,
            expires_at=11.0,
            undo_window=10.0
        )
        
        history.record(record1)
        
        # Check indexing
        assert len(history.by_session) == 1
        assert "session_001" in history.by_session
        assert len(history.by_object) == 1
        assert "lamp_001" in history.by_object
    
    def test_action_history_get_actions_for_object(self):
        """get_actions_for_object() should filter by object"""
        config = {'max_history_size': 100, 'undo_window_seconds': 10.0}
        history = ActionHistory(config)
        
        # Add multiple records for different objects
        for i, obj_id in enumerate(['lamp_001', 'door_001', 'lamp_001']):
            record = ActionRecord(
                action_id=f"action_{i:03d}",
                user_id="user_001",
                session_id="session_001",
                object_id=obj_id,
                object_label=obj_id.split('_')[0],
                category=obj_id.split('_')[0],
                action_type="toggle_power",
                before_state={'power': 'off'},
                after_state={'power': 'on'},
                reversible=True,
                timestamp=float(i),
                expires_at=float(i) + 10.0,
                undo_window=10.0
            )
            history.record(record)
        
        lamp_actions = history.get_actions_for_object('lamp_001')
        assert len(lamp_actions) == 2
        
        door_actions = history.get_actions_for_object('door_001')
        assert len(door_actions) == 1


class TestHardenedUndoController:
    """Test hardened undo controller"""
    
    def test_undo_blocked_during_paused_state(self):
        """Undo should be blocked during PAUSED state"""
        config = {
            'enabled': True,
            'require_confirmation': True,
            'undo_window_seconds': 10.0,
            'block_during_pause': True
        }
        
        history = ActionHistory({'max_history_size': 100, 'undo_window_seconds': 10.0})
        world = SmartWorldSim({}, seed=42)
        
        undo_controller = UndoController(config, history, world)
        
        # Add action to history
        world.ensure_object("lamp_001", "lamp", 1.0)
        result = world.apply_action(
            object_id="lamp_001",
            action_type="toggle_power",
            timestamp=1.0
        )
        
        record = ActionRecord.from_execution_result(
            result=result,
            object_label="lamp",
            category="lamp",
            user_id="user_001",
            session_id="session_001"
        )
        history.record(record)
        
        # Undo should NOT be available during PAUSED
        available = undo_controller.is_undo_available(
            current_time=2.0,
            system_state=SystemState.PAUSED
        )
        assert available is False
        
        # Request undo during PAUSED should fail
        success, reason = undo_controller.request_undo(
            current_time=2.0,
            system_state=SystemState.PAUSED
        )
        assert success is False
        assert "paused" in reason.lower()
    
    def test_undo_blocked_during_recovering_state(self):
        """Undo should be blocked during RECOVERING state"""
        config = {
            'enabled': True,
            'require_confirmation': True,
            'undo_window_seconds': 10.0,
            'block_during_pause': True
        }
        
        history = ActionHistory({'max_history_size': 100, 'undo_window_seconds': 10.0})
        world = SmartWorldSim({}, seed=42)
        
        undo_controller = UndoController(config, history, world)
        
        # Add action to history
        world.ensure_object("lamp_001", "lamp", 1.0)
        result = world.apply_action(
            object_id="lamp_001",
            action_type="toggle_power",
            timestamp=1.0
        )
        
        record = ActionRecord.from_execution_result(
            result=result,
            object_label="lamp",
            category="lamp",
            user_id="user_001",
            session_id="session_001"
        )
        history.record(record)
        
        # Undo should NOT be available during RECOVERING
        available = undo_controller.is_undo_available(
            current_time=2.0,
            system_state=SystemState.RECOVERING
        )
        assert available is False
    
    def test_undo_confirm_symmetric_to_execution(self):
        """Undo confirm should be symmetric to action execution"""
        config = {
            'enabled': True,
            'require_confirmation': True,
            'undo_window_seconds': 10.0
        }
        
        history = ActionHistory({'max_history_size': 100, 'undo_window_seconds': 10.0})
        world = SmartWorldSim({}, seed=42)
        
        undo_controller = UndoController(config, history, world)
        
        # Execute action
        world.ensure_object("lamp_001", "lamp", 1.0)
        result = world.apply_action(
            object_id="lamp_001",
            action_type="toggle_power",
            timestamp=1.0
        )
        
        record = ActionRecord.from_execution_result(
            result=result,
            object_label="lamp",
            category="lamp",
            user_id="user_001",
            session_id="session_001"
        )
        history.record(record)
        
        # Request undo
        success, reason = undo_controller.request_undo(
            current_time=2.0,
            system_state=SystemState.SCOPED
        )
        assert success is True
        
        # Confirm undo - should return ExecutionResult
        undo_result = undo_controller.confirm_undo(
            current_time=3.0,
            system_state=SystemState.UNDO_CONFIRMING
        )
        
        assert isinstance(undo_result, ExecutionResult)
        assert undo_result.ok is True
        assert undo_result.action_id.startswith("undo_")
        assert undo_result.reversible is False  # Undo itself is not reversible
        assert "Undid" in undo_result.reason
    
    def test_undo_refusal_tracking(self):
        """Undo controller should track refusal reasons"""
        config = {
            'enabled': True,
            'require_confirmation': True,
            'undo_window_seconds': 10.0
        }
        
        history = ActionHistory({'max_history_size': 100, 'undo_window_seconds': 10.0})
        world = SmartWorldSim({}, seed=42)
        
        undo_controller = UndoController(config, history, world)
        
        # No action available - should refuse
        success, reason = undo_controller.request_undo(
            current_time=1.0,
            system_state=SystemState.IDLE
        )
        assert success is False
        
        stats = undo_controller.get_statistics()
        assert stats['total_undo_refusals'] == 1
        assert len(stats['undo_refusal_reasons']) > 0


class TestRecoveryStateMachine:
    """Test state machine with recovery states"""
    
    def test_recovery_start_intent_type(self):
        """RECOVERY_START intent type should exist"""
        intent = Intent(
            type=IntentType.RECOVERY_START,
            confidence=1.0,
            source="user",
            timestamp=1.0
        )
        
        assert intent.type == IntentType.RECOVERY_START
    
    def test_recovery_complete_intent_type(self):
        """RECOVERY_COMPLETE intent type should exist"""
        intent = Intent(
            type=IntentType.RECOVERY_COMPLETE,
            confidence=1.0,
            source="user",
            timestamp=1.0
        )
        
        assert intent.type == IntentType.RECOVERY_COMPLETE
    
    def test_recovering_system_state(self):
        """RECOVERING system state should exist"""
        state = SystemState.RECOVERING
        assert state.value == "recovering"
    
    def test_undo_confirming_system_state(self):
        """UNDO_CONFIRMING system state should exist"""
        state = SystemState.UNDO_CONFIRMING
        assert state.value == "undo_confirming"


class TestNarrativeLogging:
    """Test narrative logging integration"""
    
    def test_recovery_plan_generates_narrative(self):
        """RecoveryPlan should generate human-readable narrative"""
        from intent_core.logger import EventLogger
        
        logger = EventLogger(log_file=None, enabled=False)
        
        plan = RecoveryPlan(
            should_pause=True,
            trigger=PauseTrigger.HAND_LOSS,
            reason="Hand lost during confirmation",
            clear_scope=False,
            clear_confirmation=True,
            clear_execution=True,
            clear_undo=False,
            recovery_actions=[RecoveryAction.WAIT_FOR_HAND, RecoveryAction.RECONFIRM_ACTION],
            recovery_explanation="Ensure hand is visible",
            evidence={},
            timestamp=5.0,
            system_state_at_pause='confirming'
        )
        
        narrative = logger._generate_pause_narrative(plan)
        
        assert isinstance(narrative, str)
        assert len(narrative) > 0
        assert "paused" in narrative.lower()
        assert "hand_loss" in narrative.lower()
        assert "confirmation" in narrative.lower()
        assert "recover" in narrative.lower()


class TestIntegration:
    """Integration tests for recovery and undo"""
    
    def test_complete_recovery_flow(self):
        """Test complete pause → recovery → resume flow"""
        # Create recovery controller
        config = {'recovery': {'require_rescope_after_pause': True}}
        controller = RecoveryController(config)
        
        # Simulate pause
        plan = RecoveryPlan(
            should_pause=True,
            trigger=PauseTrigger.OBJECT_LOSS,
            reason="Object disappeared",
            clear_scope=True,
            clear_confirmation=True,
            clear_execution=True,
            clear_undo=False,
            recovery_actions=[RecoveryAction.RESCOPE_OBJECT],
            recovery_explanation="Bring object back",
            evidence={},
            timestamp=5.0,
            system_state_at_pause='confirming'
        )
        
        # Start recovery
        controller.start_recovery()
        assert controller.recovery_in_progress is True
        
        # Complete recovery step
        controller.complete_recovery_step(RecoveryAction.RESCOPE_OBJECT)
        assert RecoveryAction.RESCOPE_OBJECT.value in controller.recovery_steps_completed
        
        # Validate recovery
        is_complete, message = controller.validate_recovery([RecoveryAction.RESCOPE_OBJECT])
        assert is_complete is True
        
        # Clear pause
        controller.clear_pause()
        assert controller.currently_paused is False
        assert controller.recovery_in_progress is False
    
    def test_complete_undo_flow(self):
        """Test complete action → undo request → undo confirm flow"""
        config = {
            'enabled': True,
            'require_confirmation': True,
            'undo_window_seconds': 10.0
        }
        
        history = ActionHistory({'max_history_size': 100, 'undo_window_seconds': 10.0})
        world = SmartWorldSim({}, seed=42)
        undo_controller = UndoController(config, history, world)
        
        # 1. Execute action
        world.ensure_object("lamp_001", "lamp", 1.0)
        result = world.apply_action("lamp_001", "toggle_power", 1.0)
        
        record = ActionRecord.from_execution_result(
            result=result,
            object_label="lamp",
            category="lamp",
            user_id="user_001",
            session_id="session_001"
        )
        history.record(record)
        
        # 2. Request undo
        success, reason = undo_controller.request_undo(
            current_time=2.0,
            system_state=SystemState.SCOPED
        )
        assert success is True
        assert undo_controller.undo_requested is True
        
        # 3. Confirm undo
        undo_result = undo_controller.confirm_undo(
            current_time=3.0,
            system_state=SystemState.UNDO_CONFIRMING
        )
        
        assert undo_result.ok is True
        assert undo_controller.undo_requested is False  # Cleared after confirm
        
        # 4. Verify action marked as undone
        assert record.undone is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])




