"""
CheckpointPlanner - segments a TaskGraph into checkpoint groups.

One segment maps to one human confirmation and one ScopedExecutionToken.
Nodes within a segment can execute autonomously while the token remains valid.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from src.task_graph.types import ConfirmationPolicy, TaskGraph, TaskNode


MAX_SILENT_NODES = 8
CHECKPOINT_THRESHOLD = 0.7


@dataclass
class CheckpointSegment:
    """A group of nodes covered by one scoped token."""

    segment_id: str
    node_ids: list[str]
    requires_confirmation: bool
    summary: str


@dataclass(frozen=True)
class ScopedExecutionToken:
    """
    Authorizes execution of a specific segment of nodes.

    In 3C this is the data model for checkpoint-scoped authorization. It does
    not replace Phase 2 safety checks; each node still checks token coverage and
    validity before execution.
    """

    token_id: str
    segment_id: str
    authorized_node_ids: frozenset[str]
    issued_at: float
    expires_at: float
    segment_hash: str
    _revoked: bool = False

    def is_valid(self, current_time: Optional[float] = None) -> bool:
        now = current_time if current_time is not None else time.monotonic()
        return not self._revoked and now < self.expires_at

    def covers(self, node_id: str) -> bool:
        return node_id in self.authorized_node_ids

    @classmethod
    def issue(
        cls,
        segment: CheckpointSegment,
        node_definitions: list[dict],
        validity_s: float = 120.0,
    ) -> "ScopedExecutionToken":
        """Issue a new scoped token for a segment."""
        now = time.monotonic()
        segment_hash = hashlib.sha256(
            json.dumps(node_definitions, sort_keys=True).encode()
        ).hexdigest()[:16]
        return cls(
            token_id=str(uuid.uuid4())[:8],
            segment_id=segment.segment_id,
            authorized_node_ids=frozenset(segment.node_ids),
            issued_at=now,
            expires_at=now + validity_s,
            segment_hash=segment_hash,
        )


class CheckpointPlanner:
    """Segments a TaskGraph into checkpoint groups."""

    def segment(self, graph: TaskGraph) -> list[CheckpointSegment]:
        """Return checkpoint segments in topological order."""
        if not graph.nodes:
            return []

        segments: list[CheckpointSegment] = []
        current_group: list[TaskNode] = []
        silent_count = 0

        for node in self._topological_order(graph):
            force_break = (
                node.confirmation_policy == ConfirmationPolicy.ALWAYS
                or node.uncertainty.combined > CHECKPOINT_THRESHOLD
                or silent_count >= MAX_SILENT_NODES
            )

            if force_break and current_group:
                segments.append(self._make_segment(current_group))
                current_group = []
                silent_count = 0

            current_group.append(node)
            if node.confirmation_policy == ConfirmationPolicy.NEVER:
                silent_count += 1
            else:
                silent_count = 0

        if current_group:
            segments.append(self._make_segment(current_group))

        if segments:
            first = segments[0]
            segments[0] = CheckpointSegment(
                segment_id=first.segment_id,
                node_ids=first.node_ids,
                requires_confirmation=True,
                summary=first.summary,
            )

        return segments

    @staticmethod
    def _make_segment(nodes: list[TaskNode]) -> CheckpointSegment:
        action_types = list(dict.fromkeys(node.action_type for node in nodes))
        summary = f"{len(nodes)} step(s): {' -> '.join(action_types[:4])}"
        if len(action_types) > 4:
            summary += " -> ..."

        return CheckpointSegment(
            segment_id=str(uuid.uuid4())[:8],
            node_ids=[node.node_id for node in nodes],
            requires_confirmation=any(
                node.confirmation_policy != ConfirmationPolicy.NEVER
                for node in nodes
            ),
            summary=summary,
        )

    @staticmethod
    def _topological_order(graph: TaskGraph) -> list[TaskNode]:
        """Simple Kahn topological sort."""
        nodes_by_id = {node.node_id: node for node in graph.nodes}
        in_degree = {node.node_id: len(node.depends_on) for node in graph.nodes}
        adjacency: dict[str, list[str]] = {node.node_id: [] for node in graph.nodes}

        for node in graph.nodes:
            for dep in node.depends_on:
                if dep in adjacency:
                    adjacency[dep].append(node.node_id)

        queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
        result: list[TaskNode] = []

        while queue:
            queue.sort(key=lambda node_id: CheckpointPlanner._object_chain_sort_key(node_id))
            node_id = queue.pop(0)
            result.append(nodes_by_id[node_id])
            for neighbor in adjacency[node_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return result

    @staticmethod
    def _object_chain_sort_key(node_id: str) -> tuple[int, int, int]:
        """Prefer reach_i -> grasp_i -> move_i -> release_i before reach_{i+1}."""
        phase_ranks = {
            "reach": 0,
            "grasp": 1,
            "move": 2,
            "release": 3,
        }
        try:
            phase, suffix = node_id.rsplit("_", 1)
        except ValueError:
            return (1, 0, 0)
        if phase not in phase_ranks or not suffix.isdigit():
            return (1, 0, 0)
        return (0, int(suffix), phase_ranks[phase])
