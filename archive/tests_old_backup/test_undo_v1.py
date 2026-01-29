"""Week 5 tests: undo functionality (Enhanced Week 8)."""

import pytest
from execution.action_history import ActionHistory, ActionRecord
from execution.undo_controller import UndoController
from execution.smart_world_sim import SmartWorldSim
from intent_core.schema import SystemState


class TestUndoV1:
    """Week 5 tests: undo functionality"""
    
    def test_undo_available_after_action(self):
        """INVARIANT: After reversible action, undo is available"""
        config = {'undo_window_seconds': 10.0}
        history = ActionHistory(config)
        
        # Record a reversible action
        record = ActionRecord(
            action_id="action_001",
            timestamp=1.0,
            user_id=None,
            object_id="obj_lamp",
            object_label="lamp",
            category="lamp",
            action_type="toggle_power",
            before_state={'power': 'off'},
            after_state={'power': 'on'},
            reversible=True,
            expires_at=11.0  # 1.0 + 10.0
        )
        
        history.record(record)
        
        # Check undo available
        assert history.last_reversible(current_time=5.0) is not None
    
    def test_undo_expired_not_available(self):
        """INVARIANT: Undo expires after window"""
        config = {'undo_window_seconds': 10.0}
        history = ActionHistory(config)
        
        record = ActionRecord(
            action_id="action_001",
            timestamp=1.0,
            user_id=None,
            object_id="obj_lamp",
            object_label="lamp",
            category="lamp",
            action_type="toggle_power",
            before_state={'power': 'off'},
            after_state={'power': 'on'},
            reversible=True,
            expires_at=11.0
        )
        
        history.record(record)
        
        # After expiry
        assert history.last_reversible(current_time=12.0) is None
    
    def test_undo_requires_confirmation(self):
        """INVARIANT: Undo request alone does not apply undo"""
        config = {'undo_window_seconds': 10.0, 'require_confirmation': True}
        history = ActionHistory(config)
        world = SmartWorldSim({}, seed=42)
        undo_controller = UndoController(config, history, world)
        
        # Record action
        record = ActionRecord(
            action_id="action_001",
            timestamp=1.0,
            user_id=None,
            object_id="obj_lamp",
            object_label="lamp",
            category="lamp",
            action_type="toggle_power",
            before_state={'power': 'off'},
            after_state={'power': 'on'},
            reversible=True,
            expires_at=11.0
        )
        history.record(record)
        
        # Ensure object in world
        world.ensure_object("obj_lamp", "lamp", 1.0)
        world.objects["obj_lamp"].state = {'power': 'on'}
        
        # Request undo
        success, reason = undo_controller.request_undo(current_time=5.0)
        assert success == True
        
        # State should still be 'on' (not undone yet)
        assert world.get_object_state("obj_lamp")['power'] == 'on'
        
        # Now confirm undo
        result = undo_controller.confirm_undo(current_time=5.5)
        assert result.ok == True
        
        # Now state should be 'off' (undone)
        assert world.get_object_state("obj_lamp")['power'] == 'off'
    
    def test_undo_restores_state(self):
        """INVARIANT: Undo restores exact previous state"""
        config = {}
        world = SmartWorldSim({}, seed=42)
        
        # Setup initial state
        world.ensure_object("obj_lamp", "lamp", 1.0)
        initial_state = world.get_object_state("obj_lamp")
        
        # Change state
        from execution.action_schema import ActionRequest, ActionType
        request = ActionRequest.create(
            object_id="obj_lamp",
            object_label="lamp",
            category="lamp",
            action_type=ActionType.TOGGLE_POWER,
            timestamp=2.0
        )
        
        before, after = world.apply_action(request)
        
        # Apply undo
        before_undo, after_undo = world.apply_undo(
            object_id="obj_lamp",
            before_state=before,
            timestamp=3.0
        )
        
        # Should match initial state
        assert after_undo == initial_state
    
    # === Week 8 Enhanced Safety Tests ===
    
    def test_undo_blocked_during_paused_state(self):
        """INVARIANT: Undo request blocked during PAUSED state (Week 8)"""
        config = {
            'undo_window_seconds': 10.0,
            'block_during_pause': True
        }
        
        history = ActionHistory({'undo_window_seconds': 10.0})
        world = SmartWorldSim({}, seed=42)
        controller = UndoController(config, history, world)
        
        # Record reversible action
        record = ActionRecord(
            action_id="action_001",
            timestamp=1.0,
            user_id=None,
            session_id=None,
            object_id="lamp_001",
            object_label="lamp",
            category="lamp",
            action_type="toggle_power",
            before_state={'power': 'off'},
            after_state={'power': 'on'},
            reversible=True,
            expires_at=11.0,
            undo_window=10.0
        )
        history.record(record)
        
        # Try to request undo during PAUSED state
        success, reason = controller.request_undo(
            current_time=5.0,
            system_state=SystemState.PAUSED  # PAUSED state
        )
        
        assert success is False
        assert "paused" in reason.lower()
    
    def test_undo_blocked_during_recovering_state(self):
        """INVARIANT: Undo request blocked during RECOVERING state (Week 8)"""
        config = {
            'undo_window_seconds': 10.0,
            'block_during_pause': True
        }
        
        history = ActionHistory({'undo_window_seconds': 10.0})
        world = SmartWorldSim({}, seed=42)
        controller = UndoController(config, history, world)
        
        # Record reversible action
        record = ActionRecord(
            action_id="action_001",
            timestamp=1.0,
            user_id=None,
            session_id=None,
            object_id="lamp_001",
            object_label="lamp",
            category="lamp",
            action_type="toggle_power",
            before_state={'power': 'off'},
            after_state={'power': 'on'},
            reversible=True,
            expires_at=11.0,
            undo_window=10.0
        )
        history.record(record)
        
        # Try to request undo during RECOVERING state
        success, reason = controller.request_undo(
            current_time=5.0,
            system_state=SystemState.RECOVERING  # RECOVERING state
        )
        
        assert success is False
        assert "recovering" in reason.lower()
    
    def test_undo_blocked_during_executing_state(self):
        """INVARIANT: Undo request blocked during EXECUTING state (Week 8)"""
        config = {
            'undo_window_seconds': 10.0,
            'block_during_pause': True
        }
        
        history = ActionHistory({'undo_window_seconds': 10.0})
        world = SmartWorldSim({}, seed=42)
        controller = UndoController(config, history, world)
        
        # Record reversible action
        record = ActionRecord(
            action_id="action_001",
            timestamp=1.0,
            user_id=None,
            session_id=None,
            object_id="lamp_001",
            object_label="lamp",
            category="lamp",
            action_type="toggle_power",
            before_state={'power': 'off'},
            after_state={'power': 'on'},
            reversible=True,
            expires_at=11.0,
            undo_window=10.0
        )
        history.record(record)
        
        # Try to request undo during EXECUTING state
        success, reason = controller.request_undo(
            current_time=5.0,
            system_state=SystemState.EXECUTING  # EXECUTING state
        )
        
        assert success is False
        assert "executing" in reason.lower()
    
    def test_undo_requires_explicit_confirmation_v2(self):
        """INVARIANT: Undo request does not apply, confirmation required (Week 8)"""
        config = {'require_confirmation': True, 'undo_window_seconds': 10.0}
        history = ActionHistory({'undo_window_seconds': 10.0})
        world = SmartWorldSim({}, seed=42)
        controller = UndoController(config, history, world)
        
        # Setup
        world.ensure_object("lamp_001", "lamp", 1.0)
        world.objects["lamp_001"].state = {'power': 'on'}
        
        record = ActionRecord(
            action_id="action_001",
            timestamp=1.0,
            user_id=None,
            session_id=None,
            object_id="lamp_001",
            object_label="lamp",
            category="lamp",
            action_type="toggle_power",
            before_state={'power': 'off'},
            after_state={'power': 'on'},
            reversible=True,
            expires_at=11.0,
            undo_window=10.0
        )
        history.record(record)
        
        # Request undo
        success, reason = controller.request_undo(
            current_time=5.0,
            system_state=SystemState.SCOPED
        )
        assert success is True
        
        # State should NOT change yet (not confirmed)
        assert world.get_object_state("lamp_001")['power'] == 'on'
        
        # Now confirm
        result = controller.confirm_undo(
            current_time=5.5,
            system_state=SystemState.UNDO_CONFIRMING
        )
        assert result.ok is True
        
        # NOW state should change
        assert world.get_object_state("lamp_001")['power'] == 'off'
    
    def test_undo_cannot_be_applied_twice(self):
        """INVARIANT: Once undone, action cannot be undone again (Week 8)"""
        config = {'undo_window_seconds': 10.0, 'allow_multiple_undo': False}
        history = ActionHistory(config)
        
        record = ActionRecord(
            action_id="action_001",
            timestamp=1.0,
            user_id=None,
            session_id=None,
            object_id="lamp_001",
            object_label="lamp",
            category="lamp",
            action_type="toggle_power",
            before_state={'power': 'off'},
            after_state={'power': 'on'},
            reversible=True,
            expires_at=11.0,
            undo_window=10.0
        )
        history.record(record)
        
        # First undo
        history.mark_undone("action_001", 5.0, "undo_001")
        
        # Try to undo again
        last = history.last_reversible(5.5)
        assert last is None  # Should not be available
        
        # Verify record is marked undone
        assert record.undone is True
    
    def test_undo_respects_expiry_time(self):
        """INVARIANT: Undo refuses after expiry (Week 8)"""
        config = {'undo_window_seconds': 10.0}
        history = ActionHistory(config)
        
        record = ActionRecord(
            action_id="action_001",
            timestamp=1.0,
            user_id=None,
            session_id=None,
            object_id="lamp_001",
            object_label="lamp",
            category="lamp",
            action_type="toggle_power",
            before_state={'power': 'off'},
            after_state={'power': 'on'},
            reversible=True,
            expires_at=11.0,  # Expires at 11.0
            undo_window=10.0
        )
        history.record(record)
        
        # Within window - should be available
        last = history.last_reversible(10.0)
        assert last is not None
        
        # After expiry - should not be available
        last = history.last_reversible(12.0)
        assert last is None
    
    def test_undo_confirm_returns_execution_result(self):
        """INVARIANT: Undo confirm returns ExecutionResult (symmetric to execution, Week 8)"""
        config = {'require_confirmation': True, 'undo_window_seconds': 10.0}
        history = ActionHistory({'undo_window_seconds': 10.0})
        world = SmartWorldSim({}, seed=42)
        controller = UndoController(config, history, world)
        
        # Setup
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
        
        # Request and confirm undo
        controller.request_undo(current_time=2.0, system_state=SystemState.SCOPED)
        undo_result = controller.confirm_undo(current_time=3.0, system_state=SystemState.UNDO_CONFIRMING)
        
        # Verify ExecutionResult structure
        from execution.action_schema import ExecutionResult
        assert isinstance(undo_result, ExecutionResult)
        assert undo_result.ok is True
        assert undo_result.action_id.startswith("undo_")
        assert undo_result.reversible is False  # Undo itself is not reversible
        assert "Undid" in undo_result.reason
    
    def test_undo_refusal_tracking(self):
        """INVARIANT: Undo controller tracks refusal reasons (Week 8)"""
        config = {'undo_window_seconds': 10.0}
        history = ActionHistory({'undo_window_seconds': 10.0})
        world = SmartWorldSim({}, seed=42)
        controller = UndoController(config, history, world)
        
        # No action available - should refuse
        success, reason = controller.request_undo(
            current_time=1.0,
            system_state=SystemState.IDLE
        )
        assert success is False
        
        stats = controller.get_statistics()
        assert stats['total_undo_refusals'] == 1
        assert len(stats['undo_refusal_reasons']) > 0
    
    def test_undo_session_filtering(self):
        """INVARIANT: Undo can filter by session_id (Week 8 multi-user prep)"""
        config = {'undo_window_seconds': 10.0}
        history = ActionHistory(config)
        
        # Record actions from different sessions
        record1 = ActionRecord(
            action_id="action_001",
            timestamp=1.0,
            user_id="user_001",
            session_id="session_001",
            object_id="lamp_001",
            object_label="lamp",
            category="lamp",
            action_type="toggle_power",
            before_state={'power': 'off'},
            after_state={'power': 'on'},
            reversible=True,
            expires_at=11.0,
            undo_window=10.0
        )
        
        record2 = ActionRecord(
            action_id="action_002",
            timestamp=2.0,
            user_id="user_002",
            session_id="session_002",
            object_id="lamp_002",
            object_label="lamp",
            category="lamp",
            action_type="toggle_power",
            before_state={'power': 'off'},
            after_state={'power': 'on'},
            reversible=True,
            expires_at=12.0,
            undo_window=10.0
        )
        
        history.record(record1)
        history.record(record2)
        
        # Get last reversible for session_001
        last = history.last_reversible(current_time=5.0, session_id="session_001")
        assert last is not None
        assert last.session_id == "session_001"
        assert last.action_id == "action_001"
        
        # Get last reversible for session_002
        last = history.last_reversible(current_time=5.0, session_id="session_002")
        assert last is not None
        assert last.session_id == "session_002"
        assert last.action_id == "action_002"

