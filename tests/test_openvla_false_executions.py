"""false_executions == 0 verification for the OpenVLA execution path."""

from __future__ import annotations

import random

from src.core.authorization import AuthScope
from src.core.schema import ArmUIState
from src.core.system_factory import build_system, load_config
from src.execution.primitive_executor import ExecutorStatus
from src.input.filter import DecisionFilter
from src.input.pipeline import DecisionPipeline
from src.input.policies import DecisionPolicy
from src.input.router import DecisionRouter
from src.input.source_fake import FakeSource
from src.interfaces.intent_proposal import ActionType, IntentProposal
from src.interfaces.primitive import Primitive, PrimitiveType


def openvla_metadata() -> dict:
    return {
        "proposer": "openvla",
        "primitive_type": PrimitiveType.OPENVLA_TRAJECTORY.value,
        "instruction": "pick up the red cube",
        "target_object_id": 4,
        "target_pos_xyz": [0.4, 0.0, 0.6],
        "delta_position": [0.01, 0.0, -0.02],
        "delta_rotation": [0.0, 0.0, 0.0],
        "gripper": 0.0,
        "raw_action": [0.01, 0.0, -0.02, 0.0, 0.0, 0.0, 0.0],
        "confidence": 0.95,
    }


def _openvla_proposal() -> IntentProposal:
    return IntentProposal(
        action=ActionType.CLEAN_TABLE,
        description="OpenVLA trajectory proposal",
        source="openvla",
        confidence=0.95,
        metadata=openvla_metadata(),
        suggested_object_ids=[4],
    )


def _base_config() -> dict:
    config = load_config("configs/default.yaml")
    config.setdefault("simulator", {})
    config["simulator"]["use_gui"] = False
    config.setdefault("gemini", {})
    config["gemini"]["enabled"] = False
    config.setdefault("eeg", {})
    config["eeg"]["enabled"] = False
    config.setdefault("logging", {})
    config["logging"]["events_enabled"] = False
    config.setdefault("openvla", {})
    config["openvla"]["enabled"] = True
    config["openvla"]["use_fake"] = True
    return config


def _install_fake_input(orch, config: dict, confirm_frames=(), cancel_frames=()):
    cfg = dict(config)
    cfg["input"] = dict(config.get("input", {}))
    cfg["input"]["mode"] = "KEYBOARD_ONLY"
    cfg["input"]["sources_enabled"] = ["keyboard"]
    cfg["input"]["debounce_frames"] = 0
    cfg["input"]["confirm_hold_frames"] = 1
    cfg["input"]["min_quality"] = 0.0

    policy = DecisionPolicy.from_config(cfg)
    router = DecisionRouter(policy)
    fake = FakeSource()
    for frame in confirm_frames:
        fake.set_confirm_on_frame(frame)
    for frame in cancel_frames:
        fake.set_cancel_on_frame(frame)
    router.register_source("keyboard", fake)
    orch.decision_pipeline = DecisionPipeline(router, DecisionFilter(cfg))


def _setup_with_forced_openvla(confirm_frames=(), cancel_frames=()):
    config = _base_config()
    orch = build_system(config)
    _install_fake_input(orch, config, confirm_frames=confirm_frames, cancel_frames=cancel_frames)
    orch.proposer_registry.propose = lambda _scene: _openvla_proposal()
    if orch.world_artifacts and orch.world_artifacts.object_ids:
        orch.force_lock_target(orch.world_artifacts.object_ids[0])
    return orch


class TestNormalAuthorizedFlow:
    def test_confirmed_openvla_execution_succeeds(self, monkeypatch):
        orch = _setup_with_forced_openvla(confirm_frames=(2,))
        try:
            monkeypatch.setattr(orch.executor, "tick", lambda _world: ExecutorStatus.COMPLETE)

            orch.step()  # selecting -> confirming
            assert orch.state_machine.state == ArmUIState.CONFIRMING

            orch.step()  # confirm -> executing
            assert orch.state_machine.state == ArmUIState.EXECUTING
            assert orch.auth_manager.is_authorized()

            orch.step()  # executing -> complete -> done
            orch.step()  # done -> idle
            assert orch.state_machine.state in (ArmUIState.DONE, ArmUIState.IDLE)
            assert orch.trust_metrics.false_executions == 0
        finally:
            orch.close()

    def test_confirmed_execution_has_valid_token(self, monkeypatch):
        orch = _setup_with_forced_openvla(confirm_frames=(2,))
        try:
            monkeypatch.setattr(orch.executor, "tick", lambda _world: ExecutorStatus.COMPLETE)
            orch.step()
            orch.step()
            assert orch.auth_manager.get_active_token_id() is not None
            assert orch.auth_manager.is_authorized()
        finally:
            orch.close()


class TestNoConfirmation:
    def test_execute_without_confirm_blocked(self):
        orch = _setup_with_forced_openvla(confirm_frames=())
        try:
            orch.step()  # selecting -> confirming, but no token issued
            assert orch.state_machine.state == ArmUIState.CONFIRMING
            assert not orch.auth_manager.is_authorized()

            primitive = Primitive(type=PrimitiveType.OPENVLA_TRAJECTORY, metadata=openvla_metadata())
            orch.executor.start_plan([primitive])
            status = orch.executor.tick(orch._read_world_state())

            assert status == ExecutorStatus.FAILED
            assert orch.executor.last_error_code == "unauthorized_execution_blocked"
            assert orch.trust_metrics.false_executions == 0
        finally:
            orch.close()

    def test_fsm_blocks_execution_in_confirming_state(self):
        orch = _setup_with_forced_openvla(confirm_frames=(), cancel_frames=())
        try:
            orch.step()  # selecting -> confirming
            assert orch.state_machine.state == ArmUIState.CONFIRMING
            # Without confirm/cancel signals, FSM must stay in confirming.
            for _ in range(8):
                orch.step()
            assert orch.state_machine.state == ArmUIState.CONFIRMING
            assert not orch.auth_manager.is_authorized()
        finally:
            orch.close()


class TestExpiredToken:
    def test_expired_token_blocks_execution(self):
        orch = _setup_with_forced_openvla(confirm_frames=())
        try:
            orch.auth_manager.issue(
                source="test",
                quality=1.0,
                scope=AuthScope.TASK_SESSION,
                autonomy_level=orch.autonomy_policy.level.value,
                max_objects=0,
            )
            orch.auth_manager.complete()  # token no longer active
            assert not orch.auth_manager.is_authorized()

            primitive = Primitive(type=PrimitiveType.OPENVLA_TRAJECTORY, metadata=openvla_metadata())
            orch.executor.start_plan([primitive])
            status = orch.executor.tick(orch._read_world_state())
            assert status == ExecutorStatus.FAILED
            assert orch.executor.last_error_code == "unauthorized_execution_blocked"
        finally:
            orch.close()


class TestRevokedToken:
    def test_revoked_token_blocks_execution(self):
        orch = _setup_with_forced_openvla(confirm_frames=())
        try:
            orch.auth_manager.issue(
                source="test",
                quality=1.0,
                scope=AuthScope.TASK_SESSION,
                autonomy_level=orch.autonomy_policy.level.value,
                max_objects=0,
            )
            orch.auth_manager.invalidate("revoked_for_test")
            assert not orch.auth_manager.is_authorized()

            primitive = Primitive(type=PrimitiveType.OPENVLA_TRAJECTORY, metadata=openvla_metadata())
            orch.executor.start_plan([primitive])
            status = orch.executor.tick(orch._read_world_state())
            assert status == ExecutorStatus.FAILED
            assert orch.executor.last_error_code == "unauthorized_execution_blocked"
        finally:
            orch.close()

    def test_trust_drop_revokes_token(self, monkeypatch):
        orch = _setup_with_forced_openvla(confirm_frames=())
        try:
            orch.auth_manager.issue(
                source="test",
                quality=1.0,
                scope=AuthScope.TASK_SESSION,
                autonomy_level=orch.autonomy_policy.level.value,
                max_objects=0,
            )
            orch.trust_engine.start_session(auth_quality=0.0)  # ~0.6 initial trust
            orch.state_machine._transition_to(ArmUIState.EXECUTING)

            def _tick_failed(_world):
                orch.executor.last_error_code = "openvla_timeout"
                return ExecutorStatus.FAILED

            monkeypatch.setattr(orch.executor, "tick", _tick_failed)
            orch._execute_task_with_trust(orch._read_world_state())

            assert orch._safe_pause_active
            assert not orch.auth_manager.is_authorized()
        finally:
            orch.close()


class TestDoubleExecution:
    def test_token_consumed_after_first_execution(self, monkeypatch):
        orch = _setup_with_forced_openvla(confirm_frames=(2,))
        try:
            original_tick = orch.executor.tick
            monkeypatch.setattr(orch.executor, "tick", lambda _world: ExecutorStatus.COMPLETE)
            orch.step()
            orch.step()  # token issued
            orch.step()  # execution complete path
            assert not orch.auth_manager.is_authorized()

            # Restore real executor tick so authorization gate is exercised.
            orch.executor.tick = original_tick
            primitive = Primitive(type=PrimitiveType.OPENVLA_TRAJECTORY, metadata=openvla_metadata())
            orch.executor.start_plan([primitive])
            status = orch.executor.tick(orch._read_world_state())
            assert status == ExecutorStatus.FAILED
            assert orch.executor.last_error_code == "unauthorized_execution_blocked"
        finally:
            orch.close()


class TestRaceCondition:
    def test_rapid_confirm_does_not_double_execute(self, monkeypatch):
        orch = _setup_with_forced_openvla(confirm_frames=(2, 3, 4, 5, 6))
        try:
            # Keep execution running briefly to ensure extra confirms happen during EXECUTING.
            counter = {"n": 0}

            def _tick(_world):
                counter["n"] += 1
                return ExecutorStatus.RUNNING if counter["n"] < 4 else ExecutorStatus.COMPLETE

            monkeypatch.setattr(orch.executor, "tick", _tick)

            token_ids = []
            for _ in range(12):
                orch.step()
                token_ids.append(orch.auth_manager.get_active_token_id())

            non_null = [tok for tok in token_ids if tok is not None]
            # Exactly one active token should exist during the single execution cycle.
            assert len(set(non_null)) <= 1
            assert orch.auth_manager.tokens_issued == 1
            assert orch.trust_metrics.false_executions == 0
        finally:
            orch.close()


class TestCrashRecovery:
    def test_executor_crash_does_not_leak_execution(self):
        orch = _setup_with_forced_openvla(confirm_frames=())
        try:
            class _CrashTranslator:
                def translate_from_metadata(self, _metadata):
                    raise RuntimeError("simulated translator crash")

            orch.executor.action_translator = _CrashTranslator()
            orch.auth_manager.issue(
                source="test",
                quality=1.0,
                scope=AuthScope.TASK_SESSION,
                autonomy_level=orch.autonomy_policy.level.value,
                max_objects=0,
            )
            primitive = Primitive(type=PrimitiveType.OPENVLA_TRAJECTORY, metadata=openvla_metadata())
            orch.executor.start_plan([primitive])
            status = orch.executor.tick(orch._read_world_state())

            assert status == ExecutorStatus.FAILED
            assert orch.executor.last_error_code == "openvla_translation_error"
            assert orch.trust_metrics.false_executions == 0
        finally:
            orch.close()


class TestFuzzConfirmReject:
    def test_random_confirm_reject_maintains_invariant(self):
        seed = 123
        rng = random.Random(seed)
        confirm_frames = []
        cancel_frames = []
        for frame in range(2, 202):
            if rng.random() < 0.5:
                confirm_frames.append(frame)
            else:
                cancel_frames.append(frame)

        orch = _setup_with_forced_openvla(confirm_frames=tuple(confirm_frames), cancel_frames=tuple(cancel_frames))
        try:
            for _ in range(240):
                orch.step()
            assert orch.trust_metrics.false_executions == 0
        finally:
            orch.close()

    def test_1000_frames_no_false_executions(self):
        orch = _setup_with_forced_openvla(confirm_frames=tuple(range(2, 1000, 10)))
        try:
            for _ in range(1000):
                orch.step()
            assert orch.trust_metrics.false_executions == 0
        finally:
            orch.close()
