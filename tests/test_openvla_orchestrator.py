"""Orchestrator + OpenVLA integration tests for FSM, auth, trust, and planning."""

from __future__ import annotations

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
from src.interfaces.scene_summary import ObjectInfo, SceneSummary
from src.planning.plan_compiler import PlanCompiler


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


def _install_test_input(orch, config: dict, confirm_frames: tuple[int, ...] = (), cancel_frames: tuple[int, ...] = ()):
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


def _openvla_metadata() -> dict:
    return {
        "proposer": "openvla",
        "primitive_type": PrimitiveType.OPENVLA_TRAJECTORY.value,
        "instruction": "pick up the red cube",
        "delta_position": [0.01, 0.0, -0.02],
        "delta_rotation": [0.0, 0.0, 0.0],
        "gripper": 0.0,
        "raw_action": [0.01, 0.0, -0.02, 0.0, 0.0, 0.0, 0.0],
    }


def _openvla_proposal() -> IntentProposal:
    return IntentProposal(
        action=ActionType.CLEAN_TABLE,
        description="OpenVLA trajectory for object 1",
        source="openvla",
        confidence=0.95,
        metadata=_openvla_metadata(),
        suggested_object_ids=[1],
    )


def _scene_with_object() -> SceneSummary:
    objects = (
        ObjectInfo(
            object_id=1,
            pos_xyz=(0.4, -0.1, 0.4),
            on_table=True,
            category="red_cube",
            confidence=1.0,
        ),
    )
    return SceneSummary(
        table_id=1,
        table_position=(0.0, 0.0, 0.3),
        bin_zone_center=(0.4, 0.0, 0.75),
        bin_zone_radius=0.12,
        objects=objects,
        objects_on_table=objects,
        clutter_score=0.8,
        is_messy=True,
        timestamp_frame=1,
        rgb_snapshot=None,
        eeg_quality=None,
    )


class TestFSMWithOpenVLA:
    def test_selecting_to_confirming_with_openvla(self, monkeypatch):
        config = _base_config()
        orch = build_system(config)
        try:
            monkeypatch.setattr(orch.proposer_registry, "propose", lambda _scene: _openvla_proposal())
            orch.force_lock_target(orch.world_artifacts.object_ids[0])
            assert orch.state_machine.state == ArmUIState.SELECTING

            orch.step()
            assert orch.state_machine.state == ArmUIState.CONFIRMING
            assert orch.current_proposal is not None
            assert orch.current_proposal.source == "openvla"
            assert orch.current_proposal.metadata.get("primitive_type") == "openvla_trajectory"
        finally:
            orch.close()

    def test_confirming_to_executing_on_confirm(self, monkeypatch):
        config = _base_config()
        orch = build_system(config)
        try:
            monkeypatch.setattr(orch.proposer_registry, "propose", lambda _scene: _openvla_proposal())
            _install_test_input(orch, config, confirm_frames=(2,))
            orch.force_lock_target(orch.world_artifacts.object_ids[0])

            orch.step()  # selecting -> confirming (proposal arrives)
            assert orch.state_machine.state == ArmUIState.CONFIRMING
            assert not orch.auth_manager.is_authorized()

            orch.step()  # confirming + confirm input -> executing
            assert orch.state_machine.state == ArmUIState.EXECUTING
            assert orch.auth_manager.is_authorized()
            assert orch.auth_manager.get_active_token_id() is not None
        finally:
            orch.close()

    def test_executing_failure_returns_to_idle(self, monkeypatch):
        config = _base_config()
        orch = build_system(config)
        try:
            monkeypatch.setattr(orch.proposer_registry, "propose", lambda _scene: _openvla_proposal())
            _install_test_input(orch, config, confirm_frames=(2,))
            orch.force_lock_target(orch.world_artifacts.object_ids[0])
            orch.step()
            orch.step()
            assert orch.state_machine.state == ArmUIState.EXECUTING

            def _tick_failed(_world):
                orch.executor.last_error_code = "openvla_timeout"
                return ExecutorStatus.FAILED

            monkeypatch.setattr(orch.executor, "tick", _tick_failed)
            trust_before = orch.trust_engine.task_trust
            orch.step()

            assert orch.state_machine.state == ArmUIState.IDLE
            assert orch.trust_engine.task_trust < trust_before
            assert not orch.auth_manager.is_authorized()
        finally:
            orch.close()


class TestAuthorizationWithOpenVLA:
    def test_no_execution_without_token(self):
        config = _base_config()
        orch = build_system(config)
        try:
            primitive = Primitive(
                type=PrimitiveType.OPENVLA_TRAJECTORY,
                metadata=_openvla_metadata(),
            )
            orch.executor.start_plan([primitive])
            world = orch._read_world_state()
            status = orch.executor.tick(world)

            assert status == ExecutorStatus.FAILED
            assert orch.executor.last_error_code == "unauthorized_execution_blocked"
        finally:
            orch.close()

    def test_token_created_on_confirm(self, monkeypatch):
        config = _base_config()
        orch = build_system(config)
        try:
            monkeypatch.setattr(orch.proposer_registry, "propose", lambda _scene: _openvla_proposal())
            _install_test_input(orch, config, confirm_frames=(2,))
            orch.force_lock_target(orch.world_artifacts.object_ids[0])
            orch.step()
            assert orch.state_machine.state == ArmUIState.CONFIRMING

            orch.step()
            assert orch.auth_manager.get_active_token_id() is not None
            assert orch.auth_manager.is_authorized()
        finally:
            orch.close()


class TestTrustWithOpenVLA:
    def test_success_recovers_trust_under_cap(self, monkeypatch):
        config = _base_config()
        orch = build_system(config)
        try:
            # Set up active execution context with lower initial trust.
            orch.auth_manager.issue(
                source="test",
                quality=1.0,
                scope=orch.autonomy_policy.get_token_scope(),
                autonomy_level=orch.autonomy_policy.level.value,
                max_objects=orch.autonomy_policy.get_max_objects(),
            )
            orch.trust_engine.start_session(auth_quality=0.7)  # starts below recovery cap
            orch.state_machine._transition_to(ArmUIState.EXECUTING)

            monkeypatch.setattr(orch.executor, "tick", lambda _world: ExecutorStatus.COMPLETE)
            trust_before = orch.trust_engine.task_trust
            orch._execute_task_with_trust(orch._read_world_state())

            assert orch.trust_engine.task_trust > trust_before
        finally:
            orch.close()

    def test_trust_drop_triggers_reauth(self, monkeypatch):
        config = _base_config()
        orch = build_system(config)
        try:
            orch.auth_manager.issue(
                source="test",
                quality=1.0,
                scope=orch.autonomy_policy.get_token_scope(),
                autonomy_level=orch.autonomy_policy.level.value,
                max_objects=orch.autonomy_policy.get_max_objects(),
            )
            orch.trust_engine.start_session(auth_quality=0.0)  # starts around 0.6
            orch.state_machine._transition_to(ArmUIState.EXECUTING)

            def _tick_failed(_world):
                orch.executor.last_error_code = "openvla_timeout"  # maps to moderate penalty
                return ExecutorStatus.FAILED

            monkeypatch.setattr(orch.executor, "tick", _tick_failed)
            orch._execute_task_with_trust(orch._read_world_state())

            assert orch._safe_pause_active
            assert not orch.auth_manager.is_authorized()
        finally:
            orch.close()


class TestPlanCompilerOpenVLA:
    def test_openvla_proposal_produces_single_primitive(self):
        compiler = PlanCompiler(_base_config())
        proposal = IntentProposal(
            action=ActionType.CLEAN_TABLE,
            description="OpenVLA proposal",
            source="openvla",
            confidence=1.0,
            metadata=_openvla_metadata(),
        )
        plan = compiler.compile_proposal(proposal, _scene_with_object())

        assert len(plan) == 1
        assert plan[0].type == PrimitiveType.OPENVLA_TRAJECTORY
        assert plan[0].metadata.get("delta_position") == [0.01, 0.0, -0.02]

    def test_heuristic_proposal_still_generates_multi_primitive_plan(self):
        compiler = PlanCompiler(_base_config())
        proposal = IntentProposal(
            action=ActionType.CLEAN_TABLE,
            description="Heuristic plan",
            source="heuristic",
            confidence=1.0,
            metadata={},
        )
        plan = compiler.compile_proposal(proposal, _scene_with_object())

        assert len(plan) >= 4
        assert PrimitiveType.REACH in [p.type for p in plan]
        assert PrimitiveType.GRASP in [p.type for p in plan]
        assert PrimitiveType.RELEASE in [p.type for p in plan]
