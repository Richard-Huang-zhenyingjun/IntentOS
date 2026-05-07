"""Planning components.

This module keeps the original deterministic ``ActionPlanner`` used by Phase 2
and adds the IntentOS ``IntentPlanner`` vertical slice for Codex 3B.
"""
from __future__ import annotations

import concurrent.futures
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from src.agents.agent_registry import AgentRegistry
from src.planning.preconditions import Preconditions
from src.robot.actions import ActionType
from src.robot.world_state import WorldState
from src.task_graph.types import (
    ConfirmationPolicy,
    TaskGraph,
    TaskNode,
    UncertaintySignals,
)
from src.task_graph.validator import Violation, validate


logger = logging.getLogger(__name__)

MAX_REPAIR_ATTEMPTS = 2


class ActionPlanner:
    """Deterministic action planner using priority rules."""

    def __init__(self, config: dict):
        self.preconditions = Preconditions(config)

        self.priority = [
            ActionType.MOVE_UP,
            ActionType.REACH,
            ActionType.GRASP,
            ActionType.PLACE,
        ]

    def propose_next_action(self, state: WorldState) -> Optional[ActionType]:
        """Propose next action based on current state."""
        print("[PLANNER] propose_next_action called")
        print(
            "  World state: "
            f"holding={state.holding}, ee_pos={state.ee_position}, "
            f"obj_pos={state.object_position}"
        )

        available = self.preconditions.get_available_actions(state)
        print(f"[PLANNER DEBUG] Available actions: {[a.value for a in available]}")

        if not available:
            print("[PLANNER DEBUG] No available actions!")
            print("[PLANNER] Returning action: None")
            return None

        for action in self.priority:
            if action in available:
                print(f"[PLANNER DEBUG] Selected action: {action.value}")
                print(f"[PLANNER] Returning action: {action}")
                return action

        print("[PLANNER DEBUG] Fallback, returning first available")
        result = available[0] if available else None
        print(f"[PLANNER] Returning action: {result}")
        return result

    def get_action_reason(self, action: ActionType, state: WorldState) -> str:
        """Get human-readable reason for action."""
        if action == ActionType.MOVE_UP:
            return f"End effector too low (z={state.ee_position[2]:.2f}m)"
        if action == ActionType.REACH:
            dist = state.distance_to_object()
            return f"Moving to object (distance={dist:.2f}m)"
        if action == ActionType.GRASP:
            return "Close enough to grasp"
        if action == ActionType.PLACE:
            return f"Holding object {state.attached_id}, ready to place"
        return f"Action: {action.value}"


@dataclass(frozen=True)
class PlannerConfig:
    llm_enabled: bool = True
    llm_timeout_s: float = 10.0
    fallback_on_invalid: bool = True
    log_raw_llm_output: bool = False


@dataclass
class PlanningResult:
    graph: TaskGraph
    used_llm: bool
    used_fallback: bool
    repair_attempts: int
    violations_found: list[Violation]
    planning_duration_ms: float
    plan_source: str


class IntentPlanner:
    """
    Turns a human goal string into a structurally valid TaskGraph.

    LLM calls are isolated here. Any invalid, unavailable, or timed-out LLM path
    falls back to the deterministic heuristic planner.
    """

    def __init__(
        self,
        agent_registry: AgentRegistry,
        cfg: PlannerConfig,
        gemini_adapter=None,
    ):
        self._registry = agent_registry
        self._cfg = cfg
        self._gemini = gemini_adapter
        self._heuristic = HeuristicPlanner(agent_registry)

    def plan(self, goal: str, scene_summary: str) -> PlanningResult:
        """Return a PlanningResult. Never raises."""
        t0 = time.monotonic()
        registered_ids = set(self._registry.all_ids())
        repair_attempts = 0
        violations_found: list[Violation] = []

        try:
            if self._cfg.llm_enabled and self._gemini is not None:
                raw_graph, llm_ok = self._call_llm(goal, scene_summary)

                if llm_ok and raw_graph is not None:
                    violations = validate(raw_graph, registered_ids)
                    violations_found = violations

                    if not violations:
                        return PlanningResult(
                            graph=raw_graph,
                            used_llm=True,
                            used_fallback=False,
                            repair_attempts=0,
                            violations_found=[],
                            planning_duration_ms=(time.monotonic() - t0) * 1000,
                            plan_source="llm",
                        )

                    repaired_graph = raw_graph
                    for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
                        repair_attempts = attempt
                        logger.info(
                            "Plan validation failed (%d violations). Repair attempt %d/%d.",
                            len(violations),
                            attempt,
                            MAX_REPAIR_ATTEMPTS,
                        )
                        repaired_graph, repair_ok = self._call_llm_repair(
                            goal,
                            scene_summary,
                            repaired_graph,
                            violations,
                        )
                        if not repair_ok or repaired_graph is None:
                            break

                        violations = validate(repaired_graph, registered_ids)
                        violations_found = violations
                        if not violations:
                            return PlanningResult(
                                graph=repaired_graph,
                                used_llm=True,
                                used_fallback=False,
                                repair_attempts=repair_attempts,
                                violations_found=[],
                                planning_duration_ms=(time.monotonic() - t0) * 1000,
                                plan_source="llm_repaired",
                            )

                    logger.warning(
                        "LLM plan invalid after repair attempts. Violations: %s",
                        [v.rule for v in violations_found],
                    )
        except Exception as exc:
            logger.warning("Planning failed before fallback: %s", exc)

        fallback_graph = self._heuristic.plan(goal, scene_summary)
        fallback_violations = validate(fallback_graph, registered_ids)
        if fallback_violations:
            logger.error(
                "Heuristic fallback produced invalid graph: %s",
                [v.rule for v in fallback_violations],
            )
            violations_found = fallback_violations

        return PlanningResult(
            graph=fallback_graph,
            used_llm=self._cfg.llm_enabled,
            used_fallback=True,
            repair_attempts=repair_attempts,
            violations_found=violations_found,
            planning_duration_ms=(time.monotonic() - t0) * 1000,
            plan_source="heuristic",
        )

    def _call_llm(self, goal: str, scene_summary: str) -> tuple[Optional[TaskGraph], bool]:
        prompt = _build_planning_prompt(goal, scene_summary, self._registry.all_ids())
        try:
            raw_text = _generate_with_timeout(
                self._gemini,
                prompt,
                timeout_s=self._cfg.llm_timeout_s,
            )
            if self._cfg.log_raw_llm_output:
                logger.debug("LLM raw output:\n%s", raw_text)
            graph = _parse_llm_response(raw_text, goal)
            return graph, graph is not None
        except Exception as exc:
            logger.warning("LLM call failed: %s", exc)
            return None, False

    def _call_llm_repair(
        self,
        goal: str,
        scene_summary: str,
        invalid_graph: TaskGraph,
        violations: list[Violation],
    ) -> tuple[Optional[TaskGraph], bool]:
        del scene_summary
        violation_text = "\n".join(
            f"- Rule '{v.rule}' on node '{v.node_id}': {v.message}"
            for v in violations
        )
        prompt = _build_repair_prompt(goal, _graph_to_json(invalid_graph), violation_text)

        try:
            raw_text = _generate_with_timeout(
                self._gemini,
                prompt,
                timeout_s=self._cfg.llm_timeout_s,
            )
            graph = _parse_llm_response(raw_text, goal)
            return graph, graph is not None
        except Exception as exc:
            logger.warning("LLM repair call failed: %s", exc)
            return None, False


class HeuristicPlanner:
    """Deterministic fallback planner. Produces simple valid arm-only graphs."""

    def __init__(self, registry: AgentRegistry):
        self._registry = registry

    def plan(self, goal: str, scene_summary: str) -> TaskGraph:
        del scene_summary
        goal_lower = goal.lower()
        graph_id = str(uuid.uuid4())[:8]

        if any(word in goal_lower for word in ("clean", "clear", "tidy")):
            nodes = self._clean_table_nodes()
        elif "home" in goal_lower:
            nodes = self._home_nodes()
        else:
            logger.info("Unknown goal %r - using safe single-reach plan.", goal)
            nodes = self._safe_default_nodes(goal)

        return TaskGraph(
            graph_id=graph_id,
            goal=goal,
            nodes=nodes,
            created_at=time.time(),
            plan_confidence=0.6,
            interpretation_note="Heuristic plan (LLM unavailable or invalid)",
        )

    def _clean_table_nodes(self) -> list[TaskNode]:
        return [
            TaskNode(
                node_id="reach_0",
                action_type="reach",
                agent_id="arm",
                parameters={"target": "nearest_object"},
                depends_on=[],
                confirmation_policy=ConfirmationPolicy.CHECKPOINT,
                uncertainty=UncertaintySignals.unknown(),
            ),
            TaskNode(
                node_id="grasp_0",
                action_type="grasp",
                agent_id="arm",
                parameters={},
                depends_on=["reach_0"],
                confirmation_policy=ConfirmationPolicy.NEVER,
                uncertainty=UncertaintySignals.unknown(),
            ),
            TaskNode(
                node_id="move_0",
                action_type="move",
                agent_id="arm",
                parameters={"target": "bin"},
                depends_on=["grasp_0"],
                confirmation_policy=ConfirmationPolicy.NEVER,
                uncertainty=UncertaintySignals.unknown(),
            ),
            TaskNode(
                node_id="release_0",
                action_type="release",
                agent_id="arm",
                parameters={},
                depends_on=["move_0"],
                confirmation_policy=ConfirmationPolicy.NEVER,
                uncertainty=UncertaintySignals.unknown(),
            ),
        ]

    def _home_nodes(self) -> list[TaskNode]:
        return [
            TaskNode(
                node_id="home_0",
                action_type="home",
                agent_id="arm",
                parameters={},
                depends_on=[],
                confirmation_policy=ConfirmationPolicy.CHECKPOINT,
                uncertainty=UncertaintySignals(
                    perception_confidence=1.0,
                    execution_history_rate=1.0,
                    simulation_risk=0.0,
                ),
            )
        ]

    def _safe_default_nodes(self, goal: str) -> list[TaskNode]:
        return [
            TaskNode(
                node_id="reach_default",
                action_type="reach",
                agent_id="arm",
                parameters={"target": "nearest_object", "goal_context": goal},
                depends_on=[],
                confirmation_policy=ConfirmationPolicy.CHECKPOINT,
                uncertainty=UncertaintySignals.unknown(),
            )
        ]


def _build_planning_prompt(
    goal: str,
    scene_summary: str,
    registered_agent_ids: list[str],
) -> str:
    return f"""You are a robot task planner. Produce a task graph for the given goal.

GOAL: {goal}

CURRENT SCENE:
{scene_summary}

AVAILABLE AGENTS: {', '.join(registered_agent_ids)}
AVAILABLE ACTIONS PER AGENT: reach, grasp, move, release, home

RULES:
1. Each node must have a unique node_id string.
2. Each node's agent_id must be one of the available agents.
3. depends_on must list node_ids that appear earlier in the list.
4. No circular dependencies.
5. action_type must be one of: reach, grasp, move, release, home.
6. uncertainty_combined is a float 0.0 (certain) to 1.0 (uncertain).

OUTPUT FORMAT - JSON only, no preamble, no markdown:
{{
  "graph_id": "unique_id",
  "goal": "{goal}",
  "plan_confidence": 0.85,
  "nodes": [
    {{
      "node_id": "reach_0",
      "action_type": "reach",
      "agent_id": "arm",
      "parameters": {{"target": "red_block"}},
      "depends_on": [],
      "confirmation_policy": "CHECKPOINT",
      "uncertainty_combined": 0.2
    }}
  ]
}}

Respond with valid JSON only. No other text."""


def _build_repair_prompt(goal: str, graph_json: str, violation_text: str) -> str:
    return f"""The following task graph has validation errors. Fix ONLY the listed violations.
Do not change any other nodes. Respond with the corrected JSON only.

GOAL: {goal}

VIOLATIONS TO FIX:
{violation_text}

CURRENT GRAPH:
{graph_json}

Respond with corrected JSON only. No other text."""


def _parse_llm_response(raw_text: str, goal: str) -> Optional[TaskGraph]:
    """Parse LLM JSON response into TaskGraph. Returns None on parse errors."""
    try:
        text = _strip_markdown_fences(raw_text)
        data = json.loads(text)

        nodes = []
        for n in data.get("nodes", []):
            uc = _clamp01(float(n.get("uncertainty_combined", 0.5)))
            uncertainty = UncertaintySignals(
                perception_confidence=_clamp01(1.0 - uc),
                execution_history_rate=0.5,
                simulation_risk=_clamp01(uc * 0.5),
            )

            policy_str = str(n.get("confirmation_policy", "CHECKPOINT")).upper()
            policy = ConfirmationPolicy.__members__.get(
                policy_str,
                ConfirmationPolicy.CHECKPOINT,
            )

            nodes.append(
                TaskNode(
                    node_id=str(n["node_id"]),
                    action_type=str(n["action_type"]),
                    agent_id=str(n["agent_id"]),
                    parameters=dict(n.get("parameters", {})),
                    depends_on=[str(d) for d in n.get("depends_on", [])],
                    confirmation_policy=policy,
                    uncertainty=uncertainty,
                )
            )

        return TaskGraph(
            graph_id=str(data.get("graph_id", str(uuid.uuid4())[:8])),
            goal=goal,
            nodes=nodes,
            created_at=time.time(),
            plan_confidence=float(data.get("plan_confidence", 0.7)),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        logger.warning("Failed to parse LLM response: %s", exc)
        return None


def _graph_to_json(graph: TaskGraph) -> str:
    """Serialize TaskGraph to JSON for repair prompts."""
    return json.dumps(
        {
            "graph_id": graph.graph_id,
            "goal": graph.goal,
            "plan_confidence": graph.plan_confidence,
            "nodes": [
                {
                    "node_id": n.node_id,
                    "action_type": n.action_type,
                    "agent_id": n.agent_id,
                    "parameters": n.parameters,
                    "depends_on": n.depends_on,
                    "confirmation_policy": n.confirmation_policy.name,
                    "uncertainty_combined": round(n.uncertainty.combined, 2),
                }
                for n in graph.nodes
            ],
        },
        indent=2,
    )


def _generate_with_timeout(adapter, prompt: str, timeout_s: float) -> str:
    """Call a Gemini-like adapter with a caller-side timeout."""
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(_generate_text, adapter, prompt, timeout_s)
        return future.result(timeout=timeout_s)
    except concurrent.futures.TimeoutError as exc:
        future.cancel()
        raise TimeoutError(f"LLM call timed out after {timeout_s:.2f}s") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _generate_text(adapter, prompt: str, timeout_s: float) -> str:
    if hasattr(adapter, "generate"):
        return str(adapter.generate(prompt=prompt, timeout_s=timeout_s))

    if hasattr(adapter, "analyze"):
        response = adapter.analyze(scene_text=prompt)
        return str(getattr(response, "raw_text", response))

    raise TypeError("Gemini adapter must expose generate() or analyze()")


def _strip_markdown_fences(raw_text: str) -> str:
    text = raw_text.strip()
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
