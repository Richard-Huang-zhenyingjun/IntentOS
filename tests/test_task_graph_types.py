"""Tests for IntentOS TaskGraph data types."""
import time

from src.task_graph import (
    ConfirmationPolicy,
    ResourceClaim,
    TaskGraph,
    TaskNode,
    TaskStatus,
    UncertaintySignals,
)


def test_uncertainty_unknown_is_conservative_midpoint():
    uncertainty = UncertaintySignals.unknown()

    assert uncertainty.perception_confidence == 0.5
    assert uncertainty.execution_history_rate == 0.5
    assert uncertainty.simulation_risk == 0.5
    assert 0.0 <= uncertainty.combined <= 1.0


def test_uncertainty_combined_weights_signals():
    low_risk = UncertaintySignals(
        perception_confidence=1.0,
        execution_history_rate=1.0,
        simulation_risk=0.0,
    )
    high_risk = UncertaintySignals(
        perception_confidence=0.0,
        execution_history_rate=0.0,
        simulation_risk=1.0,
    )

    assert low_risk.combined == 0.0
    assert high_risk.combined == 1.0


def test_task_node_defaults_to_pending_checkpoint_unknown_uncertainty():
    node = TaskNode(
        node_id="n1",
        action_type="reach",
        agent_id="arm",
    )

    assert node.status == TaskStatus.PENDING
    assert node.confirmation_policy == ConfirmationPolicy.CHECKPOINT
    assert isinstance(node.uncertainty, UncertaintySignals)
    assert not node.is_terminal


def test_task_node_terminal_statuses():
    node = TaskNode(node_id="n1", action_type="reach", agent_id="arm")

    for status in (
        TaskStatus.DONE,
        TaskStatus.FAILED,
        TaskStatus.INVALIDATED,
        TaskStatus.SKIPPED,
    ):
        node.status = status
        assert node.is_terminal


def test_resource_claim_fields_are_preserved():
    claim = ResourceClaim(
        agent_id="arm",
        node_id="n1",
        named_resources=frozenset({"workspace_zone_A", "object:red_block"}),
        spatial_zone="zone_A",
        estimated_duration_s=1.5,
    )

    assert claim.agent_id == "arm"
    assert "object:red_block" in claim.named_resources
    assert claim.spatial_zone == "zone_A"


def test_task_graph_ready_nodes_depend_on_done_dependencies():
    n1 = TaskNode(node_id="n1", action_type="reach", agent_id="arm")
    n2 = TaskNode(
        node_id="n2",
        action_type="grasp",
        agent_id="arm",
        depends_on=["n1"],
    )
    graph = TaskGraph(
        graph_id="g1",
        goal="pick red block",
        nodes=[n1, n2],
        created_at=time.time(),
    )

    assert graph.ready_nodes() == [n1]

    n1.status = TaskStatus.DONE
    assert graph.ready_nodes() == [n2]


def test_task_graph_completion_failure_and_summary():
    nodes = [
        TaskNode(node_id="n1", action_type="reach", agent_id="arm"),
        TaskNode(node_id="n2", action_type="grasp", agent_id="arm"),
    ]
    graph = TaskGraph(
        graph_id="g1",
        goal="pick red block",
        nodes=nodes,
        created_at=time.time(),
    )

    assert not graph.is_complete()
    assert not graph.has_failures()

    nodes[0].status = TaskStatus.DONE
    nodes[1].status = TaskStatus.FAILED

    assert graph.is_complete()
    assert graph.has_failures()
    assert "1/2 steps complete" in graph.summary()


def test_task_graph_get_node():
    node = TaskNode(node_id="n1", action_type="reach", agent_id="arm")
    graph = TaskGraph(
        graph_id="g1",
        goal="pick red block",
        nodes=[node],
        created_at=time.time(),
    )

    assert graph.get_node("n1") is node
    assert graph.get_node("missing") is None
