"""IntentOS 3A foundation tests."""
from __future__ import annotations

import numpy as np

from src.agents import AgentAction, AgentRegistry, ArmAgent
from src.agents.agent_base import AgentStatus
from src.interfaces.primitive import Primitive, PrimitiveType
from src.kernel import ExecutionKernel, KernelState
from src.task_graph import TaskGraph, TaskNode
from src.task_graph.validator import validate_task_graph


class FakeController:
    def __init__(self):
        self.executing = False
        self.moves = []

    def move_to_position(self, target):
        self.executing = True
        self.moves.append(np.asarray(target, dtype=float))


class FakeExecutor:
    def __init__(self):
        self.started = []

    def start_plan(self, plan):
        self.started.append(plan)


class FakeGrasp:
    def __init__(self):
        self.closed = False
        self.opened = False

    def close(self):
        self.closed = True

    def open(self):
        self.opened = True


class FakeToken:
    token_id = "tok_test"


class FakeOrchestrator:
    def __init__(self):
        self.global_frame_counter = 0
        self.trust_metrics = type("Trust", (), {"false_executions": 0})()
        self.executor = type("Exec", (), {"status": type("Status", (), {"value": "idle"})()})()
        self.auth_manager = type("Auth", (), {"get_active_token_id": lambda self: "tok_1"})()
        self.closed = False

    def step(self):
        self.global_frame_counter += 1
        return type("Snapshot", (), {"state": type("State", (), {"value": "idle"})()})()

    def close(self):
        self.closed = True


class FakeInvariant:
    def __init__(self):
        self.false_executions = 0
        self.asserted = False

    def assert_invariant(self):
        self.asserted = True


def test_kernel_api_wraps_orchestrator_without_mutating_safety_path():
    orch = FakeOrchestrator()
    kernel = ExecutionKernel(orch)

    snapshot = kernel.step()

    assert snapshot.frame == 1
    assert snapshot.state is KernelState.IDLE
    assert snapshot.capabilities.false_executions == 0
    assert snapshot.active_token_id == "tok_1"
    kernel.assert_safety_invariant()
    kernel.close()
    assert orch.closed


def test_execution_kernel_explicit_dependencies_and_callbacks():
    orch = FakeOrchestrator()
    inv = FakeInvariant()
    seen = []
    kernel = ExecutionKernel(orch, orch.auth_manager, inv)
    kernel.register_event_callback(seen.append)

    receipt = kernel.submit_proposal({"goal": "clean table"})
    events = kernel.poll_events()
    snapshot = kernel.step()

    assert receipt.accepted
    assert receipt.proposal_id
    assert events[0].kind == "proposal_submitted"
    assert seen[0].kind == "proposal_submitted"
    assert snapshot.state is KernelState.IDLE
    assert inv.asserted


def test_execution_kernel_state_transition_event():
    class MutableStateOrchestrator(FakeOrchestrator):
        def __init__(self):
            super().__init__()
            self.state = "IDLE"

    orch = MutableStateOrchestrator()
    kernel = ExecutionKernel(orch)
    orch.state = "CONFIRMING"

    events = kernel.poll_events()

    assert events[0].kind == "awaiting_confirm"
    assert events[0].details == {"from": "IDLE", "to": "AWAITING_CONFIRM"}


def test_execution_kernel_assert_invariant_raises_runtime_error():
    orch = FakeOrchestrator()
    inv = FakeInvariant()
    inv.false_executions = 1
    kernel = ExecutionKernel(orch, invariant_checker=inv)

    try:
        kernel.assert_invariant()
    except RuntimeError as exc:
        assert "SAFETY VIOLATION" in str(exc)
    else:
        assert False, "Expected safety invariant violation"


def test_kernel_capabilities_gate_proposal_submission():
    orch = FakeOrchestrator()
    kernel = ExecutionKernel(orch, active_agent_ids=frozenset({"arm"}))

    capabilities = kernel.get_capabilities()
    receipt = kernel.submit_proposal("proposal_1", {"goal": "clean table"})
    events = kernel.drain_events()

    assert capabilities.can_accept_proposal
    assert capabilities.active_agent_ids == frozenset({"arm"})
    assert receipt.accepted
    assert receipt.proposal_id == "proposal_1"
    assert events[0].kind == "proposal_submitted"


def test_kernel_rejects_proposal_when_not_idle():
    class ConfirmingOrchestrator(FakeOrchestrator):
        def step(self):
            self.global_frame_counter += 1
            return type("Snapshot", (), {"state": type("State", (), {"value": "confirming"})()})()

    kernel = ExecutionKernel(ConfirmingOrchestrator())
    kernel.step()

    receipt = kernel.submit_proposal("proposal_1", {"goal": "clean table"})

    assert not receipt.accepted
    assert "Kernel not ready" in receipt.rejection_reason


def test_agent_registry_registers_and_retrieves_agents():
    registry = AgentRegistry()
    agent = ArmAgent(agent_id="arm_1")

    registry.register(agent)

    assert "arm_1" in registry
    assert registry.get("arm_1") is agent
    assert registry.all_ids() == ["arm_1"]
    assert registry.all_agents() == [agent]


def test_agent_registry_rejects_duplicate_ids():
    registry = AgentRegistry()
    registry.register(ArmAgent(agent_id="arm_1"))

    try:
        registry.register(ArmAgent(agent_id="arm_1"))
    except ValueError as exc:
        assert "Agent 'arm_1' already registered" in str(exc)
    else:
        assert False, "Expected duplicate registration to fail"


def test_arm_agent_executes_reach_through_existing_controller():
    executor = FakeExecutor()
    agent = ArmAgent(primitive_executor=executor, grasp=FakeGrasp())
    action = AgentAction(
        node_id="n1",
        action_type="reach",
        parameters={"target_xyz": np.array([0.1, 0.2, 0.3])},
        agent_id="arm",
    )

    result = agent.execute(action, token=FakeToken())

    assert result.success
    assert result.node_id == "n1"
    assert len(executor.started) == 1
    assert np.allclose(executor.started[0][0].target_xyz, np.array([0.1, 0.2, 0.3]))
    assert agent.get_state().status == AgentStatus.IDLE


def test_arm_agent_can_coerce_dict_action():
    controller = FakeController()
    agent = ArmAgent(controller=controller)

    assert agent.can_execute({"type": "reach", "target_xyz": [0, 0, 1]}) == (True, None)
    can_do, reason = agent.can_execute({"type": "teleport"})
    assert not can_do
    assert "Unsupported action" in reason


def test_arm_agent_submits_without_local_token_check():
    executor = FakeExecutor()
    agent = ArmAgent(primitive_executor=executor)
    action = AgentAction(
        node_id="n1",
        action_type="reach",
        parameters={"target_xyz": [0, 0, 1]},
        agent_id="arm",
    )

    result = agent.execute(action, token=None)

    assert result.success
    assert len(executor.started) == 1


def test_task_graph_validator_accepts_valid_dag():
    registry = AgentRegistry()
    registry.register(ArmAgent(agent_id="arm"))
    graph = TaskGraph.from_nodes(
        graph_id="g1",
        nodes=[
            TaskNode(node_id="n1", agent_id="arm", action_type="reach"),
            TaskNode(node_id="n2", agent_id="arm", action_type="grasp", depends_on=frozenset({"n1"})),
        ],
    )

    result = validate_task_graph(graph, registry)

    assert result.ok
    assert result.topological_order == ("n1", "n2")


def test_task_graph_validator_reports_missing_dependency_and_unknown_agent():
    registry = AgentRegistry()
    graph = TaskGraph.from_nodes(
        graph_id="g1",
        nodes=[
            TaskNode(node_id="n1", agent_id="missing", action_type="reach", depends_on=frozenset({"ghost"})),
        ],
    )

    result = validate_task_graph(graph, registry)

    assert not result.ok
    assert {issue.rule for issue in result.issues} >= {"missing_dependency", "unknown_agent_id"}


def test_task_graph_validator_detects_cycles():
    registry = AgentRegistry()
    registry.register(ArmAgent(agent_id="arm"))
    graph = TaskGraph.from_nodes(
        graph_id="g1",
        nodes=[
            TaskNode(node_id="a", agent_id="arm", action_type="reach", depends_on=frozenset({"b"})),
            TaskNode(node_id="b", agent_id="arm", action_type="grasp", depends_on=frozenset({"a"})),
        ],
    )

    result = validate_task_graph(graph, registry)

    assert not result.ok
    assert "cycle" in {issue.rule for issue in result.issues}
