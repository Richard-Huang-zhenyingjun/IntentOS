import pytest

from src.intentos.orchestrator import IntentOSOrchestrator
from src.task_graph import TaskGraph, TaskNode, TaskStatus


def _graph_with_failed_node(node_id: str, error: str) -> TaskGraph:
    return TaskGraph(
        graph_id="terminal-boundary",
        goal="clean the table",
        created_at=0.0,
        nodes=[
            TaskNode(
                node_id=node_id,
                action_type=node_id.split("_", 1)[0],
                agent_id="arm",
                parameters={"object_id": 4},
                status=TaskStatus.FAILED,
                error=error,
            )
        ],
    )


@pytest.mark.parametrize(
    "error_code",
    [
        "grasp_failed",
        "grasp_no_object_id",
        "grasp_no_object_position",
        "ik_out_of_limits",
        "move_invalid_pose",
        "move_not_arrived",
        "timeout",
        "unreachable",
    ],
)
def test_terminal_object_mechanics_codes_normalize_to_skipped(error_code):
    graph = _graph_with_failed_node("grasp_0", error_code)

    IntentOSOrchestrator._normalize_terminal_recoverable_failures(graph)

    assert graph.nodes[0].status == TaskStatus.SKIPPED
    assert not IntentOSOrchestrator._graph_has_unresolved_failures(graph)


@pytest.mark.parametrize(
    "error_text",
    [
        "hardware controller fault",
        "unauthorized_execution_blocked",
        "agent missing",
        "not registered",
        "object missing",
    ],
)
def test_terminal_unrecognized_failures_stay_failed(error_text):
    graph = _graph_with_failed_node("grasp_0", error_text)

    IntentOSOrchestrator._normalize_terminal_recoverable_failures(graph)

    assert graph.nodes[0].status == TaskStatus.FAILED
    assert IntentOSOrchestrator._graph_has_unresolved_failures(graph)


def test_recoverable_code_on_non_object_chain_stays_failed():
    graph = _graph_with_failed_node("setup_0", "grasp_failed")

    IntentOSOrchestrator._normalize_terminal_recoverable_failures(graph)

    assert graph.nodes[0].status == TaskStatus.FAILED
    assert IntentOSOrchestrator._graph_has_unresolved_failures(graph)
