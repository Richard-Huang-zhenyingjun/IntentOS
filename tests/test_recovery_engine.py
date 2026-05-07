"""Tests for RecoveryEngine."""
from src.intentos import FailureClass, RecoveryEngine
from src.intentos.recovery import (
    MAX_RECOVERY_ATTEMPTS_PER_PLAN,
    MAX_RETRIES_PER_NODE,
)
from src.task_graph import TaskGraph, TaskNode


def make_node(node_id="n1", action_type="reach", target="red_block"):
    return TaskNode(
        node_id=node_id,
        action_type=action_type,
        agent_id="arm",
        parameters={"target": target},
    )


def make_graph(node=None):
    return TaskGraph(
        graph_id="g1",
        goal="test",
        nodes=[node or make_node()],
        created_at=0.0,
    )


def test_safety_keywords_escalate_immediately():
    engine = RecoveryEngine()
    node = make_node()

    for reason in (
        "collision detected",
        "safety guard tripped",
        "emergency stop requested",
        "hardware controller fault",
    ):
        decision = engine.classify(node, make_graph(node), reason)
        assert decision.failure_class == FailureClass.ESCALATION
        assert decision.escalation_reason == reason
        assert decision.retry_count == 0


def test_retry_count_below_max_returns_transient_and_increments():
    engine = RecoveryEngine()
    node = make_node(action_type="grasp")
    graph = make_graph(node)

    first = engine.classify(node, graph, "ik timeout")
    second = engine.classify(node, graph, "ik timeout")

    assert first.failure_class == FailureClass.TRANSIENT
    assert first.retry_count == 1
    assert second.failure_class == FailureClass.TRANSIENT
    assert second.retry_count == MAX_RETRIES_PER_NODE
    assert engine._retry_counts[node.node_id] == MAX_RETRIES_PER_NODE


def test_object_failure_after_max_retries_returns_replanning():
    engine = RecoveryEngine()
    node = make_node(action_type="grasp", target="red_block")
    graph = make_graph(node)

    for _ in range(MAX_RETRIES_PER_NODE):
        engine.classify(node, graph, "temporary slip")
    decision = engine.classify(node, graph, "object moved")

    assert decision.failure_class == FailureClass.REPLANNING
    assert decision.retry_count == MAX_RETRIES_PER_NODE
    assert decision.replan_goal == "retry grasp for red_block"
    assert engine._recovery_attempts == 1


def test_default_after_max_retries_escalates():
    engine = RecoveryEngine()
    node = make_node()
    graph = make_graph(node)

    for _ in range(MAX_RETRIES_PER_NODE):
        engine.classify(node, graph, "temporary timeout")
    decision = engine.classify(node, graph, "still failing")

    assert decision.failure_class == FailureClass.ESCALATION
    assert decision.escalation_reason == "still failing"
    assert engine._recovery_attempts == 1


def test_recovery_attempt_limit_escalates_before_retry():
    engine = RecoveryEngine()
    engine._recovery_attempts = MAX_RECOVERY_ATTEMPTS_PER_PLAN
    node = make_node()

    decision = engine.classify(node, make_graph(node), "temporary timeout")

    assert decision.failure_class == FailureClass.ESCALATION
    assert "Exceeded" in decision.escalation_reason
    assert node.node_id not in engine._retry_counts


def test_reset_node_clears_retry_count():
    engine = RecoveryEngine()
    node = make_node()
    graph = make_graph(node)
    engine.classify(node, graph, "temporary timeout")

    engine.reset_node(node.node_id)

    assert node.node_id not in engine._retry_counts


def test_reset_plan_clears_all_state():
    engine = RecoveryEngine()
    node = make_node()
    graph = make_graph(node)
    engine.classify(node, graph, "temporary timeout")
    engine._recovery_attempts = 2

    engine.reset_plan()

    assert engine._retry_counts == {}
    assert engine._recovery_attempts == 0


def test_none_failure_reason_treated_as_transient_first():
    engine = RecoveryEngine()
    node = make_node()

    decision = engine.classify(node, make_graph(node), None)

    assert decision.failure_class == FailureClass.TRANSIENT
    assert decision.retry_count == 1
