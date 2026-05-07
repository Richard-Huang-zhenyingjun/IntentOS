"""Tests for IntentPlanner. LLM is mocked - no real API calls."""
import time
import pytest
from unittest.mock import MagicMock

from src.agents import AgentRegistry
from src.planning import IntentPlanner, PlannerConfig


@pytest.fixture
def registry():
    reg = AgentRegistry()
    arm = MagicMock()
    arm.agent_id = "arm"
    arm.can_execute = MagicMock(return_value=(True, None))
    reg.register(arm)
    return reg


@pytest.fixture
def planner_no_llm(registry):
    cfg = PlannerConfig(llm_enabled=False)
    return IntentPlanner(agent_registry=registry, cfg=cfg, gemini_adapter=None)


@pytest.fixture
def mock_gemini():
    adapter = MagicMock()
    adapter.generate = MagicMock(
        return_value="""
{
  "graph_id": "test_001",
  "goal": "clean table",
  "plan_confidence": 0.8,
  "nodes": [
    {
      "node_id": "reach_0",
      "action_type": "reach",
      "agent_id": "arm",
      "parameters": {"target": "red_block"},
      "depends_on": [],
      "confirmation_policy": "CHECKPOINT",
      "uncertainty_combined": 0.2
    },
    {
      "node_id": "grasp_0",
      "action_type": "grasp",
      "agent_id": "arm",
      "parameters": {},
      "depends_on": ["reach_0"],
      "confirmation_policy": "NEVER",
      "uncertainty_combined": 0.3
    }
  ]
}
"""
    )
    return adapter


class TestHeuristicFallback:
    def test_always_returns_valid_graph(self, planner_no_llm):
        result = planner_no_llm.plan("clean the table", "scene summary")
        assert result.graph is not None
        assert len(result.graph.nodes) > 0
        assert result.plan_source == "heuristic"
        assert result.used_fallback is True

    def test_clean_table_produces_reach_grasp_move_release(self, planner_no_llm):
        result = planner_no_llm.plan("clean the table", "messy table")
        action_types = [n.action_type for n in result.graph.nodes]
        assert "reach" in action_types
        assert "grasp" in action_types
        assert "move" in action_types
        assert "release" in action_types

    def test_home_goal_produces_home_node(self, planner_no_llm):
        result = planner_no_llm.plan("go home", "scene")
        action_types = [n.action_type for n in result.graph.nodes]
        assert "home" in action_types

    def test_heuristic_graph_passes_validation(self, planner_no_llm, registry):
        from src.task_graph.validator import validate

        result = planner_no_llm.plan("clean table", "scene")
        violations = validate(result.graph, set(registry.all_ids()))
        assert violations == [], f"Heuristic plan has violations: {violations}"

    def test_never_raises(self, planner_no_llm):
        result = planner_no_llm.plan("", "")
        assert result is not None

        result = planner_no_llm.plan("x" * 1000, "scene")
        assert result is not None


class TestLLMPlanner:
    def test_llm_success_returns_llm_source(self, registry, mock_gemini):
        cfg = PlannerConfig(llm_enabled=True)
        planner = IntentPlanner(registry, cfg, mock_gemini)
        result = planner.plan("clean table", "scene")
        assert result.plan_source == "llm"
        assert result.used_llm is True
        assert result.used_fallback is False

    def test_llm_timeout_falls_back_to_heuristic(self, registry):
        adapter = MagicMock()
        adapter.generate = MagicMock(side_effect=TimeoutError("timeout"))
        cfg = PlannerConfig(llm_enabled=True)
        planner = IntentPlanner(registry, cfg, adapter)
        result = planner.plan("clean table", "scene")
        assert result.plan_source == "heuristic"

    def test_llm_invalid_json_falls_back(self, registry):
        adapter = MagicMock()
        adapter.generate = MagicMock(return_value="not valid json {{{{")
        cfg = PlannerConfig(llm_enabled=True)
        planner = IntentPlanner(registry, cfg, adapter)
        result = planner.plan("clean table", "scene")
        assert result.plan_source == "heuristic"

    def test_planning_duration_recorded(self, planner_no_llm):
        result = planner_no_llm.plan("clean table", "scene")
        assert result.planning_duration_ms >= 0.0


class TestProposalEngine:
    def test_proposal_has_summary(self, planner_no_llm):
        from src.planning.proposal_engine import ProposalEngine

        result = planner_no_llm.plan("clean table", "scene")
        engine = ProposalEngine()
        proposal = engine.propose(result.graph, result.plan_source, "test_001")
        assert proposal.summary
        assert len(proposal.summary) <= 200

    def test_heuristic_plan_shows_warning(self, planner_no_llm):
        from src.planning.proposal_engine import ProposalEngine

        result = planner_no_llm.plan("clean table", "scene")
        engine = ProposalEngine()
        proposal = engine.propose(result.graph, "heuristic", "test_002")
        assert proposal.warning is not None
        assert "heuristic" in proposal.warning.lower()

    def test_abort_level_for_high_uncertainty(self, registry):
        from src.planning.proposal_engine import ProposalEngine
        from src.task_graph.types import TaskGraph, TaskNode, UncertaintySignals

        node = TaskNode(
            node_id="n1",
            action_type="reach",
            agent_id="arm",
            parameters={},
            depends_on=[],
            uncertainty=UncertaintySignals(
                perception_confidence=0.0,
                execution_history_rate=0.0,
                simulation_risk=1.0,
            ),
        )
        graph = TaskGraph(
            graph_id="test",
            goal="test",
            nodes=[node],
            created_at=0,
        )
        engine = ProposalEngine()
        proposal = engine.propose(graph, "llm", "test_003")
        assert proposal.uncertainty_level == "abort"


class TestIntentOSOrchestrator:
    def test_goal_accepted_when_idle(self):
        from src.intentos import IntentOSConfig, IntentOSOrchestrator

        kernel = MagicMock()
        kernel.get_state = MagicMock(return_value=MagicMock(name="IDLE"))
        kernel.get_capabilities = MagicMock(
            return_value=MagicMock(can_accept_proposal=True, false_executions=0)
        )
        kernel.step = MagicMock()
        kernel.poll_events = MagicMock(return_value=[])
        kernel.assert_invariant = MagicMock()
        kernel.submit_proposal = MagicMock(
            return_value=MagicMock(accepted=True, proposal_id="test")
        )

        registry = AgentRegistry()
        planner = MagicMock()
        planner.plan = MagicMock(
            return_value=MagicMock(
                graph=MagicMock(nodes=[], goal="clean", graph_id="g1"),
                plan_source="heuristic",
                planning_duration_ms=10.0,
            )
        )

        orch = IntentOSOrchestrator(kernel, registry, planner, IntentOSConfig())
        accepted = orch.submit_goal("clean table", "scene")
        assert accepted

    def test_goal_rejected_when_busy(self):
        from src.intentos import IntentOSConfig, IntentOSOrchestrator, IntentOSState

        kernel = MagicMock()
        kernel.get_capabilities = MagicMock(return_value=MagicMock(false_executions=0))
        orch = IntentOSOrchestrator(kernel, AgentRegistry(), MagicMock(), IntentOSConfig())
        orch._state = IntentOSState.EXECUTING
        accepted = orch.submit_goal("clean table", "scene")
        assert not accepted

    def test_invariant_asserted_every_tick(self):
        from src.intentos import IntentOSConfig, IntentOSOrchestrator

        kernel = MagicMock()
        kernel.step = MagicMock()
        kernel.poll_events = MagicMock(return_value=[])
        kernel.assert_invariant = MagicMock()
        kernel.get_capabilities = MagicMock(return_value=MagicMock(false_executions=0))
        orch = IntentOSOrchestrator(kernel, AgentRegistry(), MagicMock(), IntentOSConfig())
        orch.tick()
        kernel.assert_invariant.assert_called_once()


class TestAsyncPlanning:
    def _kernel(self):
        kernel = MagicMock()
        kernel.step = MagicMock()
        kernel.poll_events = MagicMock(return_value=[])
        kernel.assert_invariant = MagicMock()
        kernel.get_state = MagicMock(return_value=MagicMock(name="IDLE"))
        kernel.get_capabilities = MagicMock(
            return_value=MagicMock(can_accept_proposal=True, false_executions=0)
        )
        kernel.submit_proposal = MagicMock(return_value=MagicMock(accepted=True))
        return kernel

    def test_tick_loop_continues_during_planning(self):
        """
        Phase 2 step() must be called even while planning is in progress.
        Verifies non-blocking behavior.
        """
        from src.intentos import IntentOSConfig, IntentOSOrchestrator

        kernel = self._kernel()

        slow_planner = MagicMock()

        def slow_plan(goal, scene):
            time.sleep(0.3)
            result = MagicMock()
            result.graph = MagicMock()
            result.graph.plan_confidence = 0.8
            result.graph.nodes = []
            result.graph.graph_id = "g1"
            result.graph.goal = goal
            result.graph.is_complete = MagicMock(return_value=True)
            result.graph.has_failures = MagicMock(return_value=False)
            result.plan_source = "heuristic"
            result.planning_duration_ms = 300.0
            return result

        slow_planner.plan = MagicMock(side_effect=slow_plan)

        orch = IntentOSOrchestrator(
            kernel,
            AgentRegistry(),
            slow_planner,
            IntentOSConfig(),
        )
        orch.submit_goal("clean table", "scene")

        tick_count = 0
        start = time.monotonic()
        while time.monotonic() - start < 0.6:
            orch.tick()
            tick_count += 1
            time.sleep(0.05)

        assert kernel.step.call_count == tick_count, (
            f"kernel.step() called {kernel.step.call_count} times, "
            f"expected {tick_count} (once per tick)"
        )
        assert slow_planner.plan.called

    def test_background_planning_exception_sets_error(self):
        from src.intentos import IntentOSConfig, IntentOSOrchestrator, IntentOSState

        kernel = self._kernel()
        planner = MagicMock()
        planner.plan = MagicMock(side_effect=RuntimeError("planner exploded"))
        orch = IntentOSOrchestrator(
            kernel,
            AgentRegistry(),
            planner,
            IntentOSConfig(),
        )

        orch.submit_goal("clean table", "scene")
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and orch.state != IntentOSState.ERROR:
            orch.tick()
            time.sleep(0.01)

        assert orch.state == IntentOSState.ERROR
