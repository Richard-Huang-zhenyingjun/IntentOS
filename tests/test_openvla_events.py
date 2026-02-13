"""Tests for OpenVLA event logging and metrics aggregation."""

from __future__ import annotations

import json

from src.core.metrics import MetricsCollector
from src.core.system_factory import build_system, load_config


def _proposal_events(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f.read().splitlines() if line.strip()]
    return [row for row in rows if row.get("event_type") == "proposal_issued"]


def test_openvla_proposal_event_includes_openvla_fields(tmp_path):
    config = load_config("configs/default.yaml")
    config.setdefault("simulator", {})
    config["simulator"]["use_gui"] = False
    config.setdefault("logging", {})
    events_path = tmp_path / "events.jsonl"
    config["logging"]["events_enabled"] = True
    config["logging"]["events_path"] = str(events_path)
    config.setdefault("openvla", {})
    config["openvla"]["enabled"] = True
    config["openvla"]["use_fake"] = True
    config.setdefault("gemini", {})
    config["gemini"]["enabled"] = False

    orch = build_system(config)
    try:
        target_id = orch.world_artifacts.object_ids[0]
        orch.force_lock_target(target_id)  # puts FSM into SELECTING
        for _ in range(20):
            orch.step()  # emits proposal_issued once a non-IDLE proposal is available
            if events_path.exists() and _proposal_events(str(events_path)):
                break
    finally:
        if orch.events:
            orch.events.flush()
            orch.events.close()
        orch.close()

    proposal_events = _proposal_events(str(events_path))
    assert proposal_events, "Expected at least one proposal_issued event"

    data = proposal_events[-1]["data"]
    assert data["source"] == "openvla"
    assert isinstance(data.get("instruction"), str) and data["instruction"]
    assert isinstance(data.get("action_data"), dict)
    assert len(data["action_data"]["raw_action"]) == 7
    assert "confidence" in data


def test_metrics_collector_tracks_openvla_counters():
    collector = MetricsCollector("test_openvla_metrics")

    collector.process_event(
        {
            "event_type": "proposal_issued",
            "data": {
                "source": "openvla",
                "instruction": "pick up object",
            },
        }
    )
    collector.process_event(
        {
            "event_type": "proposer_failed",
            "data": {
                "source": "openvla",
            },
        }
    )

    metrics = collector.finalize()
    assert metrics.openvla_proposals == 1
    assert metrics.openvla_failures == 1
    assert metrics.openvla_success_rate == 0.5
