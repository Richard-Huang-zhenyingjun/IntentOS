"""
SystemMemory - cross-session persistent memory for IntentOS.

Tracks:
  - Per-object success rates by action type
  - Preferred strategies per goal type
  - Recent failure patterns

Persists to data/system_memory.json by default. This is structured execution
memory, not machine learning.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MEMORY_PATH = "data/system_memory.json"
DEFAULT_SUCCESS_RATE = 0.7
RECENCY_WINDOW = 20


class SystemMemory:
    """
    Persistent memory across sessions.
    All writes are atomic via tmp file replacement.
    """

    def __init__(self, path: str = MEMORY_PATH):
        self._path = Path(path)
        self._data: dict = {
            "objects": {},
            "goal_strategies": {},
            "failure_patterns": [],
            "session_count": 0,
            "last_updated": None,
        }
        self._load()

    def record_object_action(
        self,
        object_id: str,
        action_type: str,
        success: bool,
    ) -> None:
        """Record outcome of an action on a specific object."""
        objects = self._data.setdefault("objects", {})
        obj = objects.setdefault(object_id, {})
        history = obj.setdefault(action_type, [])
        history.append(int(success))
        if len(history) > RECENCY_WINDOW:
            history[:] = history[-RECENCY_WINDOW:]
        self._save()

    def object_success_rate(self, object_id: str, action_type: str) -> float:
        """Return success rate for object+action, or default if unknown."""
        history = (
            self._data.get("objects", {})
            .get(object_id, {})
            .get(action_type, [])
        )
        if not history:
            return DEFAULT_SUCCESS_RATE
        return sum(history) / len(history)

    def record_plan_outcome(
        self,
        goal_type: str,
        plan_source: str,
        success: bool,
    ) -> None:
        """Track which plan sources work best for goal types."""
        strategies = self._data.setdefault("goal_strategies", {})
        goal = strategies.setdefault(goal_type, {})
        entry = goal.setdefault(plan_source, {"successes": 0, "attempts": 0})
        entry["attempts"] += 1
        if success:
            entry["successes"] += 1
        self._save()

    def preferred_plan_source(self, goal_type: str) -> Optional[str]:
        """
        Return best known plan source for a goal type.
        Requires at least three attempts before trusting a source.
        """
        goal = self._data.get("goal_strategies", {}).get(goal_type, {})
        if not goal:
            return None
        rates = {
            source: data["successes"] / max(data["attempts"], 1)
            for source, data in goal.items()
            if data["attempts"] >= 3
        }
        if not rates:
            return None
        return max(rates, key=rates.get)

    def record_failure(
        self,
        node_id: str,
        action_type: str,
        agent_id: str,
        reason: str,
    ) -> None:
        """Log a failure for diagnostic review."""
        patterns = self._data.setdefault("failure_patterns", [])
        patterns.append(
            {
                "timestamp": time.time(),
                "node_id": node_id,
                "action_type": action_type,
                "agent_id": agent_id,
                "reason": reason,
            }
        )
        if len(patterns) > 100:
            patterns[:] = patterns[-100:]
        self._save()

    def recent_failures(self, action_type: Optional[str] = None) -> list:
        """Return recent failures, optionally filtered by action type."""
        patterns = self._data.get("failure_patterns", [])
        if action_type:
            patterns = [
                pattern for pattern in patterns if pattern["action_type"] == action_type
            ]
        return patterns[-10:]

    def increment_session(self) -> None:
        """Call at the start of each IntentOS session."""
        self._data["session_count"] = self._data.get("session_count", 0) + 1
        self._data["last_updated"] = time.time()
        self._save()

    def summary(self) -> dict:
        """Return memory summary for logging/debugging."""
        objects = self._data.get("objects", {})
        return {
            "session_count": self._data.get("session_count", 0),
            "objects_tracked": len(objects),
            "total_object_actions": sum(
                sum(len(actions) for actions in obj.values())
                for obj in objects.values()
            ),
            "failure_patterns": len(self._data.get("failure_patterns", [])),
            "last_updated": self._data.get("last_updated"),
        }

    def _load(self) -> None:
        if self._path.exists():
            try:
                with open(self._path) as file:
                    loaded = json.load(file)
                self._data.update(loaded)
                logger.info(
                    "System memory loaded: %d objects, %d sessions",
                    len(self._data.get("objects", {})),
                    self._data.get("session_count", 0),
                )
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Could not load system memory: %s - starting fresh", exc)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp.json")
        try:
            with open(tmp, "w") as file:
                json.dump(self._data, file, indent=2)
            tmp.replace(self._path)
        except OSError as exc:
            logger.error("Failed to save system memory: %s", exc)
