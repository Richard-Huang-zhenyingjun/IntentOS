"""Tests for CheckpointPlanner and ScopedExecutionToken."""
import time

from src.planning import (
    CHECKPOINT_THRESHOLD,
    MAX_SILENT_NODES,
    CheckpointPlanner,
    ScopedExecutionToken,
)
from src.task_graph import (
    ConfirmationPolicy,
    TaskGraph,
    TaskNode,
    UncertaintySignals,
)


def uncertainty(combined: float) -> UncertaintySignals:
    if combined <= 0.30:
        return UncertaintySignals(
            perception_confidence=1.0,
            execution_history_rate=1.0,
            simulation_risk=combined / 0.30,
        )
    remainder = combined - 0.30
    inv_each = remainder / 0.70
    return UncertaintySignals(
        perception_confidence=1.0 - inv_each,
        execution_history_rate=1.0 - inv_each,
        simulation_risk=1.0,
    )


def node(
    node_id,
    depends_on=None,
    policy=ConfirmationPolicy.NEVER,
    combined=0.1,
    action_type="reach",
):
    return TaskNode(
        node_id=node_id,
        action_type=action_type,
        agent_id="arm",
        parameters={},
        depends_on=depends_on or [],
        confirmation_policy=policy,
        uncertainty=uncertainty(combined),
    )


def graph(nodes):
    return TaskGraph(
        graph_id="g1",
        goal="test",
        nodes=nodes,
        created_at=0.0,
    )


def test_empty_graph_returns_no_segments():
    planner = CheckpointPlanner()

    assert planner.segment(graph([])) == []


def test_non_empty_graph_returns_at_least_one_segment():
    planner = CheckpointPlanner()

    segments = planner.segment(graph([node("n1")]))

    assert len(segments) == 1
    assert segments[0].node_ids == ["n1"]


def test_first_segment_always_requires_confirmation():
    planner = CheckpointPlanner()

    segments = planner.segment(graph([node("n1", policy=ConfirmationPolicy.NEVER)]))

    assert segments[0].requires_confirmation


def test_high_uncertainty_node_starts_new_segment():
    planner = CheckpointPlanner()
    g = graph(
        [
            node("n1", combined=0.1),
            node("n2", depends_on=["n1"], combined=CHECKPOINT_THRESHOLD + 0.01),
        ]
    )

    segments = planner.segment(g)

    assert [segment.node_ids for segment in segments] == [["n1"], ["n2"]]


def test_always_policy_node_starts_new_segment():
    planner = CheckpointPlanner()
    g = graph(
        [
            node("n1"),
            node("n2", depends_on=["n1"], policy=ConfirmationPolicy.ALWAYS),
        ]
    )

    segments = planner.segment(g)

    assert [segment.node_ids for segment in segments] == [["n1"], ["n2"]]
    assert segments[1].requires_confirmation


def test_max_silent_nodes_limit_enforced():
    planner = CheckpointPlanner()
    nodes = [
        node(f"n{i}", depends_on=[f"n{i - 1}"] if i else [])
        for i in range(MAX_SILENT_NODES + 1)
    ]

    segments = planner.segment(graph(nodes))

    assert len(segments) == 2
    assert len(segments[0].node_ids) == MAX_SILENT_NODES
    assert segments[1].node_ids == [f"n{MAX_SILENT_NODES}"]


def test_segments_follow_topological_order_not_input_order():
    planner = CheckpointPlanner()
    g = graph(
        [
            node("n2", depends_on=["n1"]),
            node("n1"),
        ]
    )

    segments = planner.segment(g)

    assert segments[0].node_ids == ["n1", "n2"]


def test_segment_summary_lists_unique_actions():
    planner = CheckpointPlanner()
    g = graph(
        [
            node("n1", action_type="reach"),
            node("n2", depends_on=["n1"], action_type="reach"),
            node("n3", depends_on=["n2"], action_type="grasp"),
        ]
    )

    segments = planner.segment(g)

    assert segments[0].summary == "3 step(s): reach -> grasp"


def test_scoped_token_covers_only_segment_nodes():
    planner = CheckpointPlanner()
    segment = planner.segment(graph([node("n1"), node("n2", depends_on=["n1"])]))[0]

    token = ScopedExecutionToken.issue(segment, [{"node_id": "n1"}, {"node_id": "n2"}])

    assert token.covers("n1")
    assert token.covers("n2")
    assert not token.covers("outside")


def test_scoped_token_valid_before_expiry_and_invalid_after():
    planner = CheckpointPlanner()
    segment = planner.segment(graph([node("n1")]))[0]

    token = ScopedExecutionToken.issue(segment, [{"node_id": "n1"}], validity_s=1.0)

    assert token.is_valid(current_time=token.issued_at + 0.5)
    assert not token.is_valid(current_time=token.expires_at + 0.001)


def test_scoped_token_hash_stable_for_same_definitions():
    planner = CheckpointPlanner()
    segment = planner.segment(graph([node("n1")]))[0]
    definitions = [{"action_type": "reach", "node_id": "n1"}]

    token_a = ScopedExecutionToken.issue(segment, definitions)
    time.sleep(0.001)
    token_b = ScopedExecutionToken.issue(segment, definitions)

    assert token_a.segment_hash == token_b.segment_hash
    assert token_a.token_id != token_b.token_id
