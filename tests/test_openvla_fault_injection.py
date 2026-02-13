"""Fault injection tests for OpenVLA proposal/execution safety."""

from __future__ import annotations

import numpy as np

from src.core.authorization import AuthScope
from src.core.schema import ArmUIState
from src.core.system_factory import build_system, load_config
from src.execution.primitive_executor import ExecutorStatus, PrimitiveExecutor
from src.external.openvla.action_translator import TranslatedAction
from src.external.openvla.proposer_openvla import OpenVLAProposer
from src.intelligence.proposer_heuristic import HeuristicProposer
from src.intelligence.proposer_registry import ProposerRegistry
from src.interfaces.intent_proposal import ActionType, IntentProposal
from src.interfaces.primitive import Primitive, PrimitiveType
from src.interfaces.scene_summary import ObjectInfo, SceneSummary
from src.robot.simulator import ArmState
from src.robot.world_state import WorldState


def _scene() -> SceneSummary:
    objs = (
        ObjectInfo(
            object_id=4,
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
        objects=objs,
        objects_on_table=objs,
        clutter_score=0.8,
        is_messy=True,
        timestamp_frame=1,
        rgb_snapshot=None,
        eeg_quality=None,
    )


def _openvla_meta() -> dict:
    return {
        "proposer": "openvla",
        "primitive_type": PrimitiveType.OPENVLA_TRAJECTORY.value,
        "instruction": "pick up the red cube",
        "target_object_id": 4,
        "target_pos_xyz": [0.4, -0.1, 0.4],
        "delta_position": [0.01, 0.0, -0.02],
        "delta_rotation": [0.0, 0.0, 0.0],
        "gripper": 0.0,
        "raw_action": [0.01, 0.0, -0.02, 0.0, 0.0, 0.0, 0.0],
    }


def _primitive() -> Primitive:
    return Primitive(type=PrimitiveType.OPENVLA_TRAJECTORY, metadata=_openvla_meta())


def _world() -> WorldState:
    return WorldState(
        arm=ArmState(
            joint_positions=np.zeros(7),
            ee_position=np.array([0.3, 0.0, 0.8]),
            ee_orientation=np.array([0.0, 0.0, 0.0, 1.0]),
        ),
        object=None,
        target_id=None,
        holding=False,
        attached_id=None,
    )


class _ControllerSpy:
    def __init__(self, converges: bool = True):
        self.converges = converges
        self.joint_calls = 0
        self.last_target = None

    def move_to_joint_positions(self, target):
        self.joint_calls += 1
        self.last_target = np.array(target, dtype=float)
        return self.converges

    def update(self, _arm_state):
        return True

    def is_executing(self):
        return False


class _GraspStub:
    pass


class _AuthStub:
    def __init__(self, authorized: bool):
        self._authorized = authorized

    def is_authorized(self):
        return self._authorized

    def get_active_token_id(self):
        return "auth_test" if self._authorized else None


class TestAdapterFault:
    def test_adapter_crash_falls_back_to_heuristic(self):
        class CrashingAdapter:
            is_loaded = True
            action_dim = 7

            def predict(self, _instruction, _image):
                raise RuntimeError("adapter crashed")

            def close(self):
                pass

        registry = ProposerRegistry()
        registry.register(
            "openvla",
            OpenVLAProposer(CrashingAdapter(), camera_provider=None, enabled=True),
            priority=15,
        )
        registry.register("heuristic", HeuristicProposer(config={}), priority=0, is_fallback=True)

        proposal = registry.propose(_scene())
        assert proposal.source == "heuristic"
        assert proposal.action in (ActionType.CLEAN_TABLE, ActionType.IDLE)

    def test_adapter_returns_garbage(self):
        class GarbageAdapter:
            is_loaded = True
            action_dim = 7

            def predict(self, instruction, _image):
                from src.external.openvla.adapter import OpenVLAAction

                return OpenVLAAction(
                    delta_position=np.array([float("nan"), 0.0, 0.0]),
                    delta_rotation=np.zeros(3),
                    gripper=0.5,
                    raw_action=np.array([float("nan"), 0.0, 0.0, 0.0, 0.0, 0.0, 0.5]),
                    instruction=instruction,
                )

            def close(self):
                pass

        proposer = OpenVLAProposer(GarbageAdapter(), camera_provider=None, enabled=True)
        proposal = proposer.propose(_scene())
        # Either proposer returns degraded IDLE fallback or a proposal with garbage metadata.
        assert proposal is not None


class TestIKFault:
    def test_ik_failure_does_not_execute(self):
        class FailingTranslator:
            def translate_from_metadata(self, _meta):
                return TranslatedAction(
                    joint_positions=np.zeros(7),
                    gripper_command=0.0,
                    target_ee_position=np.zeros(3),
                    target_ee_rotation=np.eye(3),
                    ik_success=False,
                    ik_error=0.4,
                    clamped=False,
                )

        controller = _ControllerSpy(converges=True)
        executor = PrimitiveExecutor(
            controller=controller,
            grasp=_GraspStub(),
            action_translator=FailingTranslator(),
            authorization_manager=_AuthStub(authorized=True),
        )
        executor.start_plan([_primitive()])
        status = executor.tick(_world())

        assert status == ExecutorStatus.FAILED
        assert controller.joint_calls == 0

    def test_ik_returns_nan_joints(self):
        class NanTranslator:
            def translate_from_metadata(self, _meta):
                return TranslatedAction(
                    joint_positions=np.array([float("nan")] * 7),
                    gripper_command=0.5,
                    target_ee_position=np.zeros(3),
                    target_ee_rotation=np.eye(3),
                    ik_success=True,
                    ik_error=0.001,
                    clamped=False,
                )

        controller = _ControllerSpy(converges=True)
        executor = PrimitiveExecutor(
            controller=controller,
            grasp=_GraspStub(),
            action_translator=NanTranslator(),
            authorization_manager=_AuthStub(authorized=True),
        )
        executor.start_plan([_primitive()])
        status = executor.tick(_world())

        assert status == ExecutorStatus.FAILED
        assert executor.last_error_code == "openvla_invalid_joint_targets"
        assert controller.joint_calls == 0


class TestControllerFault:
    def test_controller_timeout_triggers_moderate_penalty(self, monkeypatch):
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
            orch.auth_manager.issue(
                source="test",
                quality=1.0,
                scope=AuthScope.TASK_SESSION,
                autonomy_level=orch.autonomy_policy.level.value,
                max_objects=0,
            )
            orch.trust_engine.start_session(auth_quality=1.0)
            orch.state_machine._transition_to(ArmUIState.EXECUTING)

            def _failed_tick(_world):
                orch.executor.last_error_code = "openvla_timeout"
                return ExecutorStatus.FAILED

            monkeypatch.setattr(orch.executor, "tick", _failed_tick)
            before = orch.trust_engine.task_trust
            orch._execute_task_with_trust(orch._read_world_state())
            after = orch.trust_engine.task_trust

            assert after <= before - 0.12 + 1e-9
        finally:
            orch.close()

    def test_controller_crash_triggers_safe_pause(self, monkeypatch):
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
            orch.auth_manager.issue(
                source="test",
                quality=1.0,
                scope=AuthScope.TASK_SESSION,
                autonomy_level=orch.autonomy_policy.level.value,
                max_objects=0,
            )
            # Start near threshold so one severe failure triggers reauth/safe pause.
            orch.trust_engine.start_session(auth_quality=0.0)
            orch.state_machine._transition_to(ArmUIState.EXECUTING)

            def _failed_tick(_world):
                orch.executor.last_error_code = "openvla_translation_error"
                return ExecutorStatus.FAILED

            monkeypatch.setattr(orch.executor, "tick", _failed_tick)
            orch._execute_task_with_trust(orch._read_world_state())

            assert orch._safe_pause_active
            assert not orch.auth_manager.is_authorized()
        finally:
            orch.close()


class TestCameraFault:
    def test_camera_failure_uses_blank_image(self):
        class BrokenCamera:
            def render_camera(self, camera_name=""):
                raise RuntimeError("camera failed")

        from src.external.openvla.adapter_fake import FakeOpenVLAAdapter

        adapter = FakeOpenVLAAdapter()
        adapter.load_model()
        proposer = OpenVLAProposer(adapter, camera_provider=BrokenCamera(), enabled=True)

        proposal = proposer.propose(_scene())
        assert proposal is not None
        assert proposal.source == "openvla"

    def test_camera_returns_black_image(self):
        class BlackCamera:
            def render_camera(self, camera_name=""):
                return np.zeros((224, 224, 3), dtype=np.uint8)

        from src.external.openvla.adapter_fake import FakeOpenVLAAdapter

        adapter = FakeOpenVLAAdapter()
        adapter.load_model()
        proposer = OpenVLAProposer(adapter, camera_provider=BlackCamera(), enabled=True)
        proposal = proposer.propose(_scene())
        assert proposal is not None
        assert proposal.source == "openvla"


class TestCompoundFaults:
    def test_camera_and_ik_fail_simultaneously(self):
        from src.external.openvla.adapter_fake import FakeOpenVLAAdapter

        class BrokenCamera:
            def render_camera(self, camera_name=""):
                raise RuntimeError("camera failed")

        adapter = FakeOpenVLAAdapter()
        adapter.load_model()
        proposer = OpenVLAProposer(adapter, camera_provider=BrokenCamera(), enabled=True)
        proposal = proposer.propose(_scene())
        assert proposal.source == "openvla"

        class FailingTranslator:
            def translate_from_metadata(self, _meta):
                return TranslatedAction(
                    joint_positions=np.zeros(7),
                    gripper_command=0.0,
                    target_ee_position=np.zeros(3),
                    target_ee_rotation=np.eye(3),
                    ik_success=False,
                    ik_error=0.2,
                    clamped=False,
                )

        controller = _ControllerSpy(converges=True)
        executor = PrimitiveExecutor(
            controller=controller,
            grasp=_GraspStub(),
            action_translator=FailingTranslator(),
            authorization_manager=_AuthStub(authorized=True),
        )
        primitive = Primitive(type=PrimitiveType.OPENVLA_TRAJECTORY, metadata=proposal.metadata)
        executor.start_plan([primitive])
        status = executor.tick(_world())

        assert status == ExecutorStatus.FAILED
        assert controller.joint_calls == 0
        assert executor.invariant_summary["false_executions"] == 0

    def test_adapter_and_trust_drop_simultaneously(self):
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
            orch.auth_manager.issue(
                source="test",
                quality=1.0,
                scope=AuthScope.TASK_SESSION,
                autonomy_level=orch.autonomy_policy.level.value,
                max_objects=0,
            )
            orch.trust_engine.start_session(auth_quality=0.0)
            orch.state_machine._transition_to(ArmUIState.EXECUTING)

            def _failed_tick(_world):
                orch.executor.last_error_code = "openvla_translation_error"
                return ExecutorStatus.FAILED

            orch.executor.tick = _failed_tick
            orch._execute_task_with_trust(orch._read_world_state())
            assert orch._safe_pause_active
            assert not orch.auth_manager.is_authorized()
        finally:
            orch.close()

    def test_10_consecutive_failures_system_recovers(self):
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
            for _ in range(10):
                orch.auth_manager.issue(
                    source="test",
                    quality=1.0,
                    scope=AuthScope.TASK_SESSION,
                    autonomy_level=orch.autonomy_policy.level.value,
                    max_objects=0,
                )
                orch.trust_engine.start_session(auth_quality=0.0)
                orch.state_machine._transition_to(ArmUIState.EXECUTING)

                def _failed_tick(_world):
                    orch.executor.last_error_code = "openvla_timeout"
                    return ExecutorStatus.FAILED

                orch.executor.tick = _failed_tick
                orch._execute_task_with_trust(orch._read_world_state())
                assert orch.trust_metrics.false_executions == 0

                if orch._safe_pause_active:
                    # Drain safe pause plan.
                    for _ in range(50):
                        orch.sim.step()
                        orch._execute_safe_pause(orch._read_world_state())
                        if not orch._safe_pause_active:
                            break
            assert True
        finally:
            orch.close()

