"""Tests for IntentPlanner."""
import json
import time

from src.agents import AgentRegistry, ArmAgent
from src.planning import IntentPlanner, PlannerConfig
from src.planning.planner import HeuristicPlanner
from src.task_graph import validate


class QueueGemini:
    def __init__(self, responses=None, exc=None, sleep_s=0.0):
        self.responses = list(responses or [])
        self.exc = exc
        self.sleep_s = sleep_s
        self.calls = []

    def generate(self, prompt: str, timeout_s: float):
        self.calls.append({"prompt": prompt, "timeout_s": timeout_s})
        if self.sleep_s:
            time.sleep(self.sleep_s)
        if self.exc is not None:
            raise self.exc
        return self.responses.pop(0)


def registry():
    reg = AgentRegistry()
    reg.register(ArmAgent(agent_id="arm"))
    return reg


def graph_json(agent_id="arm", depends_on=None, action="reach", node_id="n1"):
    return json.dumps(
        {
            "graph_id": "g_llm",
            "goal": "pick up the red block",
            "plan_confidence": 0.9,
            "nodes": [
                {
                    "node_id": node_id,
                    "action_type": action,
                    "agent_id": agent_id,
                    "parameters": {"target": "red_block"},
                    "depends_on": depends_on or [],
                    "confirmation_policy": "CHECKPOINT",
                    "uncertainty_combined": 0.2,
                }
            ],
        }
    )


def test_llm_valid_first_try_returns_llm_source():
    gemini = QueueGemini([graph_json()])
    planner = IntentPlanner(registry(), PlannerConfig(), gemini_adapter=gemini)

    result = planner.plan("pick up the red block", "red block on table")

    assert result.plan_source == "llm"
    assert result.used_llm
    assert not result.used_fallback
    assert result.repair_attempts == 0
    assert validate(result.graph, {"arm"}) == []
    assert result.planning_duration_ms >= 0.0


def test_invalid_llm_graph_repaired_returns_repaired_source():
    gemini = QueueGemini(
        [
            graph_json(agent_id="drone"),
            graph_json(agent_id="arm"),
        ]
    )
    planner = IntentPlanner(registry(), PlannerConfig(), gemini_adapter=gemini)

    result = planner.plan("pick up the red block", "red block on table")

    assert result.plan_source == "llm_repaired"
    assert result.repair_attempts == 1
    assert not result.used_fallback
    assert validate(result.graph, {"arm"}) == []
    assert len(gemini.calls) == 2
    assert "VIOLATIONS TO FIX" in gemini.calls[1]["prompt"]


def test_invalid_after_repairs_falls_back_to_heuristic():
    gemini = QueueGemini(
        [
            graph_json(agent_id="drone"),
            graph_json(agent_id="drone"),
            graph_json(agent_id="drone"),
        ]
    )
    planner = IntentPlanner(registry(), PlannerConfig(), gemini_adapter=gemini)

    result = planner.plan("clean the table", "messy table")

    assert result.plan_source == "heuristic"
    assert result.used_fallback
    assert result.repair_attempts == 2
    assert validate(result.graph, {"arm"}) == []


def test_llm_disabled_uses_heuristic_without_calling_adapter():
    gemini = QueueGemini([graph_json()])
    planner = IntentPlanner(
        registry(),
        PlannerConfig(llm_enabled=False),
        gemini_adapter=gemini,
    )

    result = planner.plan("home", "arm away from home")

    assert result.plan_source == "heuristic"
    assert result.used_fallback
    assert len(gemini.calls) == 0
    assert result.graph.nodes[0].action_type == "home"


def test_llm_exception_falls_back_and_never_raises():
    gemini = QueueGemini(exc=RuntimeError("network down"))
    planner = IntentPlanner(registry(), PlannerConfig(), gemini_adapter=gemini)

    result = planner.plan("tidy the table", "messy table")

    assert result.plan_source == "heuristic"
    assert result.used_fallback
    assert validate(result.graph, {"arm"}) == []


def test_llm_timeout_falls_back_quickly():
    gemini = QueueGemini([graph_json()], sleep_s=0.05)
    planner = IntentPlanner(
        registry(),
        PlannerConfig(llm_timeout_s=0.005),
        gemini_adapter=gemini,
    )

    t0 = time.monotonic()
    result = planner.plan("pick red block", "red block")
    elapsed = time.monotonic() - t0

    assert result.plan_source == "heuristic"
    assert elapsed < 0.04


def test_heuristic_handles_clean_clear_tidy_home_and_unknown_goals():
    heuristic = HeuristicPlanner(registry())

    for goal in ("clean the table", "clear the table", "tidy the table"):
        graph = heuristic.plan(goal, "scene")
        assert [n.action_type for n in graph.nodes] == [
            "reach",
            "grasp",
            "move",
            "release",
        ]
        assert validate(graph, {"arm"}) == []

    home = heuristic.plan("go home", "scene")
    assert [n.action_type for n in home.nodes] == ["home"]
    assert validate(home, {"arm"}) == []

    unknown = heuristic.plan("do something vague", "scene")
    assert [n.action_type for n in unknown.nodes] == ["reach"]
    assert validate(unknown, {"arm"}) == []
