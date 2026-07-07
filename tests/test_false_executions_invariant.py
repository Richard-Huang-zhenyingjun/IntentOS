"""Comprehensive invariant tests for false executions."""

import json

import numpy as np
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


def test_cancel_mid_execution_after_grasp_before_release_ends_safe(tmp_path):
    """Revoking authorization after GRASP but before RELEASE must not leave
    the arm holding an object in an unauthorized position, and must not
    record a false execution.

    Note: there is no separate user-CANCEL-during-EXECUTING input path wired
    in this orchestrator today - the state dispatcher only handles CANCEL
    while state == 'confirming' (src/core/orchestrator.py _update_state_machine).
    The system's actual mechanism for a mid-execution revoke is the
    trust-drop reauth trigger (_trigger_reauth): it invalidates the token and
    arms SafePauseHelper's deposit-then-home sequence. This test drives that
    real mechanism directly rather than inventing a new one.
    """
    config = _base_config(tmp_path)
    # Force the heuristic CLEAN_TABLE proposer: OpenVLA is registered at
    # priority 15 (> heuristic's 0) and compiles to a single opaque
    # OPENVLA_TRAJECTORY primitive, not the discrete REACH/GRASP/MOVE_TO/
    # RELEASE sequence this test needs to interrupt between GRASP and RELEASE.
    config.setdefault("openvla", {})
    config["openvla"]["enabled"] = False
    orch = build_system(config)
    try:
        _install_scheduled_input(orch, config)

        # GRASP is primitive index 2 in the compiled CLEAN_TABLE plan (approach,
        # pre_grasp, GRASP, lift, move_to_bin, lower_to_drop, RELEASE, home).
        # grasp.is_holding() does a live physical verify_grasp() check, which
        # can read True from incidental finger/object contact before the
        # GRASP primitive has actually run - so also require plan_index have
        # advanced past it, to be sure we're genuinely mid-execution between
        # GRASP and RELEASE, not catching a false-positive contact reading.
        # GRASP itself is a multi-stage APPROACH -> DESCEND -> CLOSE sequence
        # with up to 180-frame timeouts per stage, so budget generously.
        max_false_executions = 0
        grasped = False
        for _ in range(800):
            snapshot = orch.step()
            max_false_executions = max(max_false_executions, snapshot.false_executions)
            if (
                orch.grasp.is_holding()
                and orch.state_machine.state == ArmUIState.EXECUTING
                and not orch._safe_pause_active
                and orch.executor.plan_index > 2
            ):
                grasped = True
                break

        assert grasped, "Test setup failed: never reached a genuine mid-execution grasped state"
        assert orch.auth_manager.is_authorized()

        # Revoke authorization mid-execution: after GRASP, before RELEASE.
        orch._trigger_reauth("test_cancel_mid_execution")
        assert orch._safe_pause_active is True

        safe_pause_completed = False
        for _ in range(600):
            snapshot = orch.step()
            max_false_executions = max(max_false_executions, snapshot.false_executions)
            if not orch._safe_pause_active:
                safe_pause_completed = True
                break

        assert safe_pause_completed, "Safe pause never completed"
        assert max_false_executions == 0

        # is_holding()/verify_grasp() is a live finger-joint force heuristic
        # with its own pre-existing quirk: right after open(), diagnostics
        # showed width=0.25 (impossible - exceeds the configured max_width of
        # 0.08 and the 0.04-per-joint limit) with force=60.0, a likely
        # controller-saturation artifact from commanding a target beyond the
        # joint limit - not a real grip. That heuristic is unrelated to the
        # revoke/safe-pause fix under test here, so use the authoritative
        # signal instead: attached_object_id, which _execute_release() clears
        # (alongside actually removing the pybullet constraint) regardless of
        # this force reading.
        assert orch.grasp.attached_object_id is None, (
            "Object still attached after revoke - unauthorized-position risk"
        )
        assert not orch.auth_manager.is_authorized(), (
            "Stale token still active after safe pause"
        )
        assert orch.state_machine.state == ArmUIState.CONFIRMING
        assert orch._awaiting_reauth is True

        final_world = orch._read_world_state()
        safe_home = np.array(config["planning"]["clean_table"]["safe_home_xyz"])
        assert final_world.ee_position is not None
        assert np.linalg.norm(final_world.ee_position - safe_home) < 0.05
    finally:
        orch.close()
