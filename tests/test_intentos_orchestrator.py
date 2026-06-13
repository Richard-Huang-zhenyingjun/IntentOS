"""Tests for IntentOSOrchestrator."""
import tempfile
import time

from src.agents import ActionResult, AgentRegistry
from src.intentos import IntentOSConfig, IntentOSOrchestrator
from src.intentos.orchestrator import IntentOSState
from src.intentos.recovery import MAX_RETRIES_PER_NODE
from src.kernel import KernelCapabilities, KernelEvent, KernelState, ProposalReceipt
from src.planning import PlanningResult
from src.task_graph import (
    ConfirmationPolicy,
    TaskGraph,
    TaskNode,
    TaskStatus,
    UncertaintySignals,
)


class FakeKernel:
    def __init__(self):
        self.submitted = []
        self.events = []
        self.step_count = 0
        self.false_executions = 0
        self.accept = True

    def step(self):
        self.step_count += 1

    def poll_events(self):
        events = list(self.events)
        self.events.clear()
        return events

    def assert_invariant(self):
        if self.false_executions != 0:
            raise RuntimeError("SAFETY VIOLATION")

    def get_state(self):
        return KernelState.IDLE

    def get_capabilities(self):
        return KernelCapabilities(
            can_accept_proposal=True,
            active_agent_ids=frozenset({"arm"}),
            false_executions=self.false_executions,
        )

    def submit_proposal(self, proposal):
        self.submitted.append(proposal)
        return ProposalReceipt(
            proposal_id=proposal.proposal_id,
            accepted=self.accept,
            rejection_reason=None if self.accept else "busy",
        )

    def push_event(self, kind):
        self.events.append(
            KernelEvent(
                kind=kind,
                proposal_id=None,
                agent_id=None,
                timestamp_ms=0.0,
                details={},
            )
        )


class FakePlanner:
    def __init__(self, graph):
        self.graph = graph
        self.calls = []

    def plan(self, goal, scene_summary):
        self.calls.append((goal, scene_summary))
        return PlanningResult(
            graph=self.graph,
            used_llm=False,
            used_fallback=True,
            repair_attempts=0,
            violations_found=[],
            planning_duration_ms=1.0,
            plan_source="heuristic",
        )


class FakeAgent:
    def __init__(self, success=True):
        self.agent_id = "arm"
        self.success = success
        self.actions = []
        self.tokens = []

    def execute(self, action, token):
        self.actions.append(action)
        self.tokens.append(token)
        return ActionResult(
            node_id=action.node_id,
            success=self.success,
            failure_reason=None if self.success else "simulated failure",
            world_state_delta={"action": action.action_type} if self.success else {},
            duration_ms=5.0,
        )


class ObjectMovedAgent(FakeAgent):
    def execute(self, action, token):
        self.actions.append(action)
        self.tokens.append(token)
        return ActionResult(
            node_id=action.node_id,
            success=False,
            failure_reason="object moved",
            world_state_delta={},
            duration_ms=5.0,
        )


def make_graph(nodes=None, goal="clean the table"):
    return TaskGraph(
        graph_id="g1",
        goal=goal,
        nodes=nodes
        or [
            TaskNode(
                node_id="n1",
                action_type="reach",
                agent_id="arm",
                parameters={},
                depends_on=[],
            )
        ],
        created_at=0.0,
    )


def make_orchestrator(graph=None, agent=None, kernel=None, tmp_path=None):
    kernel = kernel or FakeKernel()
    registry = AgentRegistry()
    agent = agent or FakeAgent()
    registry.register(agent)
    planner = FakePlanner(graph or make_graph())
    cfg = IntentOSConfig(log_execution_steps=False)
    tmpdir = None
    if tmp_path is not None:
        cfg.execution_history_path = str(tmp_path / "history.json")
    else:
        tmpdir = tempfile.TemporaryDirectory()
        cfg.execution_history_path = f"{tmpdir.name}/history.json"
    orch = IntentOSOrchestrator(
        kernel=kernel,
        agent_registry=registry,
        planner=planner,
        cfg=cfg,
    )
    orch._test_tmpdir = tmpdir
    return orch, kernel, planner, agent


def tick_until_not_planning(orch, max_ticks=50):
    for _ in range(max_ticks):
        orch.tick()
        if orch.state != IntentOSState.PLANNING:
            return
        time.sleep(0.01)
    raise AssertionError("IntentOS stayed in PLANNING")


def test_submit_goal_accepts_when_idle_and_plans_on_tick():
    orch, kernel, planner, _ = make_orchestrator()

    assert orch.submit_goal("clean the table", "one block")
    assert orch.state == IntentOSState.PLANNING

    tick_until_not_planning(orch)

    assert planner.calls == [("clean the table", "one block")]
    assert orch.state == IntentOSState.AWAITING_CONFIRM
    assert len(kernel.submitted) == 1
    assert kernel.submitted[0].summary


def test_submit_goal_rejected_while_busy():
    orch, _, _, _ = make_orchestrator()

    assert orch.submit_goal("clean the table", "scene")
    assert not orch.submit_goal("go home", "scene")


def test_confirmed_event_starts_execution_and_completes_graph():
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
    orch, kernel, _, agent = make_orchestrator(graph=graph)
    orch.submit_goal("clean the table", "scene")
    tick_until_not_planning(orch)

    kernel.push_event("confirmed")
    tick_until_not_planning(orch)
    tick_until_not_planning(orch)
    tick_until_not_planning(orch)

    assert [a.node_id for a in agent.actions] == ["n1", "n2"]
    assert all(node.status == TaskStatus.DONE for node in graph.nodes)
    assert orch.state == IntentOSState.COMPLETE


def test_cancel_event_aborts_and_clears_context():
    orch, kernel, _, _ = make_orchestrator()
    orch.submit_goal("clean the table", "scene")
    tick_until_not_planning(orch)

    kernel.push_event("cancelled")
    tick_until_not_planning(orch)

    assert orch.state == IntentOSState.ABORTED
    assert orch.get_status()["intentos_state"] == "ABORTED"


def test_kernel_rejecting_proposal_sets_error():
    kernel = FakeKernel()
    kernel.accept = False
    orch, _, _, _ = make_orchestrator(kernel=kernel)

    orch.submit_goal("clean the table", "scene")
    tick_until_not_planning(orch)

    assert orch.state == IntentOSState.ERROR


def test_abort_uncertainty_never_reaches_kernel():
    graph = make_graph(
        [
            TaskNode(
                node_id="risky",
                action_type="reach",
                agent_id="arm",
                uncertainty=UncertaintySignals(
                    perception_confidence=0.0,
                    execution_history_rate=0.0,
                    simulation_risk=1.0,
                ),
            )
        ]
    )
    orch, kernel, _, _ = make_orchestrator(graph=graph)

    orch.submit_goal("touch unknown object", "uncertain scene")
    tick_until_not_planning(orch)

    assert orch.state == IntentOSState.ABORTED
    assert kernel.submitted == []


def test_failed_node_invalidates_downstream_and_enters_error():
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
    orch, kernel, _, agent = make_orchestrator(graph=graph, agent=FakeAgent(success=False))
    orch.submit_goal("clean the table", "scene")
    tick_until_not_planning(orch)

    kernel.push_event("confirmed")
    for _ in range(MAX_RETRIES_PER_NODE):
        tick_until_not_planning(orch)

    assert agent.actions[0].node_id == "n1"
    assert len(agent.actions) == MAX_RETRIES_PER_NODE
    assert graph.nodes[0].status == TaskStatus.FAILED
    assert graph.nodes[1].status == TaskStatus.INVALIDATED
    assert orch.state == IntentOSState.ERROR


def test_missing_agent_marks_node_failed():
    graph = make_graph(
        [
            TaskNode(
                node_id="n1",
                action_type="reach",
                agent_id="missing",
                confirmation_policy=ConfirmationPolicy.CHECKPOINT,
            )
        ]
    )
    kernel = FakeKernel()
    registry = AgentRegistry()
    planner = FakePlanner(graph)
    orch = IntentOSOrchestrator(
        kernel=kernel,
        agent_registry=registry,
        planner=planner,
        cfg=IntentOSConfig(log_execution_steps=False),
    )

    orch.submit_goal("clean the table", "scene")
    tick_until_not_planning(orch)
    kernel.push_event("confirmed")
    tick_until_not_planning(orch)
    tick_until_not_planning(orch)

    assert graph.nodes[0].status == TaskStatus.FAILED
    assert orch.state == IntentOSState.ERROR


def test_tick_asserts_kernel_invariant():
    kernel = FakeKernel()
    kernel.false_executions = 1
    orch, _, _, _ = make_orchestrator(kernel=kernel)

    try:
        orch.tick()
    except RuntimeError as exc:
        assert "SAFETY VIOLATION" in str(exc)
    else:
        raise AssertionError("tick should raise on false executions")


def test_status_reports_context_fields():
    orch, _, _, _ = make_orchestrator()
    orch.submit_goal("clean the table", "scene")
    tick_until_not_planning(orch)

    status = orch.get_status()

    assert status["goal"] == "clean the table"
    assert status["nodes_total"] == 1
    assert status["plan_source"] == "heuristic"


def test_confirmed_event_issues_scoped_token_for_current_segment(tmp_path):
    orch, kernel, _, agent = make_orchestrator(tmp_path=tmp_path)
    orch.submit_goal("clean the table", "scene")
    tick_until_not_planning(orch)

    kernel.push_event("confirmed")
    tick_until_not_planning(orch)

    assert agent.tokens
    assert agent.tokens[0].covers("n1")
    assert orch.state == IntentOSState.COMPLETE


def test_successful_node_records_execution_history(tmp_path):
    graph = make_graph([TaskNode(node_id="n1", action_type="reach", agent_id="arm")])
    orch, kernel, _, _ = make_orchestrator(graph=graph, tmp_path=tmp_path)
    orch.submit_goal("clean the table", "scene")
    tick_until_not_planning(orch)
    kernel.push_event("confirmed")
    tick_until_not_planning(orch)

    assert orch._exec_history.success_rate("arm", "reach") == 1.0


def test_node_without_valid_token_halts_and_does_not_execute(tmp_path):
    graph = make_graph([TaskNode(node_id="n1", action_type="reach", agent_id="arm")])
    orch, kernel, _, agent = make_orchestrator(graph=graph, tmp_path=tmp_path)
    orch.submit_goal("clean the table", "scene")
    tick_until_not_planning(orch)

    orch._execute_node(graph.nodes[0])

    assert graph.nodes[0].status == TaskStatus.FAILED
    assert graph.nodes[0].error == "No valid scoped token"
    assert agent.actions == []
    assert kernel.false_executions == 0


def test_transient_failure_retries_before_escalation(tmp_path):
    graph = make_graph([TaskNode(node_id="n1", action_type="reach", agent_id="arm")])
    orch, kernel, _, agent = make_orchestrator(
        graph=graph,
        agent=FakeAgent(success=False),
        tmp_path=tmp_path,
    )
    orch.submit_goal("clean the table", "scene")
    tick_until_not_planning(orch)
    kernel.push_event("confirmed")

    for expected_attempt in range(1, MAX_RETRIES_PER_NODE):
        tick_until_not_planning(orch)
        assert graph.nodes[0].status == TaskStatus.PENDING
        assert len(agent.actions) == expected_attempt

    tick_until_not_planning(orch)
    assert len(agent.actions) == MAX_RETRIES_PER_NODE
    assert graph.nodes[0].status == TaskStatus.FAILED
    assert orch.state == IntentOSState.ERROR


def test_recoverable_failure_exhaustion_skips_node_and_completes(tmp_path):
    graph = make_graph(
        [
            TaskNode(
                node_id="n1",
                action_type="reach",
                agent_id="arm",
                parameters={"target": "red_block"},
            )
        ]
    )
    orch, kernel, planner, agent = make_orchestrator(
        graph=graph,
        agent=ObjectMovedAgent(),
        tmp_path=tmp_path,
    )
    orch._attention._cooldown_s = 0.0
    orch.submit_goal("clean the table", "scene")
    tick_until_not_planning(orch)
    kernel.push_event("confirmed")

    for _ in range(MAX_RETRIES_PER_NODE):
        tick_until_not_planning(orch)

    assert graph.nodes[0].status == TaskStatus.SKIPPED
    assert len(agent.actions) == MAX_RETRIES_PER_NODE
    assert planner.calls == [("clean the table", "scene")]
    assert len(kernel.submitted) == 1
    tick_until_not_planning(orch)
    assert orch.state == IntentOSState.COMPLETE
