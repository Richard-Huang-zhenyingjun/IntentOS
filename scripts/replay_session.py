#!/usr/bin/env python3
"""
Replay a recorded Smart Workspace session.

Usage:
    python scripts/replay_session.py data/sessions/<session_file>.jsonl

If no file is provided, the most recent file in data/sessions/ is replayed.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def _format_timestamp(value: Any) -> str:
    """Format SessionLogger timestamps, accepting epoch seconds or ISO strings."""
    if value in (None, ""):
        return "??:??:??"

    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value).strftime("%H:%M:%S")

    text = str(value)
    try:
        return datetime.fromisoformat(text).strftime("%H:%M:%S")
    except ValueError:
        return text[:8] if text else "??:??:??"


def _load_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def replay(session_file: str) -> None:
    path = Path(session_file)
    if not path.exists():
        print(f"Session file not found: {session_file}")
        sys.exit(1)

    records = _load_jsonl(path)
    turns = [record for record in records if record.get("type") == "turn"]

    print(f"\n{'=' * 60}")
    print(f"SESSION REPLAY: {path.name}")
    print(f"Turns: {len(turns)}")
    print(f"{'=' * 60}\n")

    confusion_markers = []

    for i, turn in enumerate(turns):
        ts = turn.get("timestamp", "")
        user_input = turn.get("user_input", "")
        command_class = turn.get("command_class", "")
        response = turn.get("system_response", "")
        intentos_state = turn.get("intentos_state", "")
        kernel_state = turn.get("kernel_state", "")
        false_executions = turn.get("false_executions", 0)

        time_str = _format_timestamp(ts)

        print(f"[{time_str}] > {user_input}")
        if response:
            print(f"         {response[:120]}")
        if intentos_state or kernel_state:
            print(
                f"         state={intentos_state or '?'} "
                f"kernel={kernel_state or '?'} "
                f"false_executions={false_executions}"
            )

        confusion = []
        if command_class == "GOAL" and i > 0:
            prev = turns[i - 1]
            if prev.get("user_input", "").lower() == user_input.lower():
                confusion.append("REPEATED_COMMAND")
        if "why" in user_input.lower() or command_class == "EXPLAIN":
            confusion.append("WHY_REQUEST")
        if command_class == "CANCEL":
            confusion.append("CANCELLED")
        if "wrong" in response.lower() or "can't" in response.lower():
            confusion.append("SYSTEM_LIMITATION")
        if turn.get("user_confusion_signal"):
            confusion.append("LOGGER_CONFUSION_SIGNAL")

        if confusion:
            print(f"         ⚠️  {', '.join(confusion)}")
            confusion_markers.append(
                {
                    "turn": i,
                    "input": user_input,
                    "signals": confusion,
                }
            )

        print()

    print(f"{'=' * 60}")
    print(f"CONFUSION SUMMARY: {len(confusion_markers)} friction points")
    for marker in confusion_markers:
        print(
            f"  Turn {marker['turn']}: {marker['input']!r} "
            f"→ {', '.join(marker['signals'])}"
        )
    print(f"{'=' * 60}\n")


def _latest_session_file() -> Path:
    sessions = sorted(Path("data/sessions").glob("*.jsonl"))
    if not sessions:
        print("No session files found in data/sessions/")
        sys.exit(1)
    return sessions[-1]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        replay(str(_latest_session_file()))
    else:
        replay(sys.argv[1])
