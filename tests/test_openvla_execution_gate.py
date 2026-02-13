"""Authorization gate tests for OPENVLA_TRAJECTORY execution path."""

from __future__ import annotations

import numpy as np

from src.execution.primitive_executor import PrimitiveExecutor, ExecutorStatus
from src.interfaces.primitive import Primitive, PrimitiveType
from src.robot.world_state import WorldState
from src.robot.simulator import ArmState


class _ControllerStub:
    def __init__(self):
        self.joint_calls = 0
        self.last_target = None

    def move_to_joint_positions(self, target):
        self.joint_calls += 1
        self.last_target = np.array(target, dtype=float)
        return True


class _GraspStub:
    pass


class _AuthStub:
    def __init__(self, authorized: bool):
        self._authorized = authorized

    def is_authorized(self):
        return self._authorized

    def get_active_token_id(self):
        return "auth_test" if self._authorized else None


class _TranslatorStub:
    def __init__(self):
        self.calls = 0

    def translate_from_metadata(self, metadata):
        self.calls += 1
        from src.external.openvla.action_translator import TranslatedAction

        return TranslatedAction(
            joint_positions=np.zeros(7),
            gripper_command=0.0,
            target_ee_position=np.array([0.4, 0.0, 0.6]),
            target_ee_rotation=np.eye(3),
            ik_success=True,
            ik_error=0.001,
            clamped=False,
        )


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


def test_openvla_trajectory_blocked_without_auth_token():
    controller = _ControllerStub()
    translator = _TranslatorStub()
    executor = PrimitiveExecutor(
        controller=controller,
        grasp=_GraspStub(),
        action_translator=translator,
        authorization_manager=_AuthStub(authorized=False),
    )
    primitive = Primitive(
        type=PrimitiveType.OPENVLA_TRAJECTORY,
        metadata={
            "delta_position": [0.01, 0.0, 0.0],
            "delta_rotation": [0.0, 0.0, 0.0],
            "gripper": 0.0,
            "proposer": "openvla",
        },
    )
    executor.start_plan([primitive])

    status = executor.tick(_world())

    assert status == ExecutorStatus.FAILED
    assert translator.calls == 0
    assert controller.joint_calls == 0


def test_openvla_trajectory_executes_with_valid_auth_token():
    controller = _ControllerStub()
    translator = _TranslatorStub()
    executor = PrimitiveExecutor(
        controller=controller,
        grasp=_GraspStub(),
        action_translator=translator,
        authorization_manager=_AuthStub(authorized=True),
    )
    primitive = Primitive(
        type=PrimitiveType.OPENVLA_TRAJECTORY,
        metadata={
            "delta_position": [0.01, 0.0, 0.0],
            "delta_rotation": [0.0, 0.0, 0.0],
            "gripper": 0.0,
            "proposer": "openvla",
        },
    )
    executor.start_plan([primitive])

    status_1 = executor.tick(_world())  # start + dispatch
    status_2 = executor.tick(_world())  # completion

    assert status_1 == ExecutorStatus.RUNNING
    assert status_2 == ExecutorStatus.RUNNING
    assert translator.calls == 1
    assert controller.joint_calls == 1

    status_3 = executor.tick(_world())
    assert status_3 == ExecutorStatus.COMPLETE
