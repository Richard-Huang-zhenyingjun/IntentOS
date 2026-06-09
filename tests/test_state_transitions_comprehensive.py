from src.core.schema import ArmActionType, ArmDecision, ArmUIState, DecisionSignal
from src.core.state_machine import StateMachine
from src.core.system_factory import build_system, load_config


def test_fsm_happy_path_transitions():
    """IDLE -> SELECTING -> CONFIRMING -> EXECUTING -> DONE -> IDLE."""
    sm = StateMachine()
    assert sm.state == ArmUIState.IDLE

    sm.set_target(target_id=10, locked=True)
    assert sm.state == ArmUIState.SELECTING

    sm.propose_action(ArmActionType.CLEAN_TABLE, "test-proposal")
    assert sm.state == ArmUIState.CONFIRMING
    assert sm.proposal is not None

    allowed = sm.process_decision(
        ArmDecision(
            signal=DecisionSignal.CONFIRM,
            confidence=1.0,
            source="test",
            timestamp=0.0,
        )
    )
    assert allowed
    assert sm.state == ArmUIState.EXECUTING

    sm.complete_execution()
    assert sm.state == ArmUIState.DONE
    assert sm.proposal is None

    sm.reset()
    assert sm.state == ArmUIState.IDLE


def test_fsm_cancel_path_and_guardrails():
    """Confirming cancel path and propose-without-target guard."""
    sm = StateMachine()
    sm.propose_action(ArmActionType.CLEAN_TABLE, "no-target")
    assert sm.state == ArmUIState.IDLE

    sm.set_target(target_id=20, locked=True)
    sm.propose_action(ArmActionType.CLEAN_TABLE, "with-target")
    assert sm.state == ArmUIState.CONFIRMING

    allowed = sm.process_decision(
        ArmDecision(
            signal=DecisionSignal.CANCEL,
            confidence=1.0,
            source="test",
            timestamp=0.0,
        )
    )
    assert not allowed
    assert sm.state == ArmUIState.SELECTING
    assert sm.proposal is None


def test_pause_and_resume_transitions():
    """IDLE -> PAUSED -> IDLE flow."""
    sm = StateMachine()
    sm.trigger_pause("manual-pause")
    assert sm.state == ArmUIState.PAUSED
    assert sm.paused
    assert sm.pause_reason == "manual-pause"

    sm.resume_from_pause()
    assert sm.state == ArmUIState.IDLE
    assert not sm.paused
    assert sm.pause_reason == ""


def test_orchestrator_trust_drop_drives_safe_pause_then_confirming():
    """
    EXECUTING -> safe pause -> CONFIRMING re-auth flow.
    (In current implementation trust drop does not use PAUSED state.)
    """
    config = load_config("configs/default.yaml")
    config.setdefault("simulator", {})
    config["simulator"]["use_gui"] = False
    config.setdefault("gemini", {})
    config["gemini"]["enabled"] = False
    config.setdefault("eeg", {})
    config["eeg"]["enabled"] = False
    config.setdefault("logging", {})
    config["logging"]["events_enabled"] = False

    orch = build_system(config)
    try:
        # Speed up primitive completion for deterministic safe pause execution.
        controller = orch.executor.controller

        def _update_fast(_current_state):
            if not controller.executing:
                return False
            controller.executing = False
            controller.target_joints = None
            controller._settle_counter = 0
            return True

        controller.update = _update_fast

        orch.state_machine._transition_to(ArmUIState.EXECUTING)
        orch._trigger_reauth("unit-test-trust-drop")
        assert orch._safe_pause_active
        assert not orch.auth_manager.is_authorized()

        for _ in range(60):
            orch.sim.step()
            world = orch._read_world_state()
            orch._execute_safe_pause(world)
            if not orch._safe_pause_active:
                break

        assert not orch._safe_pause_active
        assert orch.state_machine.state == ArmUIState.CONFIRMING
        assert orch._awaiting_reauth
    finally:
        orch.close()


def test_orchestrator_divergence_sets_paused():
    """Divergence handler should set PAUSED state and reason."""
    config = load_config("configs/default.yaml")
    config.setdefault("simulator", {})
    config["simulator"]["use_gui"] = False
    config.setdefault("gemini", {})
    config["gemini"]["enabled"] = False
    config.setdefault("eeg", {})
    config["eeg"]["enabled"] = False
    config.setdefault("logging", {})
    config["logging"]["events_enabled"] = False

    orch = build_system(config)
    try:
        orch._handle_physics_divergence()
        assert orch.state_machine.state == ArmUIState.PAUSED
        assert orch.state_machine.paused
        assert "Physics divergence detected" in orch.state_machine.pause_reason
    finally:
        orch.close()
