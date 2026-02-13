"""
Tests for OpenVLA execution with authorization gate.

Run: pytest tests/test_openvla_execution.py -v
"""
from __future__ import annotations

import numpy as np

from src.core.authorization import AuthScope, AuthorizationManager
from src.core.trust import TrustEngine
from src.execution.primitive_executor import ExecutorStatus, PrimitiveExecutor
from src.external.openvla.action_translator import TranslatedAction
from src.external.openvla.action_translator_fake import FakeActionTranslator
from src.interfaces.primitive import Primitive, PrimitiveType
from src.robot.simulator import ArmState
from src.robot.world_state import WorldState


def make_openvla_metadata():
    return {
        "proposer": "openvla",
        "instruction": "pick up the red cube",
        "delta_position": [0.01, 0.0, -0.02],
        "delta_rotation": [0.0, 0.0, 0.0],
        "gripper": 0.0,
        "raw_action": [0.01, 0.0, -0.02, 0.0, 0.0, 0.0, 0.0],
        "confidence": 0.95,
    }


def _world():
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
        self.move_calls = 0
        self.last_joint_target = None
        self.last_xyz_target = None

    def move_to_joint_positions(self, target_positions):
        self.joint_calls += 1
        self.last_joint_target = np.array(target_positions, dtype=float)
        return self.converges

    def move_to_position(self, target_xyz):
        self.move_calls += 1
        self.last_xyz_target = np.array(target_xyz, dtype=float)

    def update(self, _arm_state):
        return True

    def is_executing(self):
        return False


class _GraspStub:
    pass


def _make_executor(controller, translator, auth_manager):
    return PrimitiveExecutor(
        controller=controller,
        grasp=_GraspStub(),
        action_translator=translator,
        authorization_manager=auth_manager,
    )


def _issue_valid_token(auth: AuthorizationManager):
    return auth.issue(
        source="test",
        quality=1.0,
        scope=AuthScope.TASK_SESSION,
        autonomy_level="A2_TASK_CONFIRM",
        max_objects=0,
    )


class TestAuthorizationGate:
    def test_authorized_execution_proceeds(self):
        auth = AuthorizationManager()
        _issue_valid_token(auth)
        controller = _ControllerSpy(converges=True)
        executor = _make_executor(controller, FakeActionTranslator(), auth)
        primitive = Primitive(type=PrimitiveType.OPENVLA_TRAJECTORY, metadata=make_openvla_metadata())
        executor.start_plan([primitive])

        s1 = executor.tick(_world())
        s2 = executor.tick(_world())
        s3 = executor.tick(_world())

        assert s1 == ExecutorStatus.RUNNING
        assert s2 == ExecutorStatus.RUNNING
        assert s3 == ExecutorStatus.COMPLETE
        assert controller.joint_calls == 1

    def test_unauthorized_execution_blocked(self):
        auth = AuthorizationManager()  # no token issued
        controller = _ControllerSpy(converges=True)
        translator = FakeActionTranslator()
        executor = _make_executor(controller, translator, auth)
        primitive = Primitive(type=PrimitiveType.OPENVLA_TRAJECTORY, metadata=make_openvla_metadata())
        executor.start_plan([primitive])

        status = executor.tick(_world())

        assert status == ExecutorStatus.FAILED
        assert controller.joint_calls == 0
        assert translator.call_count == 0

    def test_expired_token_blocked(self):
        auth = AuthorizationManager()
        _issue_valid_token(auth)
        auth.complete()  # token no longer ACTIVE

        controller = _ControllerSpy(converges=True)
        executor = _make_executor(controller, FakeActionTranslator(), auth)
        primitive = Primitive(type=PrimitiveType.OPENVLA_TRAJECTORY, metadata=make_openvla_metadata())
        executor.start_plan([primitive])

        status = executor.tick(_world())
        assert status == ExecutorStatus.FAILED
        assert controller.joint_calls == 0

    def test_revoked_token_blocked(self):
        auth = AuthorizationManager()
        _issue_valid_token(auth)
        auth.invalidate("unit-test-revoked")

        controller = _ControllerSpy(converges=True)
        executor = _make_executor(controller, FakeActionTranslator(), auth)
        primitive = Primitive(type=PrimitiveType.OPENVLA_TRAJECTORY, metadata=make_openvla_metadata())
        executor.start_plan([primitive])

        status = executor.tick(_world())
        assert status == ExecutorStatus.FAILED
        assert controller.joint_calls == 0

    def test_token_id_logged_in_output(self, capsys):
        auth = AuthorizationManager()
        token = _issue_valid_token(auth)
        controller = _ControllerSpy(converges=True)
        executor = _make_executor(controller, FakeActionTranslator(), auth)
        primitive = Primitive(type=PrimitiveType.OPENVLA_TRAJECTORY, metadata=make_openvla_metadata())
        executor.start_plan([primitive])
        executor.tick(_world())
        out = capsys.readouterr().out

        assert token.token_id in out
        assert "Executing trajectory" in out


class TestOpenVLAExecution:
    def test_metadata_extraction(self):
        meta = make_openvla_metadata()
        translator = FakeActionTranslator()
        result = translator.translate_from_metadata(meta)
        assert result.ik_success
        assert result.gripper_command == 0.0

    def test_invalid_metadata_fails_gracefully(self):
        translator = FakeActionTranslator()
        bad_meta = {"proposer": "openvla"}
        try:
            _ = translator.translate_from_metadata(bad_meta)
            assert False, "Expected KeyError/TypeError for incomplete metadata"
        except (KeyError, TypeError):
            assert True

    def test_ik_failure_does_not_execute(self):
        class FailingTranslator:
            def translate_from_metadata(self, _meta):
                return TranslatedAction(
                    joint_positions=np.zeros(7),
                    gripper_command=0.0,
                    target_ee_position=np.zeros(3),
                    target_ee_rotation=np.eye(3),
                    ik_success=False,
                    ik_error=0.5,
                    clamped=False,
                )

        auth = AuthorizationManager()
        _issue_valid_token(auth)
        controller = _ControllerSpy(converges=True)
        executor = _make_executor(controller, FailingTranslator(), auth)
        primitive = Primitive(type=PrimitiveType.OPENVLA_TRAJECTORY, metadata=make_openvla_metadata())
        executor.start_plan([primitive])
        status = executor.tick(_world())

        assert status == ExecutorStatus.FAILED
        assert controller.joint_calls == 0

    def test_controller_receives_correct_joints(self):
        auth = AuthorizationManager()
        _issue_valid_token(auth)
        controller = _ControllerSpy(converges=True)
        translator = FakeActionTranslator()
        executor = _make_executor(controller, translator, auth)
        primitive = Primitive(type=PrimitiveType.OPENVLA_TRAJECTORY, metadata=make_openvla_metadata())
        executor.start_plan([primitive])

        executor.tick(_world())
        executor.tick(_world())

        assert controller.last_joint_target is not None
        assert controller.last_joint_target.shape == (7,)
        assert not np.any(np.isnan(controller.last_joint_target))


class TestTrustIntegration:
    def _trust_config(self):
        return {
            "trust": {
                "init_task_trust": 1.0,
                "recovery_per_success": 0.03,
                "max_recovery_trust": 0.90,
                "reauth": {
                    "enable": True,
                    "task_trust_below": 0.55,
                    "consecutive_failures": 2,
                },
            }
        }

    def test_successful_execution_increases_trust(self):
        engine = TrustEngine(self._trust_config())
        engine.start_session(auth_quality=1.0)
        engine.record_primitive_result("grasp_fail", object_index=0)  # drop trust first
        before = engine.task_trust
        engine.record_object_complete(success=True, object_index=0)
        assert engine.task_trust > before

    def test_failed_execution_decreases_trust(self):
        engine = TrustEngine(self._trust_config())
        engine.start_session(auth_quality=1.0)
        before = engine.task_trust
        engine.record_primitive_result("ik_fail", object_index=0)
        assert engine.task_trust < before

    def test_trust_drop_triggers_reauth(self):
        engine = TrustEngine(self._trust_config())
        engine.start_session(auth_quality=1.0)
        engine.record_object_complete(success=False, object_index=0)
        engine.record_object_complete(success=False, object_index=0)
        reason = engine.should_reauth()
        assert reason is not None


class TestExecutionEvents:
    def test_success_output_logged(self, capsys):
        auth = AuthorizationManager()
        _issue_valid_token(auth)
        controller = _ControllerSpy(converges=True)
        executor = _make_executor(controller, FakeActionTranslator(), auth)
        primitive = Primitive(type=PrimitiveType.OPENVLA_TRAJECTORY, metadata=make_openvla_metadata())
        executor.start_plan([primitive])
        executor.tick(_world())
        out = capsys.readouterr().out
        assert "[OPENVLA] Executing trajectory" in out

    def test_ik_failure_output_logged(self, capsys):
        class FailingTranslator:
            def translate_from_metadata(self, _meta):
                return TranslatedAction(
                    joint_positions=np.zeros(7),
                    gripper_command=0.0,
                    target_ee_position=np.zeros(3),
                    target_ee_rotation=np.eye(3),
                    ik_success=False,
                    ik_error=0.5,
                    clamped=False,
                )

        auth = AuthorizationManager()
        _issue_valid_token(auth)
        executor = _make_executor(_ControllerSpy(), FailingTranslator(), auth)
        primitive = Primitive(type=PrimitiveType.OPENVLA_TRAJECTORY, metadata=make_openvla_metadata())
        executor.start_plan([primitive])
        executor.tick(_world())
        out = capsys.readouterr().out
        assert "IK failed" in out

    def test_timeout_output_logged(self, capsys):
        auth = AuthorizationManager()
        _issue_valid_token(auth)
        controller = _ControllerSpy(converges=False)
        executor = _make_executor(controller, FakeActionTranslator(), auth)
        primitive = Primitive(type=PrimitiveType.OPENVLA_TRAJECTORY, metadata=make_openvla_metadata())
        executor.start_plan([primitive])
        executor.tick(_world())
        _ = capsys.readouterr()
        executor.tick(_world())
        out = capsys.readouterr().out
        assert "Joint convergence timeout" in out

    def test_error_output_logged(self, capsys):
        class RaisingTranslator:
            def translate_from_metadata(self, _meta):
                raise RuntimeError("translation exploded")

        auth = AuthorizationManager()
        _issue_valid_token(auth)
        executor = _make_executor(_ControllerSpy(), RaisingTranslator(), auth)
        primitive = Primitive(type=PrimitiveType.OPENVLA_TRAJECTORY, metadata=make_openvla_metadata())
        executor.start_plan([primitive])
        executor.tick(_world())
        out = capsys.readouterr().out
        assert "Translation error" in out

    def test_all_output_paths_include_token_id(self, capsys):
        auth = AuthorizationManager()
        token = _issue_valid_token(auth)
        executor = _make_executor(_ControllerSpy(converges=False), FakeActionTranslator(), auth)
        primitive = Primitive(type=PrimitiveType.OPENVLA_TRAJECTORY, metadata=make_openvla_metadata())
        executor.start_plan([primitive])
        executor.tick(_world())
        _ = capsys.readouterr()
        executor.tick(_world())
        out = capsys.readouterr().out
        assert token.token_id in out
