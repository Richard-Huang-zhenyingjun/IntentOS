"""
AmbiguityResolver - handles goals with multiple valid interpretations.

When planner confidence is low, the resolver can generate up to three
alternative TaskGraphs and select one automatically or via keyboard-only human
selection. EEG remains confirm/cancel only.

This module is optional. The planner works without it.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from src.task_graph.types import TaskGraph
from src.task_graph.validator import validate

logger = logging.getLogger(__name__)

AMBIGUITY_THRESHOLD = 0.70
AUTO_SELECT_THRESHOLD = 0.85
MAX_INTERPRETATIONS = 3


@dataclass(frozen=True)
class Interpretation:
    """One candidate interpretation of a goal."""

    interpretation_id: str
    description: str
    confidence: float
    graph: Optional[TaskGraph]
    valid: bool
    key: str


@dataclass
class AmbiguityResolution:
    """Result of ambiguity resolution."""

    selected_graph: TaskGraph
    selected_interpretation: str
    auto_selected: bool
    interpretations_shown: int


class AmbiguityResolver:
    """
    Resolves goal ambiguity by selecting among alternative valid plans.
    Selection uses keyboard callbacks or console input, never EEG.
    """

    def __init__(self, planner, agent_registry):
        self._planner = planner
        self._registry = agent_registry

    def resolve(
        self,
        goal: str,
        scene_summary: str,
        selection_callback=None,
    ) -> Optional[AmbiguityResolution]:
        """
        Generate alternative interpretations and resolve ambiguity.

        selection_callback: callable(options: list[Interpretation]) -> str
            Returns the selected option key: "1", "2", or "3".
        """
        interpretations = self._generate_interpretations(goal, scene_summary)
        if not interpretations:
            logger.warning("AmbiguityResolver: no valid interpretations for %r", goal)
            return None

        interpretations = sorted(
            interpretations,
            key=lambda interpretation: interpretation.confidence,
            reverse=True,
        )
        valid = [interpretation for interpretation in interpretations if interpretation.valid]
        if not valid:
            return None

        top = valid[0]
        if top.confidence >= AUTO_SELECT_THRESHOLD:
            gap = top.confidence - (valid[1].confidence if len(valid) > 1 else 0.0)
            if gap >= 0.2:
                logger.info(
                    "Auto-selected interpretation: %r (confidence=%.2f)",
                    top.description,
                    top.confidence,
                )
                return AmbiguityResolution(
                    selected_graph=top.graph,
                    selected_interpretation=top.description,
                    auto_selected=True,
                    interpretations_shown=0,
                )

        options = valid[:MAX_INTERPRETATIONS]
        logger.info(
            "Ambiguity detected for %r - presenting %d options to human",
            goal,
            len(options),
        )

        if selection_callback is not None:
            selected_key = selection_callback(options)
        else:
            selected_key = self._console_selection(options)

        selected = next(
            (interpretation for interpretation in options if interpretation.key == selected_key),
            options[0],
        )

        return AmbiguityResolution(
            selected_graph=selected.graph,
            selected_interpretation=selected.description,
            auto_selected=False,
            interpretations_shown=len(options),
        )

    def _generate_interpretations(
        self,
        goal: str,
        scene_summary: str,
    ) -> list[Interpretation]:
        """
        Generate candidate interpretations.

        For now this wraps the existing planner twice: literal and conservative.
        A future LLM multi-interpretation prompt can replace this internal method
        without changing the resolver interface.
        """
        registered_ids = set(self._registry.all_ids())
        interpretations = []
        keys = ["1", "2", "3"]

        result_a = self._planner.plan(goal, scene_summary)
        graph_a = result_a.graph
        interp_a = Interpretation(
            interpretation_id=str(uuid.uuid4())[:8],
            description=f"Literal: {goal}",
            confidence=graph_a.plan_confidence if graph_a else 0.0,
            graph=graph_a,
            valid=bool(graph_a and not validate(graph_a, registered_ids)),
            key=keys[0],
        )
        interpretations.append(interp_a)

        conservative_goal = f"safely {goal}"
        result_b = self._planner.plan(conservative_goal, scene_summary)
        graph_b = result_b.graph
        if graph_b is not None and (graph_a is None or graph_b.graph_id != graph_a.graph_id):
            interp_b = Interpretation(
                interpretation_id=str(uuid.uuid4())[:8],
                description=f"Conservative: {conservative_goal}",
                confidence=max(0.0, graph_b.plan_confidence - 0.1),
                graph=graph_b,
                valid=bool(graph_b and not validate(graph_b, registered_ids)),
                key=keys[1],
            )
            interpretations.append(interp_b)

        return [interpretation for interpretation in interpretations if interpretation.valid]

    @staticmethod
    def _console_selection(options: list[Interpretation]) -> str:
        """Console fallback for selection, used in demos."""
        print("\nGoal is ambiguous. Please select an interpretation:\n")
        for option in options:
            print(
                f"  [{option.key}] {option.description} "
                f"(confidence: {option.confidence:.0%})"
            )
        print()
        while True:
            choice = input("Enter choice (or press Enter for option 1): ").strip()
            if not choice:
                return options[0].key
            if choice in [option.key for option in options]:
                return choice
            print(f"Invalid choice. Enter one of: {[option.key for option in options]}")
