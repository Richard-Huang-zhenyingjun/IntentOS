"""Tests for AgentRegistry."""
from src.agents import AgentRegistry, ArmAgent


def test_register_and_lookup_agent():
    registry = AgentRegistry()
    agent = ArmAgent(agent_id="arm")

    registry.register(agent)

    assert registry.get("arm") is agent
    assert "arm" in registry


def test_get_unknown_agent_returns_none():
    registry = AgentRegistry()
    assert registry.get("missing") is None


def test_duplicate_agent_id_rejected():
    registry = AgentRegistry()
    registry.register(ArmAgent(agent_id="arm"))

    try:
        registry.register(ArmAgent(agent_id="arm"))
    except ValueError as exc:
        assert "Agent 'arm' already registered" in str(exc)
    else:
        assert False, "Expected duplicate registration to fail"


def test_all_ids_and_agents_preserve_registration_order():
    registry = AgentRegistry()
    arm_a = ArmAgent(agent_id="arm_a")
    arm_b = ArmAgent(agent_id="arm_b")

    registry.register(arm_a)
    registry.register(arm_b)

    assert registry.all_ids() == ["arm_a", "arm_b"]
    assert registry.all_agents() == [arm_a, arm_b]
