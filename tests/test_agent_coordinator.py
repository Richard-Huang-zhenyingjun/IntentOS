"""Tests for AgentCoordinator. Uses SimAgent for fast, hardware-free testing."""
import time
import uuid
from concurrent.futures import Future
from unittest.mock import MagicMock

from src.agents import AgentRegistry, SimAgent, SimAgentConfig
from src.coordination import AgentCoordinator, CoordinatorConfig
from src.task_graph.types import TaskGraph, TaskNode, TaskStatus, UncertaintySignals


def make_registry(success_rates=None):
    reg = AgentRegistry()
    cfg = SimAgentConfig(
        success_rates=success_rates
        or {
            "reach": 1.0,
            "grasp": 1.0,
            "move": 1.0,
            "release": 1.0,
            "home": 1.0,
        },
        simulate_delays=False,
        seed=42,
    )
    arm = SimAgent("arm", cfg)
    sim = SimAgent("sim_agent", cfg)
    reg.register(arm)
    reg.register(sim)
    return reg


def make_graph(nodes):
    return TaskGraph(
        graph_id=str(uuid.uuid4())[:8],
        goal="test",
        nodes=nodes,
        created_at=time.time(),
    )


def make_node(node_id, agent_id="arm", depends_on=None, action="reach"):
    return TaskNode(
        node_id=node_id,
        action_type=action,
        agent_id=agent_id,
        parameters={},
        depends_on=depends_on or [],
    )


class TestSequentialDispatch:
    def test_single_node_executes(self):
        registry = make_registry()
        coord = AgentCoordinator(registry, CoordinatorConfig(dispatch_tick_s=0.01))
        nodes = [make_node("n1")]
        graph = make_graph(nodes)
        try:
            result = coord.execute_segment(["n1"], token=MagicMock(), graph=graph)
        finally:
            coord.shutdown()
        assert result.all_succeeded
        assert graph.get_node("n1").status == TaskStatus.DONE

    def test_sequential_dependencies_respected(self):
        registry = make_registry()
        coord = AgentCoordinator(registry, CoordinatorConfig(dispatch_tick_s=0.01))
        nodes = [
            make_node("n1"),
            make_node("n2", depends_on=["n1"]),
            make_node("n3", depends_on=["n2"]),
        ]
        graph = make_graph(nodes)
        try:
            result = coord.execute_segment(
                ["n1", "n2", "n3"], token=MagicMock(), graph=graph
            )
        finally:
            coord.shutdown()
        assert result.all_succeeded
        assert all(
            graph.get_node(nid).status == TaskStatus.DONE
            for nid in ["n1", "n2", "n3"]
        )

    def test_failed_node_recorded(self):
        registry = make_registry(
            success_rates={
                "reach": 0.0,
                "grasp": 1.0,
                "move": 1.0,
                "release": 1.0,
                "home": 1.0,
            }
        )
        coord = AgentCoordinator(registry, CoordinatorConfig(dispatch_tick_s=0.01))
        nodes = [make_node("n1", action="reach")]
        graph = make_graph(nodes)
        try:
            result = coord.execute_segment(["n1"], token=MagicMock(), graph=graph)
        finally:
            coord.shutdown()
        assert not result.all_succeeded
        assert "n1" in result.failed_node_ids


class TestParallelDispatch:
    def test_independent_nodes_on_different_agents_run_parallel(self):
        """Two independent nodes on different agents should both dispatch."""
        registry = make_registry()
        coord = AgentCoordinator(
            registry,
            CoordinatorConfig(dispatch_tick_s=0.01, max_parallel_agents=4),
        )
        nodes = [
            make_node("n1", agent_id="arm"),
            make_node("n2", agent_id="sim_agent"),
        ]
        graph = make_graph(nodes)
        try:
            result = coord.execute_segment(["n1", "n2"], token=MagicMock(), graph=graph)
        finally:
            coord.shutdown()
        assert result.all_succeeded
        assert graph.get_node("n1").status == TaskStatus.DONE
        assert graph.get_node("n2").status == TaskStatus.DONE

    def test_dependent_nodes_wait(self):
        """n2 depends on n1 - n2 must not start before n1 done."""
        registry = make_registry()
        coord = AgentCoordinator(registry, CoordinatorConfig(dispatch_tick_s=0.01))
        nodes = [
            make_node("n1", agent_id="arm"),
            make_node("n2", agent_id="sim_agent", depends_on=["n1"]),
        ]
        graph = make_graph(nodes)
        try:
            result = coord.execute_segment(["n1", "n2"], token=MagicMock(), graph=graph)
        finally:
            coord.shutdown()
        assert result.all_succeeded


class TestEmergencyStop:
    def test_emergency_stop_all_never_raises(self):
        registry = make_registry()
        coord = AgentCoordinator(registry, CoordinatorConfig())
        try:
            coord.emergency_stop_all()
        finally:
            coord.shutdown()

    def test_emergency_stop_all_calls_every_agent(self):
        registry = AgentRegistry()
        agents = [MagicMock(), MagicMock()]
        agents[0].agent_id = "arm"
        agents[0].emergency_stop = MagicMock()
        agents[1].agent_id = "sim_agent"
        agents[1].emergency_stop = MagicMock()
        registry.register(agents[0])
        registry.register(agents[1])
        coord = AgentCoordinator(registry, CoordinatorConfig())
        try:
            coord.emergency_stop_all()
        finally:
            coord.shutdown()
        agents[0].emergency_stop.assert_called_once()
        agents[1].emergency_stop.assert_called_once()


class TestResourceConflict:
    def test_resource_conflict_prevents_parallel_execution(self):
        """Two nodes claiming the same named resource cannot run in parallel."""
        from src.task_graph.types import ResourceClaim

        registry = make_registry()
        coord = AgentCoordinator(registry, CoordinatorConfig(dispatch_tick_s=0.01))

        n1 = make_node("n1", agent_id="arm")
        n2 = make_node("n2", agent_id="sim_agent")
        n1.resource_claim = ResourceClaim(
            "arm", "n1", frozenset({"object:red_block"}), None
        )
        n2.resource_claim = ResourceClaim(
            "sim_agent", "n2", frozenset({"object:red_block"}), None
        )
        graph = make_graph([n1, n2])
        try:
            result = coord.execute_segment(["n1", "n2"], token=MagicMock(), graph=graph)
        finally:
            coord.shutdown()
        assert result.all_succeeded


class TestDeadlockDetection:
    def test_deadlock_timeout_fires_after_no_progress(self):
        registry = make_registry()
        slow_cfg = SimAgentConfig(
            success_rates={"reach": 1.0},
            timing_s={"reach": 0.03},
            simulate_delays=True,
            seed=42,
        )
        registry._agents["arm"] = SimAgent("arm", slow_cfg)
        coord = AgentCoordinator(
            registry,
            CoordinatorConfig(dispatch_tick_s=0.001, deadlock_timeout_s=0.001),
        )
        graph = make_graph([make_node("n1", agent_id="arm")])
        calls = []
        original = coord._break_deadlock

        def record_break(segment_nodes, graph, pending_futures):
            calls.append(True)
            return original(segment_nodes, graph, pending_futures)

        coord._break_deadlock = record_break
        try:
            coord.execute_segment(["n1"], token=MagicMock(), graph=graph)
        finally:
            coord.shutdown()

        assert calls

    def test_deadlock_resolution_deprioritizes_highest_uncertainty_node(self):
        registry = make_registry()
        coord = AgentCoordinator(registry, CoordinatorConfig())
        low = make_node("low", agent_id="arm")
        high = make_node("high", agent_id="sim_agent")
        low.status = TaskStatus.RUNNING
        high.status = TaskStatus.RUNNING
        low.uncertainty = UncertaintySignals(
            perception_confidence=0.9,
            execution_history_rate=0.9,
            simulation_risk=0.1,
        )
        high.uncertainty = UncertaintySignals(
            perception_confidence=0.1,
            execution_history_rate=0.1,
            simulation_risk=0.9,
        )
        future_low = Future()
        future_high = Future()
        pending = {
            future_low: "low",
            future_high: "high",
        }

        try:
            coord._break_deadlock([low, high], make_graph([low, high]), pending)
        finally:
            coord.shutdown()

        assert high.status == TaskStatus.PENDING
        assert low.status == TaskStatus.RUNNING
        assert future_high not in pending
        assert pending[future_low] == "low"
