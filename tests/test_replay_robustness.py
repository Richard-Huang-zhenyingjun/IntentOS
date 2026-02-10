"""Robustness tests for replay event formatting and JSONL parsing."""

import json
from src.tools.replay_events import format_event, replay


def test_unknown_event_type():
    event = {"event_type": "xyz", "frame": 1, "data": {}}
    output = format_event(event)
    assert isinstance(output, str)
    assert len(output) > 0


def test_empty_data():
    event = {"event_type": "trust_updated", "frame": 1, "data": {}}
    output = format_event(event)
    assert isinstance(output, str)
    assert len(output) > 0


def test_malformed_jsonl_file(tmp_path):
    filepath = tmp_path / "mixed_events.jsonl"

    lines = [
        json.dumps({"event_type": "auth_token_issued", "frame": 1, "data": {"token_id": "auth_1"}}),
        "this is not json",
        "{\"event_type\": \"trust_updated\", \"frame\": 2, \"data\": {\"task_trust\": 0.9}}",
        "{bad json line",
    ]

    filepath.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Should skip malformed lines and not raise.
    replay(str(filepath))
