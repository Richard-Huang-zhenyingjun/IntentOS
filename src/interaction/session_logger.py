"""
SessionLogger - logs every interaction turn for post-session review.

Output: data/sessions/session_YYYYMMDD_HHMMSS.jsonl
Format: one JSON object per line (JSONL)

What to look for after a session:
  - Turns where user typed "why" or "explain" -> system wasn't clear
  - Turns where user typed the goal twice -> first attempt failed silently
  - High user_confusion_signal -> something was confusing
  - false_executions > 0 -> safety violation (should never happen)
  - confirm_count > 2 for a 10-step task -> attention overload
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


SESSION_DIR = Path("data/sessions")


class SessionLogger:
    """
    Logs every interaction turn to a JSONL file.
    One file per session. Atomic writes per turn.
    """

    def __init__(self, preset_name: str = "default"):
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._path = SESSION_DIR / f"session_{preset_name}_{timestamp}.jsonl"
        self._session_start = time.time()
        self._turn_count = 0
        self._confirm_count = 0
        self._explain_count = 0
        self._false_exec_count = 0
        self._file = open(self._path, "w", buffering=1)

        self._write({
            "type": "session_start",
            "preset": preset_name,
            "timestamp": self._session_start,
        })

    def log_turn(
        self,
        user_input: str,
        command_class: str,
        system_response: str,
        orchestrator_state: dict,
        debug_mode: bool,
    ) -> None:
        """Log one interaction turn."""
        self._turn_count += 1

        if command_class == "CONFIRM":
            self._confirm_count += 1
        if command_class == "EXPLAIN":
            self._explain_count += 1

        false_exec = orchestrator_state.get("false_executions", 0)
        if false_exec > self._false_exec_count:
            self._false_exec_count = false_exec

        confusion_signal = self._detect_confusion(
            user_input,
            command_class,
            system_response,
        )

        turn = {
            "type": "turn",
            "turn_number": self._turn_count,
            "timestamp": time.time(),
            "elapsed_s": round(time.time() - self._session_start, 1),
            "user_input": user_input,
            "command_class": command_class,
            "system_response": system_response[:200],
            "intentos_state": orchestrator_state.get("intentos_state", "?"),
            "kernel_state": orchestrator_state.get("kernel_state", "?"),
            "false_executions": false_exec,
            "debug_mode": debug_mode,
            "confirm_count_so_far": self._confirm_count,
            "explain_count_so_far": self._explain_count,
            "user_confusion_signal": confusion_signal,
        }
        self._write(turn)

    def log_execution_event(
        self,
        event_type: str,
        node_id: str,
        success: bool,
        human_description: str,
        failure_reason: Optional[str] = None,
    ) -> None:
        """Log a node execution event."""
        self._write({
            "type": "execution_event",
            "timestamp": time.time(),
            "event_type": event_type,
            "node_id": node_id,
            "success": success,
            "human_description": human_description,
            "failure_reason": failure_reason,
        })

    def log_recovery(
        self,
        failure_class: str,
        node_id: str,
        human_explanation: str,
        user_response: Optional[str] = None,
    ) -> None:
        """Log a recovery event."""
        self._write({
            "type": "recovery",
            "timestamp": time.time(),
            "failure_class": failure_class,
            "node_id": node_id,
            "human_explanation": human_explanation,
            "user_response": user_response,
        })

    def close(self) -> None:
        """Write session summary and close file."""
        duration = time.time() - self._session_start
        summary = {
            "type": "session_end",
            "timestamp": time.time(),
            "duration_s": round(duration, 1),
            "turns": self._turn_count,
            "confirmations": self._confirm_count,
            "explain_requests": self._explain_count,
            "false_executions": self._false_exec_count,
            "session_file": str(self._path),
        }
        self._write(summary)
        self._file.close()

        print(f"\n{'─' * 50}")
        print(f"  Session saved: {self._path.name}")
        print(f"  Duration:      {duration:.0f}s")
        print(f"  Turns:         {self._turn_count}")
        print(f"  Confirmations: {self._confirm_count}")
        print(f"  Explain asks:  {self._explain_count}")
        print(f"  false_executions: {self._false_exec_count}")
        print(f"{'─' * 50}")

    def _write(self, obj: dict) -> None:
        """Write one JSON line, flush immediately."""
        self._file.write(json.dumps(obj) + "\n")
        self._file.flush()

    @staticmethod
    def _detect_confusion(
        user_input: str,
        command_class: str,
        system_response: str,
    ) -> bool:
        """
        Heuristic: did this turn suggest the user was confused?
        """
        confusion_phrases = {
            "why",
            "what",
            "explain",
            "what do you mean",
            "i don't understand",
            "huh",
            "what happened",
            "what are you doing",
            "what does that mean",
        }
        return (
            command_class == "EXPLAIN"
            or any(p in user_input.lower() for p in confusion_phrases)
            or "I don't understand" in system_response
        )
