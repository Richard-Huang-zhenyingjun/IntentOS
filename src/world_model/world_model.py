"""
WorldModel - heuristic risk estimator for IntentOS.

Annotates each TaskNode in a TaskGraph with a simulation_risk score (0.0-1.0).
This module raises flags for the human-facing proposal path; it does not make
execution decisions and does not claim physics ground truth.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from math import sqrt
from typing import Optional

from src.task_graph.types import TaskGraph, TaskNode, UncertaintySignals


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorldModelConfig:
    workspace_radius_m: float = 0.8
    workspace_height_min_m: float = 0.0
    workspace_height_max_m: float = 0.6
    spatial_conflict_penalty: float = 0.4
    unreachable_penalty: float = 0.6
    invisible_penalty: float = 0.5
    irreversible_actions: frozenset[str] = frozenset({"release"})


@dataclass
class NodeRisk:
    """Risk assessment for a single TaskNode."""

    node_id: str
    simulation_risk: float
    spatial_conflict: bool
    reachable: bool
    object_visible: bool
    reversible: bool
    notes: list[str]


@dataclass
class WorldAssessment:
    """Risk assessment for the full TaskGraph."""

    per_node: dict[str, NodeRisk]
    overall_risk: float
    collision_warnings: list[str]
    unreachable_nodes: list[str]


class WorldModel:
    """
    Heuristic world model. Call assess(graph, world_state) before execution.

    world_state is a dict from the vision/scene system. Expected keys:
      objects: list of {"id": str, "position": [x, y, z], "visible": bool}
      arm_base_position: [x, y, z] (accepted for future use)
    """

    def __init__(
        self,
        cfg: WorldModelConfig,
        arm_controller=None,
    ):
        self._cfg = cfg
        self._arm = arm_controller

    def assess(
        self,
        graph: TaskGraph,
        world_state: Optional[dict] = None,
    ) -> WorldAssessment:
        """Assess all nodes in the graph and return risk metadata."""
        ws = world_state or {}
        objects = {
            str(obj.get("id")): obj
            for obj in ws.get("objects", [])
            if isinstance(obj, dict) and obj.get("id") is not None
        }

        node_risks: dict[str, NodeRisk] = {}
        zone_usage: dict[str, list[str]] = {}

        for node in graph.nodes:
            risk = self._assess_node(node, objects, zone_usage)
            node_risks[node.node_id] = risk

        overall = max((risk.simulation_risk for risk in node_risks.values()), default=0.0)
        collision_warnings = [
            f"Nodes {', '.join(node_ids)} share zone {zone}"
            for zone, node_ids in zone_usage.items()
            if len(node_ids) > 1
        ]
        unreachable = [
            node_id
            for node_id, risk in node_risks.items()
            if not risk.reachable
        ]

        return WorldAssessment(
            per_node=node_risks,
            overall_risk=overall,
            collision_warnings=collision_warnings,
            unreachable_nodes=unreachable,
        )

    def annotate_graph(
        self,
        graph: TaskGraph,
        world_state: Optional[dict] = None,
    ) -> None:
        """Annotate each node's uncertainty.simulation_risk in place."""
        assessment = self.assess(graph, world_state)
        for node in graph.nodes:
            risk_info = assessment.per_node.get(node.node_id)
            if risk_info is None:
                continue
            old_uncertainty = node.uncertainty
            node.uncertainty = UncertaintySignals(
                perception_confidence=old_uncertainty.perception_confidence,
                execution_history_rate=old_uncertainty.execution_history_rate,
                simulation_risk=max(old_uncertainty.simulation_risk, risk_info.simulation_risk),
            )

    def _assess_node(
        self,
        node: TaskNode,
        objects: dict,
        zone_usage: dict[str, list[str]],
    ) -> NodeRisk:
        risk = 0.0
        notes: list[str] = []

        target = node.parameters.get("target")
        obj = objects.get(str(target)) if target is not None else None

        reachable = True
        if obj is not None and "position" in obj:
            reachable = self._in_workspace(obj["position"])
            if not reachable:
                risk += self._cfg.unreachable_penalty
                notes.append(f"Object {target!r} outside workspace")

        visible = True
        if obj is not None:
            visible = bool(obj.get("visible", True))
            if not visible:
                risk += self._cfg.invisible_penalty
                notes.append(f"Object {target!r} not visible")

        zone = node.resource_claim.spatial_zone if node.resource_claim else None
        spatial_conflict = False
        if zone:
            zone_usage.setdefault(zone, []).append(node.node_id)
            spatial_conflict = len(zone_usage[zone]) > 1
            if spatial_conflict:
                risk += self._cfg.spatial_conflict_penalty
                notes.append(f"Zone {zone!r} used by multiple nodes")

        reversible = node.action_type not in self._cfg.irreversible_actions
        if not reversible:
            notes.append(f"Action {node.action_type!r} is irreversible")

        return NodeRisk(
            node_id=node.node_id,
            simulation_risk=min(1.0, risk),
            spatial_conflict=spatial_conflict,
            reachable=reachable,
            object_visible=visible,
            reversible=reversible,
            notes=notes,
        )

    def _in_workspace(self, position: list) -> bool:
        """Heuristic radius and height workspace check."""
        if len(position) < 3:
            return True
        x, y, z = position[:3]
        radius = sqrt(float(x) ** 2 + float(y) ** 2)
        return (
            radius <= self._cfg.workspace_radius_m
            and self._cfg.workspace_height_min_m <= float(z) <= self._cfg.workspace_height_max_m
        )
