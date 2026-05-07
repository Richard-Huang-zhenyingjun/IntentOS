"""Tests for SimAgent. No hardware required."""
import pytest
from unittest.mock import MagicMock

from src.agents import SimAgent, SimAgentConfig, AgentAction, AgentStatus


@pytest.fixture
def fast_agent():
    cfg = SimAgentConfig(
        success_rates={
            "reach": 1.0,
            "grasp": 1.0,
            "move": 1.0,
            "release": 1.0,
            "home": 1.0,
        },
        simulate_delays=False,
        seed=0,
    )
    return SimAgent(agent_id="sim_agent", cfg=cfg)


@pytest.fixture
def failing_agent():
    cfg = SimAgentConfig(
        success_rates={
            "reach": 0.0,
            "grasp": 0.0,
            "move": 0.0,
            "release": 0.0,
            "home": 0.0,
        },
        simulate_delays=False,
        seed=0,
    )
    return SimAgent(agent_id="sim_agent", cfg=cfg)


def make_action(action_type="reach", node_id="n1"):
    return AgentAction(
        node_id=node_id,
        action_type=action_type,
        parameters={},
        agent_id="sim_agent",
    )


class TestSimAgentContract:
    def test_implements_agent_base(self, fast_agent):
        from src.agents import AgentBase

        assert isinstance(fast_agent, AgentBase)

    def test_agent_id_matches_constructor(self, fast_agent):
        assert fast_agent.agent_id == "sim_agent"

    def test_can_execute_supported_action(self, fast_agent):
        ok, reason = fast_agent.can_execute(make_action("reach"))
        assert ok
        assert reason is None

    def test_cannot_execute_unsupported_action(self, fast_agent):
        ok, reason = fast_agent.can_execute(make_action("fly"))
        assert not ok
        assert reason is not None

    def test_successful_execution_returns_success(self, fast_agent):
        result = fast_agent.execute(make_action(), token=MagicMock())
        assert result.success
        assert result.node_id == "n1"
        assert result.duration_ms >= 0.0

    def test_failing_execution_returns_failure(self, failing_agent):
        result = failing_agent.execute(make_action(), token=MagicMock())
        assert not result.success
        assert result.failure_reason is not None

    def test_state_is_idle_after_success(self, fast_agent):
        fast_agent.execute(make_action(), token=MagicMock())
        assert fast_agent.get_state().status == AgentStatus.IDLE

    def test_state_is_error_after_failure(self, failing_agent):
        failing_agent.execute(make_action(), token=MagicMock())
        assert failing_agent.get_state().status == AgentStatus.ERROR

    def test_emergency_stop_never_raises(self, fast_agent):
        fast_agent.emergency_stop()

    def test_emergency_stop_sets_paused(self, fast_agent):
        fast_agent.emergency_stop()
        assert fast_agent.get_state().status == AgentStatus.PAUSED

    def test_reset_error_restores_idle(self, failing_agent):
        failing_agent.execute(make_action(), token=MagicMock())
        assert failing_agent.get_state().status == AgentStatus.ERROR
        failing_agent.reset_error()
        assert failing_agent.get_state().status == AgentStatus.IDLE

    def test_world_state_delta_populated(self, fast_agent):
        result = fast_agent.execute(make_action(), token=MagicMock())
        assert "action" in result.world_state_delta
        assert "agent" in result.world_state_delta
