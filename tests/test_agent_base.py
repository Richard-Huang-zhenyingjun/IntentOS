"""Tests for AgentBase contract and ArmAgent adapter."""
import pytest
from unittest.mock import MagicMock

from src.agents import ArmAgent, AgentAction, AgentRegistry, AgentStatus
from src.agents.agent_base import AgentBase


@pytest.fixture
def mock_executor():
    ex = MagicMock()
    ex.execute_reach = MagicMock(return_value=True)
    ex.execute_grasp = MagicMock(return_value=True)
    return ex


@pytest.fixture
def mock_bridge():
    b = MagicMock()
    b.is_connected = MagicMock(return_value=True)
    return b


@pytest.fixture
def arm_agent(mock_executor, mock_bridge):
    return ArmAgent(mock_executor, mock_bridge)


def make_action(action_type="reach", node_id="node_1"):
    return AgentAction(
        node_id=node_id,
        action_type=action_type,
        parameters={"target": "red_block"},
        agent_id="arm",
    )


class TestAgentContract:
    def test_agent_base_is_abstract(self):
        with pytest.raises(TypeError):
            AgentBase()

    def test_arm_agent_implements_agent_base(self):
        assert issubclass(ArmAgent, AgentBase)

    def test_agent_id_is_arm(self, arm_agent):
        assert arm_agent.agent_id == "arm"

    def test_can_execute_returns_tuple(self, arm_agent):
        result = arm_agent.can_execute(make_action())
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_can_execute_unsupported_action(self, arm_agent):
        ok, reason = arm_agent.can_execute(make_action("fly"))
        assert not ok
        assert reason is not None

    def test_cannot_execute_when_bridge_disconnected(self, arm_agent, mock_bridge):
        mock_bridge.is_connected.return_value = False
        ok, reason = arm_agent.can_execute(make_action())
        assert not ok
        assert reason is not None

    def test_execute_returns_action_result(self, arm_agent):
        result = arm_agent.execute(make_action(), token=MagicMock())
        assert result.node_id == "node_1"
        assert isinstance(result.success, bool)
        assert result.duration_ms >= 0.0

    def test_execute_passes_token_to_executor(self, arm_agent, mock_executor):
        token = MagicMock()
        result = arm_agent.execute(make_action(), token=token)

        assert result.success
        mock_executor.execute_reach.assert_called_once_with(token=token, target="red_block")

    def test_emergency_stop_never_raises(self, arm_agent, mock_bridge):
        mock_bridge.emergency_stop.side_effect = Exception("serial error")
        arm_agent.emergency_stop()

    def test_emergency_stop_sets_paused_status(self, arm_agent, mock_bridge):
        mock_bridge.emergency_stop.side_effect = None
        arm_agent.emergency_stop()
        state = arm_agent.get_state()
        assert state.status == AgentStatus.PAUSED

    def test_get_state_is_nonblocking(self, arm_agent):
        state = arm_agent.get_state()
        assert state.agent_id == "arm"


class TestAgentRegistry:
    def test_register_and_get(self, arm_agent):
        registry = AgentRegistry()
        registry.register(arm_agent)
        assert registry.get("arm") is arm_agent

    def test_duplicate_registration_raises(self, arm_agent, mock_executor, mock_bridge):
        registry = AgentRegistry()
        registry.register(arm_agent)
        arm2 = ArmAgent(mock_executor, mock_bridge)
        with pytest.raises(ValueError):
            registry.register(arm2)

    def test_contains_check(self, arm_agent):
        registry = AgentRegistry()
        registry.register(arm_agent)
        assert "arm" in registry
        assert "drone" not in registry
