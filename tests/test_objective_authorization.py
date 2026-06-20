import tempfile
import time

from src.agents import ActionResult, AgentRegistry
from src.interfaces.scene_summary import ObjectInfo, SceneSummary
from src.intentos import IntentOSConfig, IntentOSOrchestrator
from src.intentos.orchestrator import (
    IntentOSState,
    ObjectiveAuthorization,
    ObjectiveAuthorizationStatus,
)
from src.kernel import KernelCapabilities, KernelEvent, KernelState, ProposalReceipt
from src.kernel.types import KernelSnapshot
from src.planning import CheckpointSegment, PlanningResult, ScopedExecutionToken
from src.planning.planner import HeuristicPlanner
from src.task_graph import TaskGraph, TaskNode, TaskStatus


class FakeKernel:
    def __init__(self):
        self.submitted = []
        self.events = []
        self.step_count = 0
        self.false_executions = 0
        self.active_token_id = None

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

    def get_snapshot(self):
        return KernelSnapshot(
            frame=self.step_count,
            state=self.get_state(),
            capabilities=self.get_capabilities(),
            active_token_id=self.active_token_id,
        )

    def submit_proposal(self, proposal):
        self.submitted.append(proposal)
        return ProposalReceipt(
            proposal_id=proposal.proposal_id,
            accepted=True,
            rejection_reason=None,
        )


class FakePlanner:
    def __init__(self, graph):
        self.graph = graph
        self.calls = []
        self._heuristic = HeuristicPlanner(AgentRegistry())

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
    def __init__(self):
        self.agent_id = "arm"
        self.actions = []
        self.tokens = []

    def execute(self, action, token):
        self.actions.append(action)
        self.tokens.append(token)
        return ActionResult(
            node_id=action.node_id,
            success=True,
            failure_reason=None,
            world_state_delta={"action": action.action_type},
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


def make_orchestrator(graph=None):
    kernel = FakeKernel()
    registry = AgentRegistry()
    agent = FakeAgent()
    registry.register(agent)
    planner = FakePlanner(graph or make_graph())
    cfg = IntentOSConfig(log_execution_steps=False)
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


def table_scene(object_id=4, pos=(0.2, 0.1, 0.63)):
    obj = ObjectInfo(object_id=object_id, pos_xyz=pos, on_table=True)
    return SceneSummary(
        table_id=1,
        table_position=(0.0, 0.0, 0.3),
        bin_zone_center=(0.4, 0.0, 0.75),
        bin_zone_radius=0.12,
        objects=(obj,),
        objects_on_table=(obj,),
        clutter_score=0.0,
        is_messy=True,
    )


def active_objective_auth(token_id="auth_abc"):
    return ObjectiveAuthorization(
        objective_type="table_clear",
        source_goal="clean the table",
        phase2_token_id=token_id,
        proposal_id="proposal_1",
    )


def test_objective_auth_is_created_on_real_confirmation():
    orch, kernel, _, _ = make_orchestrator()
    orch.submit_goal("clean the table", "scene")
    tick_until_not_planning(orch)

    kernel.events.append(
        KernelEvent(
            kind="confirmed",
            proposal_id=None,
            agent_id=None,
            timestamp_ms=0.0,
            details={"phase2_token_id": "auth_abc"},
        )
    )
    tick_until_not_planning(orch)

    auth = orch._objective_authorization
    assert auth is not None
    assert auth.objective_type == "table_clear"
    assert auth.source_goal == "clean the table"
    assert auth.phase2_token_id == "auth_abc"
    assert auth.proposal_id is not None
    assert auth.status == ObjectiveAuthorizationStatus.ACTIVE
    assert auth.reason is None


def test_continue_confirmed_objective_replans_tokens_and_executes_without_false_executions():
    orch, kernel, _, agent = make_orchestrator()
    kernel.active_token_id = "auth_abc"
    orch._objective_authorization = active_objective_auth("auth_abc")

    result = orch.continue_confirmed_objective(table_scene(), set())

    assert result.accepted
    assert result.reason == "complete"
    assert result.outcomes[4]["status"] == "DONE"
    assert result.outcomes[4]["reason"] is None
    assert [action.action_type for action in agent.actions] == [
        "reach",
        "grasp",
        "move",
        "release",
    ]
    assert agent.tokens
    assert all(token.covers(action.node_id) for action, token in zip(agent.actions, agent.tokens))
    assert kernel.false_executions == 0
    assert orch.state == IntentOSState.COMPLETE


def test_out_of_scope_replanned_graph_is_refused_not_executed():
    orch, kernel, planner, agent = make_orchestrator()
    kernel.active_token_id = "auth_abc"
    orch._objective_authorization = active_objective_auth("auth_abc")

    def bad_nodes(_available):
        return [
            TaskNode(
                node_id="reach_0",
                action_type="reach",
                agent_id="arm",
                parameters={"object_id": 4, "target_xyz": [0.2, 0.1, 0.7]},
            ),
            TaskNode(
                node_id="move_0",
                action_type="move",
                agent_id="arm",
                parameters={"target": "shelf", "target_xyz": [0.9, 0.9, 1.4]},
                depends_on=["reach_0"],
            ),
        ]

    planner._heuristic.clean_table_nodes_for_objects = bad_nodes

    result = orch.continue_confirmed_objective(table_scene(), set())

    assert not result.accepted
    assert result.reason == "move destination 'shelf' is outside objective scope"
    assert agent.actions == []
    assert kernel.false_executions == 0


def test_continue_confirmed_objective_after_completed_or_revoked_is_refused():
    orch, kernel, _, _ = make_orchestrator()
    kernel.active_token_id = "auth_abc"
    orch._objective_authorization = active_objective_auth("auth_abc")

    orch.complete_objective_authorization("objective_satisfied")
    completed_result = orch.continue_confirmed_objective(table_scene(), set())

    assert not completed_result.accepted
    assert completed_result.reason == "objective authorization is not active"
    assert orch._objective_authorization.status == ObjectiveAuthorizationStatus.COMPLETED

    orch._objective_authorization = active_objective_auth("auth_abc")
    orch.revoke_objective_authorization("max_cycles_exceeded")
    revoked_result = orch.continue_confirmed_objective(table_scene(), set())

    assert not revoked_result.accepted
    assert revoked_result.reason == "objective authorization is not active"
    assert orch._objective_authorization.status == ObjectiveAuthorizationStatus.REVOKED


def test_objective_auth_alone_does_not_bypass_scoped_primitive_gate():
    graph = make_graph(
        [
            TaskNode(
                node_id="reach_0",
                action_type="reach",
                agent_id="arm",
                parameters={"object_id": 4, "target_xyz": [0.2, 0.1, 0.7]},
            )
        ]
    )
    orch, kernel, _, agent = make_orchestrator(graph)
    kernel.active_token_id = "auth_abc"
    orch._objective_authorization = active_objective_auth("auth_abc")
    orch.submit_goal("clean the table", "scene")
    tick_until_not_planning(orch)
    orch._state = IntentOSState.EXECUTING
    orch._current_token = ScopedExecutionToken.issue(
        CheckpointSegment(
            segment_id="wrong_segment",
            node_ids=["some_other_node"],
            requires_confirmation=False,
            summary="wrong node",
        ),
        node_definitions=[],
    )

    orch.tick()

    assert agent.actions == []
    assert graph.nodes[0].status == TaskStatus.FAILED
    assert graph.nodes[0].error == "No valid scoped token"
    assert orch.state == IntentOSState.ERROR
    assert orch._objective_authorization.status == ObjectiveAuthorizationStatus.REVOKED
    assert orch._objective_authorization.reason == "unauthorized_scoped_token"
    assert kernel.false_executions == 0

