"""
ProposalEngine - translates TaskGraph into human-readable proposals.

The engine formats a plan for review by the existing Phase 2 proposal path.
It does not decide whether the human confirms and does not execute anything.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from src.task_graph.types import ConfirmationPolicy, TaskGraph


logger = logging.getLogger(__name__)

UNCERTAINTY_WARN_THRESHOLD = 0.5
UNCERTAINTY_CHECKPOINT_THRESHOLD = 0.7
UNCERTAINTY_ABORT_THRESHOLD = 0.85


@dataclass(frozen=True)
class ExecutionProposal:
    """Human-facing proposal generated from a TaskGraph."""

    proposal_id: str
    summary: str
    step_count: int
    estimated_duration_s: float
    requires_confirmation: bool
    warning: Optional[str]
    uncertainty_level: str
    graph_id: str
    plan_source: str


@dataclass(frozen=True)
class ProposalAssessment:
    """Internal risk assessment that drives proposal formatting."""

    max_uncertainty: float
    high_uncertainty_nodes: list[str]
    irreversible_node_ids: list[str]
    should_abort: bool
    checkpoint_required: bool


class ProposalEngine:
    """Translates TaskGraph into ExecutionProposal."""

    def assess(self, graph: TaskGraph) -> ProposalAssessment:
        """Analyze uncertainty, checkpoint requirements, and irreversible steps."""
        uncertainties = [node.uncertainty.combined for node in graph.nodes]
        max_uncertainty = max(uncertainties) if uncertainties else 0.0

        high_uncertainty_nodes = [
            node.node_id
            for node in graph.nodes
            if node.uncertainty.combined > UNCERTAINTY_WARN_THRESHOLD
        ]
        irreversible_node_ids = [
            node.node_id
            for node in graph.nodes
            if node.confirmation_policy == ConfirmationPolicy.ALWAYS
        ]

        should_abort = max_uncertainty > UNCERTAINTY_ABORT_THRESHOLD
        checkpoint_required = (
            max_uncertainty > UNCERTAINTY_CHECKPOINT_THRESHOLD
            or bool(irreversible_node_ids)
            or any(
                node.confirmation_policy != ConfirmationPolicy.NEVER
                for node in graph.nodes
            )
        )

        return ProposalAssessment(
            max_uncertainty=max_uncertainty,
            high_uncertainty_nodes=high_uncertainty_nodes,
            irreversible_node_ids=irreversible_node_ids,
            should_abort=should_abort,
            checkpoint_required=checkpoint_required,
        )

    def propose(
        self,
        graph: TaskGraph,
        plan_source: str,
        proposal_id: str,
    ) -> ExecutionProposal:
        """Generate a human-facing proposal from a valid TaskGraph."""
        assessment = self.assess(graph)
        summary = self._build_summary(graph, assessment)

        return ExecutionProposal(
            proposal_id=proposal_id,
            summary=summary,
            step_count=len(graph.nodes),
            estimated_duration_s=self._estimate_duration(graph),
            requires_confirmation=assessment.checkpoint_required,
            warning=self._build_warning(assessment, plan_source),
            uncertainty_level=self._classify_uncertainty(assessment.max_uncertainty),
            graph_id=graph.graph_id,
            plan_source=plan_source,
        )

    @staticmethod
    def _build_summary(graph: TaskGraph, assessment: ProposalAssessment) -> str:
        n_steps = len(graph.nodes)
        action_types = [node.action_type for node in graph.nodes]
        unique_actions = list(dict.fromkeys(action_types))

        goal_lower = graph.goal.lower()
        if "clean" in goal_lower or "clear" in goal_lower:
            verb = "Clean the table"
        elif "home" in goal_lower:
            verb = "Move arm to home position"
        else:
            verb = f"Execute: {graph.goal[:60]}"

        actions = " -> ".join(unique_actions[:4])
        if len(unique_actions) > 4:
            actions += " -> ..."

        summary = f"{verb} - {n_steps} step{'s' if n_steps != 1 else ''} ({actions})"
        if assessment.should_abort:
            return f"WARNING CANNOT EXECUTE: {summary}"
        if assessment.high_uncertainty_nodes:
            return f"WARNING {summary}"
        return summary

    @staticmethod
    def _build_warning(
        assessment: ProposalAssessment,
        plan_source: str,
    ) -> Optional[str]:
        parts: list[str] = []
        if assessment.should_abort:
            parts.append(
                "Uncertainty too high to execute safely "
                f"({assessment.max_uncertainty:.0%}). Human intervention required."
            )
        elif assessment.high_uncertainty_nodes:
            parts.append(
                f"High uncertainty on {len(assessment.high_uncertainty_nodes)} "
                f"step(s): {', '.join(assessment.high_uncertainty_nodes[:3])}"
            )

        if assessment.irreversible_node_ids:
            parts.append(
                f"{len(assessment.irreversible_node_ids)} irreversible step(s) - "
                "cannot be undone after execution."
            )
        if plan_source == "heuristic":
            parts.append("Plan generated by heuristic (LLM unavailable).")

        return " | ".join(parts) if parts else None

    @staticmethod
    def _classify_uncertainty(max_uncertainty: float) -> str:
        if max_uncertainty < UNCERTAINTY_WARN_THRESHOLD:
            return "low"
        if max_uncertainty < UNCERTAINTY_CHECKPOINT_THRESHOLD:
            return "medium"
        if max_uncertainty < UNCERTAINTY_ABORT_THRESHOLD:
            return "high"
        return "abort"

    @staticmethod
    def _estimate_duration(graph: TaskGraph) -> float:
        return len(graph.nodes) * 2.0
