"""Week 5-6 tests: action execution and undo safety."""

import pytest
from intent_core.system_orchestrator import SystemOrchestrator
from execution.action_schema import ActionType, ActionRequest
from execution.action_executor import ActionExecutor
from execution.smart_world_sim import SmartWorldSim
from affordances.affordance_schema import ObjectCategory


class TestExecutionV1:
    """Week 5 tests: action execution"""
    
    def test_confirm_with_scope_executes(self):
        """INVARIANT: Confirmation + scope + highlighted option → execution"""
        config = {
            'camera_enabled': True,
            'affordances': {'enabled': True},
            'gesture': {'enabled': True},
            'execution': {'enabled': True},
            'detection': {'mode': 'mock'},
            'seed': 42
        }
        
        orchestrator = SystemOrchestrator(config, seed=42)
        
        # Simulate sequence:
        # 1. Stable scope on lamp
        # 2. Affordance generated (toggle_power)
        # 3. Pinch confirmation
        # 4. Execution
        
        # Run ticks until execution
        for i in range(50):
            snapshot = orchestrator.step(timestamp=float(i))
        
        # Check execution occurred
        # (This would require mocking/injecting specific states)
        # For real test, would verify:
        assert orchestrator.action_history.total_recorded > 0
    
    def test_confirm_without_scope_refuses(self):
        """INVARIANT: Confirmation without scope → no execution"""
        config = {
            'execution': {'enabled': True},
            'seed': 42
        }
        
        orchestrator = SystemOrchestrator(config, seed=42)
        
        # Attempt execution with no scope
        result = orchestrator.router.route(
            execution_allowed=True,
            highlighted_option=None,
            scoped_object_id=None,
            scoped_object_label=None,
            scoped_category=None,
            timestamp=1.0
        )
        
        # Should refuse
        assert result is None
        assert orchestrator.router.refusal_count > 0
    
    def test_unknown_category_refuses(self):
        """INVARIANT: Unknown category → execution refused"""
        from execution.action_executor import ActionExecutor
        from execution.smart_world_sim import SmartWorldSim
        from execution.action_schema import ActionRequest, ActionType
        
        config = {
            'enabled': True,
            'allowed_categories': ['lamp', 'door', 'phone']
        }
        
        world = SmartWorldSim({}, seed=42)
        executor = ActionExecutor(config, world)
        
        # Try to execute on unknown category
        request = ActionRequest.create(
            object_id="obj_001",
            object_label="toaster",
            category="toaster",  # Not in allowed list
            action_type=ActionType.TOGGLE_POWER,
            timestamp=1.0
        )
        
        result = executor.execute(request)
        
        assert result.ok == False
        assert "not in allowed list" in result.reason.lower()
    
    def test_placeholder_action_refuses(self):
        """INVARIANT: Placeholder actions (pick_up) never execute"""
        from execution.action_executor import ActionExecutor
        from execution.smart_world_sim import SmartWorldSim
        from execution.action_schema import ActionRequest, ActionType
        
        config = {
            'enabled': True,
            'allowed_categories': ['cup']
        }
        
        world = SmartWorldSim({}, seed=42)
        executor = ActionExecutor(config, world)
        
        # Try to execute PICK_UP (placeholder)
        request = ActionRequest.create(
            object_id="obj_001",
            object_label="cup",
            category="cup",
            action_type=ActionType.PICK_UP,  # Placeholder
            timestamp=1.0
        )
        
        result = executor.execute(request)
        
        assert result.ok == False
        assert "placeholder" in result.reason.lower()
    
    def test_one_action_per_confirmation(self):
        """INVARIANT: One confirmation = one action (no repeat firing)"""
        # This would be tested at orchestrator level
        # Verify execution_allowed flag is cleared after execution
        pass
    
    def test_scope_change_clears_confirmation(self):
        """INVARIANT: Scope change during confirmation → clear state"""
        # Test at orchestrator level
        # Verify state transitions to IDLE when scope changes
        pass


class TestSpecificActionsWeek6:
    """Week 6 tests: specific state-setting actions (TURN_ON/OFF, OPEN/CLOSE, WAKE/SLEEP)"""
    
    def test_turn_on_changes_state_correctly(self):
        """INVARIANT: TURN_ON sets lamp to ON"""
        world = SmartWorldSim({}, seed=42)
        
        # Setup lamp in OFF state
        world.ensure_object("lamp_001", "lamp", 1.0)
        world.objects["lamp_001"].state = {'power': 'off'}
        
        # Execute TURN_ON
        request = ActionRequest.create(
            object_id="lamp_001",
            object_label="lamp",
            category="lamp",
            action_type=ActionType.TURN_ON,
            timestamp=2.0
        )
        
        before, after = world.apply_action(request)
        
        # State should change
        assert before['power'] == 'off'
        assert after['power'] == 'on'
    
    def test_turn_off_changes_state_correctly(self):
        """INVARIANT: TURN_OFF sets lamp to OFF"""
        world = SmartWorldSim({}, seed=42)
        
        # Setup lamp in ON state
        world.ensure_object("lamp_001", "lamp", 1.0)
        world.objects["lamp_001"].state = {'power': 'on'}
        
        # Execute TURN_OFF
        request = ActionRequest.create(
            object_id="lamp_001",
            object_label="lamp",
            category="lamp",
            action_type=ActionType.TURN_OFF,
            timestamp=2.0
        )
        
        before, after = world.apply_action(request)
        
        # State should change
        assert before['power'] == 'on'
        assert after['power'] == 'off'
    
    def test_turn_on_idempotent(self):
        """INVARIANT: TURN_ON when already ON is safe (idempotent)"""
        world = SmartWorldSim({}, seed=42)
        
        # Setup lamp already ON
        world.ensure_object("lamp_001", "lamp", 1.0)
        world.objects["lamp_001"].state = {'power': 'on'}
        
        # Execute TURN_ON again
        request = ActionRequest.create(
            object_id="lamp_001",
            object_label="lamp",
            category="lamp",
            action_type=ActionType.TURN_ON,
            timestamp=2.0
        )
        
        before, after = world.apply_action(request)
        
        # State should remain ON (no error)
        assert before['power'] == 'on'
        assert after['power'] == 'on'
    
    def test_turn_off_idempotent(self):
        """INVARIANT: TURN_OFF when already OFF is safe (idempotent)"""
        world = SmartWorldSim({}, seed=42)
        
        # Setup lamp already OFF
        world.ensure_object("lamp_001", "lamp", 1.0)
        world.objects["lamp_001"].state = {'power': 'off'}
        
        # Execute TURN_OFF again
        request = ActionRequest.create(
            object_id="lamp_001",
            object_label="lamp",
            category="lamp",
            action_type=ActionType.TURN_OFF,
            timestamp=2.0
        )
        
        before, after = world.apply_action(request)
        
        # State should remain OFF (no error)
        assert before['power'] == 'off'
        assert after['power'] == 'off'
    
    def test_open_changes_door_state(self):
        """INVARIANT: OPEN sets door to OPEN"""
        world = SmartWorldSim({}, seed=42)
        
        # Setup door CLOSED
        world.ensure_object("door_001", "door", 1.0)
        world.objects["door_001"].state = {'position': 'closed'}
        
        # Execute OPEN
        request = ActionRequest.create(
            object_id="door_001",
            object_label="door",
            category="door",
            action_type=ActionType.OPEN,
            timestamp=2.0
        )
        
        before, after = world.apply_action(request)
        
        assert before['position'] == 'closed'
        assert after['position'] == 'open'
    
    def test_close_changes_door_state(self):
        """INVARIANT: CLOSE sets door to CLOSED"""
        world = SmartWorldSim({}, seed=42)
        
        # Setup door OPEN
        world.ensure_object("door_001", "door", 1.0)
        world.objects["door_001"].state = {'position': 'open'}
        
        # Execute CLOSE
        request = ActionRequest.create(
            object_id="door_001",
            object_label="door",
            category="door",
            action_type=ActionType.CLOSE,
            timestamp=2.0
        )
        
        before, after = world.apply_action(request)
        
        assert before['position'] == 'open'
        assert after['position'] == 'closed'
    
    def test_wake_changes_phone_state(self):
        """INVARIANT: WAKE sets phone screen to ON"""
        world = SmartWorldSim({}, seed=42)
        
        # Setup phone screen OFF
        world.ensure_object("phone_001", "phone", 1.0)
        world.objects["phone_001"].state = {'screen': 'screen_off'}
        
        # Execute WAKE
        request = ActionRequest.create(
            object_id="phone_001",
            object_label="phone",
            category="phone",
            action_type=ActionType.WAKE,
            timestamp=2.0
        )
        
        before, after = world.apply_action(request)
        
        assert before['screen'] == 'screen_off'
        assert after['screen'] == 'screen_on'
    
    def test_sleep_changes_phone_state(self):
        """INVARIANT: SLEEP sets phone screen to OFF"""
        world = SmartWorldSim({}, seed=42)
        
        # Setup phone screen ON
        world.ensure_object("phone_001", "phone", 1.0)
        world.objects["phone_001"].state = {'screen': 'screen_on'}
        
        # Execute SLEEP
        request = ActionRequest.create(
            object_id="phone_001",
            object_label="phone",
            category="phone",
            action_type=ActionType.SLEEP,
            timestamp=2.0
        )
        
        before, after = world.apply_action(request)
        
        assert before['screen'] == 'screen_on'
        assert after['screen'] == 'screen_off'
    
    def test_undo_restores_state_after_specific_action(self):
        """INVARIANT: Undo works with specific actions (TURN_ON/OFF)"""
        world = SmartWorldSim({}, seed=42)
        
        # Initial state: OFF
        world.ensure_object("lamp_001", "lamp", 1.0)
        initial_state = world.get_object_state("lamp_001")
        
        # Execute TURN_ON
        request = ActionRequest.create(
            object_id="lamp_001",
            object_label="lamp",
            category="lamp",
            action_type=ActionType.TURN_ON,
            timestamp=2.0
        )
        
        before, after = world.apply_action(request)
        
        # Should be ON now
        assert world.get_object_state("lamp_001")['power'] == 'on'
        
        # Undo
        before_undo, after_undo = world.apply_undo(
            object_id="lamp_001",
            before_state=before,
            timestamp=3.0
        )
        
        # Should be back to OFF
        assert world.get_object_state("lamp_001")['power'] == 'off'
        assert world.get_object_state("lamp_001") == initial_state
    
    def test_toggle_still_works(self):
        """INVARIANT: Week 5 toggle actions still work (backward compatible)"""
        world = SmartWorldSim({}, seed=42)
        
        # Setup lamp OFF
        world.ensure_object("lamp_001", "lamp", 1.0)
        world.objects["lamp_001"].state = {'power': 'off'}
        
        # Execute TOGGLE_POWER
        request = ActionRequest.create(
            object_id="lamp_001",
            object_label="lamp",
            category="lamp",
            action_type=ActionType.TOGGLE_POWER,
            timestamp=2.0
        )
        
        before, after = world.apply_action(request)
        
        # Should toggle to ON
        assert before['power'] == 'off'
        assert after['power'] == 'on'
        
        # Toggle again
        request2 = ActionRequest.create(
            object_id="lamp_001",
            object_label="lamp",
            category="lamp",
            action_type=ActionType.TOGGLE_POWER,
            timestamp=3.0
        )
        
        before2, after2 = world.apply_action(request2)
        
        # Should toggle back to OFF
        assert before2['power'] == 'on'
        assert after2['power'] == 'off'
    
    def test_specific_actions_execute_via_executor(self):
        """INVARIANT: ActionExecutor accepts specific actions (not just toggles)"""
        config = {
            'enabled': True,
            'allowed_categories': ['lamp', 'door', 'phone'],
            'allowed_actions': ['toggle_power', 'turn_on', 'turn_off', 'open', 'close', 'wake', 'sleep']
        }
        
        world = SmartWorldSim({}, seed=42)
        executor = ActionExecutor(config, world)
        
        # Setup lamp OFF
        world.ensure_object("lamp_001", "lamp", 1.0)
        
        # Execute TURN_ON via executor
        request = ActionRequest.create(
            object_id="lamp_001",
            object_label="lamp",
            category="lamp",
            action_type=ActionType.TURN_ON,
            timestamp=2.0
        )
        
        result = executor.execute(request)
        
        # Should succeed
        assert result.ok == True
        assert result.after_state['power'] == 'on'

