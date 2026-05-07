"""Tests for ExecutionHistory."""
import json

from src.task_graph import TaskGraph, TaskNode, UncertaintySignals
from src.world_model import DEFAULT_RATE, ExecutionHistory


def history_path(tmp_path):
    return tmp_path / "execution_history.json"


def make_graph():
    return TaskGraph(
        graph_id="g1",
        goal="test",
        nodes=[
            TaskNode(
                node_id="n1",
                action_type="reach",
                agent_id="arm",
                uncertainty=UncertaintySignals(
                    perception_confidence=0.9,
                    execution_history_rate=0.9,
                    simulation_risk=0.2,
                ),
            ),
            TaskNode(
                node_id="n2",
                action_type="grasp",
                agent_id="arm",
                uncertainty=UncertaintySignals(
                    perception_confidence=0.8,
                    execution_history_rate=0.9,
                    simulation_risk=0.3,
                ),
            ),
        ],
        created_at=0.0,
    )


def test_missing_file_starts_empty_without_exception(tmp_path):
    path = history_path(tmp_path)

    history = ExecutionHistory(str(path))

    assert history.summary() == {}
    assert history.success_rate("arm", "reach") == DEFAULT_RATE


def test_record_persists_to_disk_immediately(tmp_path):
    path = history_path(tmp_path)
    history = ExecutionHistory(str(path))

    history.record("arm", "reach", True)

    assert path.exists()
    with open(path) as file:
        data = json.load(file)
    assert data == {"arm": {"reach": {"attempts": 1, "successes": 1}}}
    assert not path.with_suffix(".tmp.json").exists()


def test_success_rate_after_recording_outcomes(tmp_path):
    history = ExecutionHistory(str(history_path(tmp_path)))

    history.record("arm", "grasp", True)
    history.record("arm", "grasp", False)
    history.record("arm", "grasp", True)

    assert history.success_rate("arm", "grasp") == 2 / 3


def test_persisted_history_loads_on_new_instance(tmp_path):
    path = history_path(tmp_path)
    history = ExecutionHistory(str(path))
    history.record("arm", "move", True)
    history.record("arm", "move", False)

    reloaded = ExecutionHistory(str(path))

    assert reloaded.success_rate("arm", "move") == 0.5


def test_corrupt_file_recovers_to_empty_history(tmp_path):
    path = history_path(tmp_path)
    path.write_text("{not json")

    history = ExecutionHistory(str(path))

    assert history.summary() == {}
    assert history.success_rate("arm", "reach") == DEFAULT_RATE


def test_annotate_graph_updates_execution_history_rate(tmp_path):
    history = ExecutionHistory(str(history_path(tmp_path)))
    history.record("arm", "reach", True)
    history.record("arm", "reach", False)
    graph = make_graph()

    history.annotate_graph(graph)

    reach = graph.get_node("n1")
    grasp = graph.get_node("n2")
    assert reach.uncertainty.perception_confidence == 0.9
    assert reach.uncertainty.simulation_risk == 0.2
    assert reach.uncertainty.execution_history_rate == 0.5
    assert grasp.uncertainty.execution_history_rate == DEFAULT_RATE


def test_annotate_graph_does_not_increase_confidence(tmp_path):
    history = ExecutionHistory(str(history_path(tmp_path)))
    history.record("arm", "reach", True)
    node = TaskNode(
        node_id="n1",
        action_type="reach",
        agent_id="arm",
        uncertainty=UncertaintySignals(
            perception_confidence=0.9,
            execution_history_rate=0.2,
            simulation_risk=0.2,
        ),
    )
    graph = TaskGraph(graph_id="g1", goal="test", nodes=[node], created_at=0.0)

    history.annotate_graph(graph)

    assert node.uncertainty.execution_history_rate == 0.2


def test_summary_reports_rates_and_attempts(tmp_path):
    history = ExecutionHistory(str(history_path(tmp_path)))
    history.record("arm", "release", True)
    history.record("arm", "release", False)

    assert history.summary() == {
        "arm": {
            "release": {
                "rate": 0.5,
                "attempts": 2,
            }
        }
    }
