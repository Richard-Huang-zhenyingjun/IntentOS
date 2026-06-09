import numpy as np

from src.agents import ArmAgent
from src.agents.agent_base import AgentAction
from src.execution.primitive_executor import PrimitiveExecutor
from src.robot.simulator import ArmState


class _FakeSim:
    robot_id = 1
    client = 0

    @staticmethod
    def get_arm_state():
        return ArmState(
            joint_positions=np.zeros(7),
            ee_position=np.array([0.0, 0.0, 0.7]),
            ee_orientation=np.array([0.0, 0.0, 0.0, 1.0]),
        )

    @staticmethod
    def get_object_state():
        return None

    @staticmethod
    def step():
        return None


class _FakeController:
    def __init__(self):
        self.sim = _FakeSim()

    @staticmethod
    def move_to_position_smooth(*_args, **_kwargs):
        return None

    @staticmethod
    def is_executing():
        return False


class _FakeGrasp:
    @staticmethod
    def open():
        return None

    @staticmethod
    def close(force=None):
        return force

    @staticmethod
    def is_holding():
        return False

    @staticmethod
    def get_attached_id():
        return None


def test_forced_magnet_grasp_failure_preserves_reason_and_invariant():
    executor = PrimitiveExecutor(_FakeController(), _FakeGrasp())
    executor.force_grasp_failure(42)
    agent = ArmAgent(primitive_executor=executor)
    action = AgentAction(
        node_id="grasp_0",
        action_type="grasp",
        parameters={
            "object_id": 42,
            "target_xyz": [0.0, 0.0, 0.63],
        },
        agent_id="arm",
    )

    result = agent.execute(action, token=object())

    assert result.success is False
    assert result.failure_reason == "grasp_failed"
    assert executor.last_error_code == "grasp_failed"
    assert executor._invariant_checker.false_executions == 0
