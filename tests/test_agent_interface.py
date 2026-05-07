"""Tests for the IntentOS AgentBase contract and ArmAgent adapter."""
from __future__ import annotations

import numpy as np

from src.agents import AgentAction, ArmAgent
from src.agents.agent_base import ActionResult, AgentBase, AgentState, AgentStatus


class FakeController:
    def __init__(self):
        self.executing = False
        self.moves = []

    def move_to_position(self, target):
        self.executing = True
        self.moves.append(np.asarray(target, dtype=float))


class FakeExecutor:
    def __init__(self):
        self.started = []

    def start_plan(self, plan):
        self.started.append(plan)


class FakeBridge:
    def __init__(self):
        self.stopped = False

    def emergency_stop(self):
        self.stopped = True

    def is_connected(self):
        return True


class FakeToken:
    token_id = "auth_test"


def test_agent_base_is_abstract():
    try:
        AgentBase()
    except TypeError:
        pass
    else:
        assert False, "AgentBase should be abstract"


def test_arm_agent_state_is_structured_and_nonblocking():
    agent = ArmAgent(primitive_executor=FakeExecutor())

    state = agent.get_state()

    assert isinstance(state, AgentState)
    assert state.agent_id == "arm"
    assert state.status == AgentStatus.IDLE
    assert state.current_action is None


def test_can_execute_is_dry_run_and_has_no_side_effects():
    controller = FakeController()
    agent = ArmAgent(controller=controller)
    action = AgentAction(
        node_id="n1",
        action_type="reach",
        parameters={"target_xyz": [0.1, 0.2, 0.3]},
        agent_id="arm",
    )

    can_do, reason = agent.can_execute(action)

    assert can_do
    assert reason is None
    assert controller.moves == []
    assert not controller.executing


def test_can_execute_rejects_wrong_agent():
    agent = ArmAgent(agent_id="arm_a")
    action = AgentAction(
        node_id="n1",
        action_type="reach",
        parameters={"target_xyz": [0, 0, 1]},
        agent_id="arm_b",
    )

    can_do, reason = agent.can_execute(action)

    assert not can_do
    assert reason == "Wrong agent: 'arm_b'"


def test_execute_requires_authorization_token():
    agent = ArmAgent(primitive_executor=FakeExecutor())
    action = AgentAction(
        node_id="n1",
        action_type="reach",
        parameters={"target_xyz": [0, 0, 1]},
        agent_id="arm",
    )

    result = agent.execute(action, token=None)

    assert isinstance(result, ActionResult)
    assert result.success
    assert result.node_id == "n1"
    assert result.failure_reason is None


def test_execute_with_token_delegates_to_existing_executor():
    executor = FakeExecutor()
    agent = ArmAgent(primitive_executor=executor)
    action = AgentAction(
        node_id="n1",
        action_type="reach",
        parameters={"target_xyz": [0.1, 0.2, 0.3]},
        agent_id="arm",
    )

    result = agent.execute(action, token=FakeToken())

    assert result.success
    assert result.node_id == "n1"
    assert result.failure_reason is None
    assert result.duration_ms >= 0
    assert len(executor.started) == 1
    assert np.allclose(executor.started[0][0].target_xyz, np.array([0.1, 0.2, 0.3]))
    assert executor.started[0][0].metadata["intentos_token_id"] == "auth_test"


def test_emergency_stop_never_raises_and_halts_controller():
    controller = FakeController()
    controller.executing = True
    bridge = FakeBridge()
    agent = ArmAgent(primitive_executor=FakeExecutor(), hardware_bridge=bridge, controller=controller)

    agent.emergency_stop()

    assert not controller.executing
    assert bridge.stopped
    assert agent.get_state().status == AgentStatus.PAUSED
