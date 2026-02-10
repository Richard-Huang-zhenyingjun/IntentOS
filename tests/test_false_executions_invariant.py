"""Comprehensive invariant tests for false executions."""

import json

import pytest

from src.core.schema import ArmUIState
from src.core.system_factory import build_system, load_config
from src.input.filter import DecisionFilter
from src.input.pipeline import DecisionPipeline
from src.input.policies import DecisionPolicy
from src.input.router import DecisionRouter
from src.input.source_fake import FakeSource


def _base_config(tmp_path) -> dict:
    config = load_config("configs/default.yaml")
    config.setdefault("simulator", {})
    config["simulator"]["use_gui"] = False
    config.setdefault("gemini", {})
    config["gemini"]["enabled"] = False
    config.setdefault("eeg", {})
    config["eeg"]["enabled"] = False
    config.setdefault("logging", {})
    config["logging"]["events_enabled"] = True
    config["logging"]["events_path"] = str(tmp_path / "events.jsonl")
    return config


def _install_scheduled_input(orch, config: dict):
    test_cfg = dict(config)
    test_cfg["input"] = dict(config.get("input", {}))
    test_cfg["input"]["mode"] = "KEYBOARD_ONLY"
    test_cfg["input"]["sources_enabled"] = ["keyboard"]
    test_cfg["input"]["debounce_frames"] = 0
    test_cfg["input"]["confirm_hold_frames"] = 1
    test_cfg["input"]["min_quality"] = 0.0

    policy = DecisionPolicy.from_config(test_cfg)
    router = DecisionRouter(policy)
    fake = FakeSource()
    # Kick off selection+confirm multiple times to stress authorization flow.
    for frame in (5, 15, 60, 70, 115, 125):
        fake.set_confirm_on_frame(frame)
    router.register_source("keyboard", fake)
    orch.decision_pipeline = DecisionPipeline(router, DecisionFilter(test_cfg))
    if orch.world_artifacts and orch.world_artifacts.object_ids:
        orch.force_lock_target(orch.world_artifacts.object_ids[0])


def test_false_executions_zero_across_full_run(tmp_path):
    """Complete simulated run keeps false executions at zero."""
    config = _base_config(tmp_path)
    orch = build_system(config)
    try:
        _install_scheduled_input(orch, config)
        snapshot = None
        for _ in range(400):
            snapshot = orch.step()

        assert snapshot is not None
        assert snapshot.false_executions == 0

        events_path = tmp_path / "events.jsonl"
        assert events_path.exists()
        lines = [json.loads(line) for line in events_path.read_text().splitlines() if line.strip()]
        assert lines, "Expected non-empty event log"

        token_issues = [e for e in lines if e.get("event_type") == "auth_token_issued"]
        assert len(token_issues) >= 1
        for event in token_issues:
            assert event.get("data", {}).get("token_id")
    finally:
        orch.close()


def test_no_execution_without_token():
    """Execution path must fail hard if state is EXECUTING without valid token."""
    config = load_config("configs/default.yaml")
    config.setdefault("simulator", {})
    config["simulator"]["use_gui"] = False
    config.setdefault("gemini", {})
    config["gemini"]["enabled"] = False
    config.setdefault("eeg", {})
    config["eeg"]["enabled"] = False
    config.setdefault("logging", {})
    config["logging"]["events_enabled"] = False

    orch = build_system(config)
    try:
        orch.state_machine._transition_to(ArmUIState.EXECUTING)
        orch.auth_manager.invalidate("force_no_token")
        world = orch._read_world_state()
        with pytest.raises(AssertionError, match="INVARIANT VIOLATED"):
            orch._execute_task_with_trust(world)
    finally:
        orch.close()
