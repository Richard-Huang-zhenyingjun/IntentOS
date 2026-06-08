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
        self._world_artifacts = None
        self._sim = None
        self._label_map = {}
        self._id_to_label = {}
        self._moved_object_ids: set = set()

    def set_world_context(self, world_artifacts, sim) -> None:
        """Attach optional simulator context for coordinate grounding."""
        self._world_artifacts = world_artifacts
        self._sim = sim

    def set_object_labels(self, label_map: dict) -> None:
        """
        Map semantic labels to PyBullet body IDs.
        label_map: {"red_block": 4, "blue_block": 5, ...}
        Built from preset objects list + world_artifacts.object_ids
        in spawn order.
        """
        self._label_map = label_map
        self._id_to_label = {v: k for k, v in label_map.items()}

    def mark_object_moved(self, object_id: int) -> None:
        """Call after an object is successfully moved to bin/tray."""
        self._moved_object_ids.add(object_id)

    def reset_moved_objects(self) -> None:
        """Call at session start or preset reset."""
        self._moved_object_ids.clear()

    def set_moved_objects(self, object_ids: set) -> None:
        """Replace moved-object tracking from the interaction session."""
        self._moved_object_ids = set(object_ids)

    @staticmethod
    def _is_valid_position(pos) -> bool:
        """Check if a PyBullet position is physically sane."""
        import math

        return all(
            not math.isnan(x) and not math.isinf(x) and abs(x) < 5.0
            for x in pos
        )

    def plan(self, goal: str, scene_summary: str) -> TaskGraph:
        del scene_summary
        goal_lower = goal.lower()
        graph_id = str(uuid.uuid4())[:8]

        object_label, destination = self._parse_object_goal(goal_lower)
        take_out_words = [
            "take out",
            "from bin",
            "out of bin",
            "bring back",
            "remove from bin",
        ]

        if any(w in goal_lower for w in take_out_words):
            nodes = self._take_from_bin_nodes(destination="table")
        elif object_label:
            nodes = self._specific_object_nodes(object_label, destination)
        elif any(w in goal_lower for w in ("clean", "clear", "tidy")):
            nodes = self._clean_table_nodes()
        elif "home" in goal_lower:
            nodes = self._home_nodes()
        else:
            nodes = self._safe_default_nodes(goal)

        return TaskGraph(
            graph_id=graph_id,
            goal=goal,
            nodes=nodes,
            created_at=time.time(),
            plan_confidence=0.6,
            interpretation_note="Heuristic plan",
        )

    def _parse_object_goal(self, goal_lower: str) -> tuple[Optional[str], str]:
        """
        Parse goal for specific object reference and destination.
        Returns (object_label_or_None, destination).

        Examples:
          "move the red block to the bin" -> ("red_block", "bin")
          "put the tool in the tray" -> ("tool", "tray")
          "move blue block to tray" -> ("blue_block", "tray")
        """
        destination = "bin"
        if "tray" in goal_lower:
            destination = "tray"

        for label in self._label_map.keys():
            variants = [
                label,
                label.replace("_", " "),
                label.split("_")[0],
            ]
            if any(v in goal_lower for v in variants):
                return label, destination

        return None, destination

    def _clean_table_nodes(self) -> list[TaskNode]:
        cycles = []
        available = self._get_available_objects()

        if not available:
            available = [None]

        prev_release_id = None
        for i, obj_info in enumerate(available):
            reach_id = f"reach_{i}"
            grasp_id = f"grasp_{i}"
            move_id = f"move_{i}"
            release_id = f"release_{i}"

            deps_reach = [prev_release_id] if prev_release_id else []

            reach_params = obj_info if obj_info else {"target": "nearest_object"}
            grasp_params = {
                k: reach_params[k]
                for k in ("target_xyz", "object_id")
                if isinstance(reach_params, dict) and k in reach_params
            }
            bin_params = self._resolve_bin()

            cycles.extend(
                [
                    TaskNode(
                        node_id=reach_id,
                        action_type="reach",
                        agent_id="arm",
                        parameters=reach_params,
                        depends_on=deps_reach,
                        confirmation_policy=ConfirmationPolicy.CHECKPOINT,
                        uncertainty=UncertaintySignals.unknown(),
                    ),
                    TaskNode(
                        node_id=grasp_id,
                        action_type="grasp",
                        agent_id="arm",
                        parameters=grasp_params,
                        depends_on=[reach_id],
                        confirmation_policy=ConfirmationPolicy.NEVER,
                        uncertainty=UncertaintySignals.unknown(),
                    ),
                    TaskNode(
                        node_id=move_id,
                        action_type="move",
                        agent_id="arm",
                        parameters=bin_params,
                        depends_on=[grasp_id],
                        confirmation_policy=ConfirmationPolicy.NEVER,
                        uncertainty=UncertaintySignals.unknown(),
                    ),
                    TaskNode(
                        node_id=release_id,
                        action_type="release",
                        agent_id="arm",
                        parameters={},
                        depends_on=[move_id],
                        confirmation_policy=ConfirmationPolicy.NEVER,
                        uncertainty=UncertaintySignals.unknown(),
                    ),
                ]
            )
            prev_release_id = release_id

        return cycles

    def _get_available_objects(self) -> list[dict]:
        """
        Returns list of grounded parameter dicts for each object
        currently on the table (not in bin zone).
        """
        if self._world_artifacts is None or self._sim is None:
            return []

        import pybullet as p

        bin_center = self._world_artifacts.bin_zone_center
        bin_radius = self._world_artifacts.bin_zone_radius

        available = []
        for obj_id in self._world_artifacts.object_ids:
            if obj_id in self._moved_object_ids:
                continue
            try:
                pos, _ = p.getBasePositionAndOrientation(
                    obj_id, physicsClientId=self._sim.client
                )
                if not self._is_valid_position(pos):
                    continue
                dx = pos[0] - bin_center[0]
                dy = pos[1] - bin_center[1]
                in_bin = (dx**2 + dy**2) ** 0.5 < bin_radius * 1.2
                if in_bin:
                    continue
                available.append(
                    {
                        "target": f"object_{obj_id}",
                        "target_xyz": list(pos),
                        "object_id": obj_id,
                    }
                )
            except Exception:
                continue
        return available

    def _get_bin_objects(self) -> list[dict]:
        """Returns grounded params for objects currently in bin."""
        if self._world_artifacts is None or self._sim is None:
            return []

        import pybullet as p

        bin_center = self._world_artifacts.bin_zone_center
        bin_radius = self._world_artifacts.bin_zone_radius
        in_bin = []
        for obj_id in self._world_artifacts.object_ids:
            try:
                pos, _ = p.getBasePositionAndOrientation(
                    obj_id, physicsClientId=self._sim.client
                )
                dx = pos[0] - bin_center[0]
                dy = pos[1] - bin_center[1]
                if (dx**2 + dy**2) ** 0.5 < bin_radius * 1.5:
                    in_bin.append(
                        {
                            "target": f"object_{obj_id}",
                            "target_xyz": list(pos),
                            "object_id": obj_id,
                        }
                    )
            except Exception:
                continue
        return in_bin

    def _resolve_nearest_object(self) -> dict:
        if self._world_artifacts is None or self._sim is None:
            return {
                "target": "nearest_object",
                "target_xyz": [0.2, 0.0, 0.65],
            }

        try:
            import pybullet as p
        except ImportError:
            logger.warning("PyBullet unavailable; using fallback nearest object target.")
            return {
                "target": "nearest_object",
                "target_xyz": [0.2, 0.0, 0.65],
            }

        try:
            bin_center = self._world_artifacts.bin_zone_center
            bin_radius = self._world_artifacts.bin_zone_radius
            object_ids = self._world_artifacts.object_ids
            client = self._sim.client
        except AttributeError:
            logger.warning("Could not read world artifacts; using fallback nearest object.")
            return {
                "target": "nearest_object",
                "target_xyz": [0.2, 0.0, 0.65],
            }

        best_id = None
        best_pos = None
        best_dist = float("inf")

        for obj_id in object_ids:
            if obj_id in self._moved_object_ids:
                continue
            try:
                pos, _ = p.getBasePositionAndOrientation(
                    obj_id,
                    physicsClientId=client,
                )
            except Exception:
                continue

            dx = pos[0] - bin_center[0]
            dy = pos[1] - bin_center[1]
            dist_to_bin = (dx**2 + dy**2) ** 0.5
            if dist_to_bin < bin_radius * 3.0:
                continue

            dist = (pos[0] ** 2 + pos[1] ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_id = obj_id
                best_pos = pos

        if best_id is None or best_pos is None:
            logger.warning("No table object found; using fallback nearest object target.")
            return {
                "target": "nearest_object",
                "target_xyz": [0.2, 0.0, 0.65],
            }

        return {
            "target": f"object_{best_id}",
            "target_xyz": list(best_pos),
            "object_id": best_id,
        }

    def _resolve_object_by_label(self, label: str) -> dict:
        """
        Resolve a semantic label to grounded coordinates.

        Returns a dict with a status field:
          - "resolved": object found, has valid target_xyz
          - "already_moved": object exists but was already handled
          - "not_present": no object matches this label in the scene
          - "unreachable": object matched but has an invalid position
        """
        try:
            import pybullet as p
        except ImportError:
            return {
                "status": "not_present",
                "target": None,
                "object_id": None,
                "target_xyz": None,
                "label": label,
            }

        body_id = self._label_map.get(label)
        if body_id is None:
            label_tokens = set(label.replace("_", " ").lower().split())
            for k, v in self._label_map.items():
                k_tokens = set(k.replace("_", " ").lower().split())
                if label_tokens and label_tokens.issubset(k_tokens):
                    body_id = v
                    break
                if k_tokens and k_tokens.issubset(label_tokens):
                    body_id = v
                    break

        if body_id is None:
            return {
                "status": "not_present",
                "target": None,
                "object_id": None,
                "target_xyz": None,
                "label": label,
            }

        if body_id in self._moved_object_ids:
            return {
                "status": "already_moved",
                "target": "already_moved",
                "object_id": body_id,
                "target_xyz": [0.0, 0.0, 0.65],
                "label": label,
            }

        try:
            pos, _ = p.getBasePositionAndOrientation(
                body_id, physicsClientId=self._sim.client
            )
            valid = self._is_valid_position(pos)
            if not valid:
                return {
                    "status": "unreachable",
                    "target": None,
                    "object_id": body_id,
                    "target_xyz": None,
                    "label": label,
                }

            return {
                "status": "resolved",
                "target": f"object_{body_id}",
                "target_xyz": list(pos),
                "object_id": body_id,
                "label": label,
            }
        except Exception:
            return {
                "status": "unreachable",
                "target": None,
                "object_id": body_id,
                "target_xyz": None,
                "label": label,
            }

    def _resolve_bin(self) -> dict:
        if self._world_artifacts is None:
            return {"target": "bin"}
        try:
            center = self._world_artifacts.bin_zone_center
            # Release above bin walls so objects fall into the physical bin.
            return {
                "target": "bin",
                "target_xyz": list(center),
                "destination_xyz": list(center),
            }
        except AttributeError:
            return {"target": "bin"}

    def _resolve_tray(self) -> dict:
        """Resolve tray destination coordinates."""
        tray_pos = [0.0, -0.18, 0.68]
        return {
            "target": "tray",
            "target_xyz": tray_pos,
            "destination_xyz": tray_pos,
        }

    def _specific_object_nodes(
        self,
        object_label: str,
        destination: str = "bin",
    ) -> list[TaskNode]:
        """One reach-grasp-move-release for a specific named object."""
        reach_params = self._resolve_object_by_label(object_label)
        if reach_params.get("status") != "resolved":
            return self._safe_default_nodes(
                f"{reach_params.get('label', object_label)} "
                f"{reach_params.get('status', 'not_present')}"
            )
        move_params = (
            self._resolve_bin()
            if destination == "bin"
            else self._resolve_tray()
        )
        grasp_params = {
            k: reach_params[k]
            for k in ("target_xyz", "object_id")
            if isinstance(reach_params, dict) and k in reach_params
        }
        return [
            TaskNode(
                node_id="reach_0",
                action_type="reach",
                agent_id="arm",
                parameters=reach_params,
                depends_on=[],
                confirmation_policy=ConfirmationPolicy.CHECKPOINT,
                uncertainty=UncertaintySignals.unknown(),
            ),
            TaskNode(
                node_id="grasp_0",
                action_type="grasp",
                agent_id="arm",
                parameters=grasp_params,
                depends_on=["reach_0"],
                confirmation_policy=ConfirmationPolicy.NEVER,
                uncertainty=UncertaintySignals.unknown(),
            ),
            TaskNode(
                node_id="move_0",
                action_type="move",
                agent_id="arm",
                parameters=move_params,
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

    def _take_from_bin_nodes(
        self,
        destination: str = "table",
    ) -> list[TaskNode]:
        """Move nearest bin object to table center or tray."""
        bin_objects = self._get_bin_objects()
        if not bin_objects:
            return self._safe_default_nodes("take from bin")

        obj = bin_objects[0]
        grasp_params = {
            k: obj[k]
            for k in ("target_xyz", "object_id")
            if isinstance(obj, dict) and k in obj
        }
        if destination == "tray":
            dest_params = self._resolve_tray()
        else:
            dest_params = {
                "target": "table",
                "target_xyz": [0.0, 0.0, 0.63],
                "destination_xyz": [0.0, 0.0, 0.63],
            }

        return [
            TaskNode(
                node_id="reach_0",
                action_type="reach",
                agent_id="arm",
                parameters=obj,
                depends_on=[],
                confirmation_policy=ConfirmationPolicy.CHECKPOINT,
                uncertainty=UncertaintySignals.unknown(),
            ),
            TaskNode(
                node_id="grasp_0",
                action_type="grasp",
                agent_id="arm",
                parameters=grasp_params,
                depends_on=["reach_0"],
                confirmation_policy=ConfirmationPolicy.NEVER,
                uncertainty=UncertaintySignals.unknown(),
            ),
            TaskNode(
                node_id="move_0",
                action_type="move",
                agent_id="arm",
                parameters=dest_params,
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
        reach_params = self._resolve_nearest_object()
        reach_params["goal_context"] = goal
        return [
            TaskNode(
                node_id="reach_default",
                action_type="reach",
                agent_id="arm",
                parameters=reach_params,
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
