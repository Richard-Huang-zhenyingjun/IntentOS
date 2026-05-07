"""
ExecutionHistory - tracks per-action success rates.

Feeds the execution_history_rate component of UncertaintySignals.
Storage is a simple JSON file with one entry per (agent_id, action_type) pair.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path


logger = logging.getLogger(__name__)

DEFAULT_HISTORY_PATH = "data/execution_history.json"
DEFAULT_RATE = 0.7


class ExecutionHistory:
    """Tracks action success rates per agent with atomic JSON writes."""

    def __init__(self, path: str = DEFAULT_HISTORY_PATH):
        self._path = Path(path)
        self._data: dict = {}
        self._load()

    def record(self, agent_id: str, action_type: str, success: bool) -> None:
        """Record outcome of one action and save to disk immediately."""
        agent_data = self._data.setdefault(agent_id, {})
        entry = agent_data.setdefault(action_type, {"attempts": 0, "successes": 0})
        entry["attempts"] += 1
        if success:
            entry["successes"] += 1
        self._save()

    def success_rate(self, agent_id: str, action_type: str) -> float:
        """Return success rate, or DEFAULT_RATE if no history exists."""
        entry = self._data.get(agent_id, {}).get(action_type)
        if entry is None or entry.get("attempts", 0) == 0:
            return DEFAULT_RATE
        return float(entry.get("successes", 0)) / float(entry["attempts"])

    def annotate_graph(self, graph) -> None:
        """Update execution_history_rate for all nodes in graph."""
        for node in graph.nodes:
            rate = self.success_rate(node.agent_id, node.action_type)
            old_uncertainty = node.uncertainty
            node.uncertainty = type(old_uncertainty)(
                perception_confidence=old_uncertainty.perception_confidence,
                execution_history_rate=min(old_uncertainty.execution_history_rate, rate),
                simulation_risk=old_uncertainty.simulation_risk,
            )

    def summary(self) -> dict:
        """Return stored rates for logging and debugging."""
        result = {}
        for agent_id, actions in self._data.items():
            result[agent_id] = {
                action: {
                    "rate": round(values["successes"] / max(values["attempts"], 1), 3),
                    "attempts": values["attempts"],
                }
                for action, values in actions.items()
            }
        return result

    def _load(self) -> None:
        if not self._path.exists():
            self._data = {}
            return

        try:
            with open(self._path) as file:
                self._data = json.load(file)
            logger.info("Execution history loaded from %s", self._path)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not load execution history: %s", exc)
            self._data = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp.json")
        try:
            with open(tmp, "w") as file:
                json.dump(self._data, file, indent=2)
            tmp.replace(self._path)
        except OSError as exc:
            logger.error("Failed to save execution history: %s", exc)
