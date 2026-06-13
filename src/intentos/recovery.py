"""
RecoveryEngine - classifies and handles node execution failures.

Recovery never bypasses authorization. Any replan must flow back through a new
proposal, checkpoint confirmation, and scoped token.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from src.task_graph.types import TaskGraph, TaskNode


logger = logging.getLogger(__name__)

MAX_RETRIES_PER_NODE = 5
MAX_RECOVERY_ATTEMPTS_PER_PLAN = 3


class FailureClass(Enum):
    TRANSIENT = auto()
    REPLANNING = auto()
    SKIP = auto()
    ESCALATION = auto()


@dataclass
class RecoveryDecision:
    failure_class: FailureClass
    node_id: str
    retry_count: int
    message: str
    replan_goal: Optional[str] = None
    escalation_reason: Optional[str] = None


class RecoveryEngine:
    """Classifies node failures and returns recovery decisions."""

    def __init__(self):
        self._retry_counts: dict[str, int] = {}
        self._recovery_attempts: int = 0

    def classify(
        self,
        node: TaskNode,
        graph: TaskGraph,
        failure_reason: Optional[str],
    ) -> RecoveryDecision:
        """Classify a node failure and issue a recovery decision."""
        del graph
        node_id = node.node_id
        retry_count = self._retry_counts.get(node_id, 0)
        reason = (failure_reason or "").lower()

        safety_keywords = {
            "collision",
            "safety",
            "emergency",
            "hardware",
            "not registered",
            "agent missing",
            "missing agent",
        }
        if any(keyword in reason for keyword in safety_keywords):
            return RecoveryDecision(
                failure_class=FailureClass.ESCALATION,
                node_id=node_id,
                retry_count=retry_count,
                message=f"Safety-related failure: {failure_reason}",
                escalation_reason=failure_reason,
            )

        recoverable_keywords = {
            "grasp_failed",
            "grasp_no_object",
            "unreachable",
            "timeout",
            "not found",
            "missing",
            "moved",
            "move_invalid_pose",
            "move_not_arrived",
            "ik_out_of_limits",
            "occluded",
            "invisible",
        }
        if any(keyword in reason for keyword in recoverable_keywords):
            if retry_count < MAX_RETRIES_PER_NODE - 1:
                self._retry_counts[node_id] = retry_count + 1
                return RecoveryDecision(
                    failure_class=FailureClass.TRANSIENT,
                    node_id=node_id,
                    retry_count=retry_count + 1,
                    message=(
                        f"Recoverable failure on {node.action_type}: "
                        f"{failure_reason}. Retry {retry_count + 1}/"
                        f"{MAX_RETRIES_PER_NODE}."
                    ),
                )

            return RecoveryDecision(
                failure_class=FailureClass.SKIP,
                node_id=node_id,
                retry_count=MAX_RETRIES_PER_NODE,
                message=(
                    f"Recoverable failure on {node.action_type} exhausted "
                    "retries. Skipping this object and continuing."
                ),
            )

        if self._recovery_attempts >= MAX_RECOVERY_ATTEMPTS_PER_PLAN:
            return RecoveryDecision(
                failure_class=FailureClass.ESCALATION,
                node_id=node_id,
                retry_count=retry_count,
                message=(
                    f"Too many recovery attempts ({self._recovery_attempts}). "
                    "Human intervention needed."
                ),
                escalation_reason=(
                    f"Exceeded {MAX_RECOVERY_ATTEMPTS_PER_PLAN} recovery attempts"
                ),
            )

        if retry_count < MAX_RETRIES_PER_NODE - 1:
            self._retry_counts[node_id] = retry_count + 1
            return RecoveryDecision(
                failure_class=FailureClass.TRANSIENT,
                node_id=node_id,
                retry_count=retry_count + 1,
                message=(
                    f"Transient failure on {node.action_type}. "
                    f"Retry {retry_count + 1}/{MAX_RETRIES_PER_NODE}."
                ),
            )

        object_keywords = {"not found", "missing", "moved", "occluded", "invisible"}
        if any(keyword in reason for keyword in object_keywords):
            self._recovery_attempts += 1
            target = node.parameters.get("target", "object")
            replan_goal = f"retry {node.action_type} for {target}"
            return RecoveryDecision(
                failure_class=FailureClass.REPLANNING,
                node_id=node_id,
                retry_count=retry_count,
                message=f"Object-related failure. Replanning subtask: {replan_goal}",
                replan_goal=replan_goal,
            )

        self._recovery_attempts += 1
        return RecoveryDecision(
            failure_class=FailureClass.ESCALATION,
            node_id=node_id,
            retry_count=retry_count,
            message=f"Node {node_id} failed after {retry_count} retries. Human intervention needed.",
            escalation_reason=failure_reason,
        )

    def reset_node(self, node_id: str) -> None:
        """Reset retry count for a node after successful recovery."""
        self._retry_counts.pop(node_id, None)

    def reset_plan(self) -> None:
        """Reset all state for a new plan."""
        self._retry_counts.clear()
        self._recovery_attempts = 0
