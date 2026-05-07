"""Tests for TaskGraph structural validator."""
from src.task_graph import TaskGraph, TaskNode, validate


def make_graph(nodes):
    return TaskGraph(graph_id="g1", goal="test goal", nodes=nodes, created_at=0.0)


def test_valid_graph_returns_empty_violation_list():
    graph = make_graph(
        [
            TaskNode(node_id="n1", action_type="reach", agent_id="arm"),
            TaskNode(
                node_id="n2",
                action_type="grasp",
                agent_id="arm",
                depends_on=["n1"],
            ),
        ]
    )

    assert validate(graph, registered_agent_ids={"arm"}) == []


def test_empty_graph_violation():
    graph = make_graph([])

    violations = validate(graph, registered_agent_ids={"arm"})

    assert [v.rule for v in violations] == ["no_empty_graph"]


def test_duplicate_node_id_violation():
    graph = make_graph(
        [
            TaskNode(node_id="n1", action_type="reach", agent_id="arm"),
            TaskNode(node_id="n1", action_type="grasp", agent_id="arm"),
        ]
    )

    violations = validate(graph, registered_agent_ids={"arm"})

    assert any(v.rule == "unique_node_ids" and v.node_id == "n1" for v in violations)


def test_missing_dependency_violation():
    graph = make_graph(
        [
            TaskNode(
                node_id="n1",
                action_type="reach",
                agent_id="arm",
                depends_on=["ghost"],
            )
        ]
    )

    violations = validate(graph, registered_agent_ids={"arm"})

    assert any(v.rule == "deps_exist" and v.node_id == "n1" for v in violations)


def test_unknown_agent_violation():
    graph = make_graph(
        [TaskNode(node_id="n1", action_type="reach", agent_id="drone")]
    )

    violations = validate(graph, registered_agent_ids={"arm"})

    assert any(v.rule == "agents_registered" and v.node_id == "n1" for v in violations)


def test_cycle_violation():
    graph = make_graph(
        [
            TaskNode(
                node_id="a",
                action_type="reach",
                agent_id="arm",
                depends_on=["b"],
            ),
            TaskNode(
                node_id="b",
                action_type="grasp",
                agent_id="arm",
                depends_on=["a"],
            ),
        ]
    )

    violations = validate(graph, registered_agent_ids={"arm"})

    assert any(v.rule == "no_cycles" for v in violations)
