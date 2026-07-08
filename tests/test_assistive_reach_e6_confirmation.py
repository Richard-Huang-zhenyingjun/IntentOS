"""
E6: prove the confirmation round-trip for assistive-reach (CLEAR_SPECIFIC)
through the real _handle_confirm path - not by asserting a flag, and not by
calling PlanCompiler.compile()/executor.start_plan() directly.

Every test here drives the same state machine -> decision pipeline ->
_handle_confirm -> _authorize_and_start_phase2_execution path the heuristic
CLEAN_TABLE proposer uses (src/core/orchestrator.py step()). There is no
reach-specific confirm branch to find or build: E5's wiring (ArmActionType.
CLEAR_SPECIFIC, ReachIntentProposer registration, the IDLE-branch target
lock) already gets a reach proposal to 'confirming' the same way CLEAN_TABLE
gets there, and _handle_confirm itself has never branched on action type -
confirmed by direct reading (only checks decision_frame.metadata["intentos_
owned"], nothing else). So this file is proof, not new wiring: see the E6
report for exactly what was and wasn't already true before these tests ran.

Timeout / no-response: searched state_machine.py and orchestrator.py -
state_entry_frame is written on every transition but never read anywhere.
There is no auto-expiry of a pending CONFIRMING state. Confirmed absent, not
invented: no timeout test exists in this file for that reason.
"""
import math

import numpy as np
import pytest

from src.core.schema import ArmUIState
from src.core.system_factory import build_system, load_config
from src.execution.primitive_executor import ExecutorStatus
from src.input.filter import DecisionFilter
from src.input.pipeline import DecisionPipeline
from src.input.policies import DecisionPolicy
from src.input.router import DecisionRouter
from src.input.source_fake import FakeSource
from src.interfaces.hand_state import HandState
from src.interfaces.intent_proposal import ActionType


def _base_config(tmp_path):
    config = load_config("configs/default.yaml")
    config.setdefault("simulator", {})
    config["simulator"]["use_gui"] = False
    config.setdefault("gemini", {})
    config["gemini"]["enabled"] = False
    config.setdefault("eeg", {})
    config["eeg"]["enabled"] = False
    config.setdefault("openvla", {})
    config["openvla"]["enabled"] = False  # isolate the heuristic/reach path
    config.setdefault("logging", {})
    config["logging"]["events_enabled"] = True
    config["logging"]["events_path"] = str(tmp_path / "events.jsonl")
    return config


def _install_scheduled_events(orch, config, confirm_frames=(), cancel_frames=()):
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
    for frame in confirm_frames:
        fake.set_confirm_on_frame(frame)
    for frame in cancel_frames:
        fake.set_cancel_on_frame(frame)
    router.register_source("keyboard", fake)
    orch.decision_pipeline = DecisionPipeline(router, DecisionFilter(test_cfg))


def _hand_track_to(start_xy, end_xy, n_frames=8, fps=30.0, aperture=0.15):
    dt = 1.0 / fps
    sx, sy = start_xy
    ex, ey = end_xy
    dx = (ex - sx) / (n_frames - 1)
    dy = (ey - sy) / (n_frames - 1)
    vx, vy = dx / dt, dy / dt
    speed = math.hypot(vx, vy)
    n = math.hypot(dx, dy)
    direction_xy = (dx / n, dy / n) if n > 1e-9 else (0.0, 0.0)
    frames = []
    for i in range(n_frames):
        px, py = sx + dx * i, sy + dy * i
        frames.append(HandState(
            timestamp_s=i * dt,
            wrist_xy=(px, py),
            index_tip_xy=(px, py),
            thumb_tip_xy=(px + aperture, py),
            velocity_xy=(vx, vy),
            speed=speed,
            reach_direction_xy=direction_xy,
            grasp_aperture=aperture,
            detection_confidence=1.0,
            hand_present=True,
        ))
    return frames


def _reachable_target_id(orch, config):
    """Nearest-to-base first (mirrors PlanCompiler._select_nearest_object),
    filtered by a real controller._compute_ik() feasibility check (pure, no
    motion) - see tests/test_e5_reach_end_to_end.py for why plain
    nearest-in-xy alone isn't reliable."""
    approach_height = config["planning"]["clean_table"]["approach_height"]
    robot_base_xy = np.array([0.0, 0.0])
    candidates = sorted(
        orch.current_scene.objects_on_table,
        key=lambda obj: np.linalg.norm(np.array(obj.pos_xyz[:2]) - robot_base_xy),
    )
    for obj in candidates:
        approach_target = np.array(obj.pos_xyz) + np.array([0, 0, approach_height])
        if orch.controller._compute_ik(approach_target) is not None:
            return obj.object_id
    raise RuntimeError("no reachable object found in this scene")


def _commit_reach_to_object(orch, target_object_id):
    """Feed a real hand track through the registered reach proposer so it
    commits to target_object_id. update_hand() is a side channel - it is
    never wired into confirm/authorize/execute, only into what the proposer
    itself decides to propose next 'selecting' tick."""
    reach_proposer = orch.proposer_registry.get("reach_intent")
    assert reach_proposer is not None, "reach_intent proposer not registered"

    target_obj = next(
        obj for obj in orch.current_scene.objects_on_table
        if obj.object_id == target_object_id
    )
    end_xy = (target_obj.pos_xyz[0], target_obj.pos_xyz[1])
    start_xy = (end_xy[0] - 0.3, end_xy[1] - 0.1)
    for hand in _hand_track_to(start_xy, end_xy, n_frames=8):
        reach_proposer.update_hand(hand)

    decision = reach_proposer.estimate(orch.current_scene)
    assert decision.committed and decision.target_object_id == target_object_id, (
        f"reach did not commit to the intended object: {decision}"
    )
    return reach_proposer


def _run_until(orch, max_steps, predicate):
    max_false_executions = 0
    for _ in range(max_steps):
        snapshot = orch.step()
        max_false_executions = max(max_false_executions, snapshot.false_executions)
        if predicate():
            return True, max_false_executions
    return False, max_false_executions


def _run_n(orch, n_steps):
    max_false_executions = 0
    for _ in range(n_steps):
        snapshot = orch.step()
        max_false_executions = max(max_false_executions, snapshot.false_executions)
    return max_false_executions


def test_reach_pending_confirmation_executes_nothing(tmp_path):
    """A reach proposal reaching CONFIRMING (one confirm to lock target ->
    auto-propose -> CONFIRMING) with no second confirm ever sent must stay
    pending forever: no token, no primitive, no arm motion, false_executions
    stays 0. Proves 'awaiting confirmation' is a real gate, not a formality."""
    config = _base_config(tmp_path)
    orch = build_system(config)
    try:
        orch.step()
        target_id = _reachable_target_id(orch, config)
        _commit_reach_to_object(orch, target_id)

        # Only the first confirm (locks target, reaches CONFIRMING). No
        # second confirm anywhere in this schedule.
        _install_scheduled_events(orch, config, confirm_frames=[5])

        reached_confirming, max_false_executions = _run_until(
            orch, 60, lambda: orch.state_machine.state == ArmUIState.CONFIRMING
        )
        assert reached_confirming
        assert orch.current_proposal.action == ActionType.CLEAR_SPECIFIC

        # Real finding while building this test: raw end-effector position
        # is NOT a usable "did it move" signal here. Nothing actively holds
        # joint position via POSITION_CONTROL while no primitive is running
        # (setJointMotorControlArray is only called from inside REACH/
        # MOVE_TO methods) - so the arm passively sags under gravity, fast
        # (>0.5 units within 10 steps measured on CI), the instant physics
        # keeps stepping with no active hold. That is a real, pre-existing
        # simulator/controller characteristic, unrelated to authorization -
        # not a signal that a primitive executed. The commanded-motion
        # question is answered precisely and reliably by the logical
        # signals below instead: no token, no plan, no attachment. Sitting
        # pending for a long time - no confirm arrives.
        more_false = _run_n(orch, 300)
        max_false_executions = max(max_false_executions, more_false)

        assert orch.state_machine.state == ArmUIState.CONFIRMING, (
            "should still be pending - nothing should auto-advance it"
        )
        assert orch.auth_manager.get_active_token_id() is None
        assert orch.auth_manager.tokens_issued == 0
        assert orch.executor.status == ExecutorStatus.IDLE
        assert orch.executor.active_plan in (None, [])
        assert not orch.executor.is_holding_object()
        assert max_false_executions == 0
    finally:
        orch.close()


def test_reach_confirm_issues_token_strictly_after_confirm_then_executes(tmp_path):
    """The token must not exist before the confirm event, and must exist
    immediately after it - proving _authorize_and_start_phase2_execution
    (not something else) is what creates it, exactly on the confirm tick."""
    config = _base_config(tmp_path)
    orch = build_system(config)
    try:
        orch.step()
        target_id = _reachable_target_id(orch, config)
        _commit_reach_to_object(orch, target_id)

        _install_scheduled_events(orch, config, confirm_frames=[5, 15])

        reached_confirming, max_false_executions = _run_until(
            orch, 60, lambda: orch.state_machine.state == ArmUIState.CONFIRMING
        )
        assert reached_confirming
        # Strictly before the authorizing confirm: no token anywhere yet.
        assert orch.auth_manager.get_active_token_id() is None
        assert orch.auth_manager.tokens_issued == 0
        assert orch.executor.status == ExecutorStatus.IDLE

        # Step one tick at a time up to and through the frame-15 confirm,
        # so we can pinpoint exactly when the token appears.
        token_seen_at_step = None
        for i in range(30):
            snapshot = orch.step()
            max_false_executions = max(max_false_executions, snapshot.false_executions)
            if orch.auth_manager.get_active_token_id() is not None:
                token_seen_at_step = i
                break

        assert token_seen_at_step is not None, "token was never issued"
        assert orch.auth_manager.tokens_issued == 1
        # Token issuance and the EXECUTING transition happen inside the same
        # synchronous call (_authorize_and_start_phase2_execution issues the
        # token, compiles, then calls state_machine.start_execution() - all
        # in one call, itself called synchronously from the same step()
        # tick's 'confirming' branch) - so this must already be EXECUTING on
        # the exact same tick the token first appears, not eventually.
        assert orch.state_machine.state == ArmUIState.EXECUTING

        executing, more_false = _run_until(
            orch, 30, lambda: orch.state_machine.state == ArmUIState.EXECUTING
        )
        max_false_executions = max(max_false_executions, more_false)
        assert executing
        assert orch.executor.active_plan, "confirm must have started a real plan"
        assert max_false_executions == 0
    finally:
        orch.close()


def test_reach_reject_zero_execution_zero_token(tmp_path):
    """The critical negative case: an explicit decline while a reach
    proposal is pending must produce zero primitives, zero tokens ever
    issued, no arm motion, and discard the proposal (reset to IDLE) -
    through the same CANCEL handling CLEAN_TABLE gets, not a reach-specific
    path."""
    config = _base_config(tmp_path)
    orch = build_system(config)
    try:
        orch.step()
        target_id = _reachable_target_id(orch, config)
        _commit_reach_to_object(orch, target_id)

        _install_scheduled_events(orch, config, confirm_frames=[5], cancel_frames=[15])

        reached_confirming, max_false_executions = _run_until(
            orch, 60, lambda: orch.state_machine.state == ArmUIState.CONFIRMING
        )
        assert reached_confirming

        idled, more_false = _run_until(
            orch, 30, lambda: orch.state_machine.state == ArmUIState.IDLE
        )
        max_false_executions = max(max_false_executions, more_false)
        assert idled, "reject/cancel must reset the state machine to IDLE"

        # Raw end-effector position is not used here as a "did it move"
        # signal - see test_reach_pending_confirmation_executes_nothing for
        # why (passive gravity sag with nothing actively holding joint
        # position, fast and real, unrelated to authorization). The logical
        # signals below answer "did anything execute" precisely. Run on a
        # good while past the reject - nothing should ever start.
        more_false = _run_n(orch, 200)
        max_false_executions = max(max_false_executions, more_false)

        assert orch.auth_manager.get_active_token_id() is None
        assert orch.auth_manager.tokens_issued == 0, (
            "a rejected proposal must never have caused a token to be issued"
        )
        assert orch.executor.status == ExecutorStatus.IDLE
        assert orch.executor.active_plan in (None, [])
        assert not orch.executor.is_holding_object()
        assert orch.state_machine.target_id is None
        assert orch.state_machine.proposal is None
        assert max_false_executions == 0
    finally:
        orch.close()


def test_reach_no_timeout_concept_pending_forever_is_the_only_current_behavior(tmp_path):
    """
    Documents rather than invents: state_machine.py tracks state_entry_frame
    on every transition but nothing in this codebase ever reads it back to
    auto-expire a pending CONFIRMING state (grep confirms zero read sites).
    So today, "timeout" and "pending indefinitely" are the same behavior -
    already covered by test_reach_pending_confirmation_executes_nothing
    above. This test only asserts that a very long pending window still
    produces zero execution, without asserting any expiry transition, since
    none exists to assert.
    """
    config = _base_config(tmp_path)
    orch = build_system(config)
    try:
        orch.step()
        target_id = _reachable_target_id(orch, config)
        _commit_reach_to_object(orch, target_id)

        _install_scheduled_events(orch, config, confirm_frames=[5])

        reached_confirming, max_false_executions = _run_until(
            orch, 60, lambda: orch.state_machine.state == ArmUIState.CONFIRMING
        )
        assert reached_confirming

        # A long window well past anything this codebase's other tests wait
        # for GRASP/safe-pause to converge - if an expiry existed, it would
        # have fired by now.
        more_false = _run_n(orch, 1000)
        max_false_executions = max(max_false_executions, more_false)

        assert orch.state_machine.state == ArmUIState.CONFIRMING, (
            "no timeout/expiry exists in this codebase - state should still "
            "be exactly where it was left, not auto-transitioned"
        )
        assert orch.auth_manager.tokens_issued == 0
        assert orch.executor.active_plan in (None, [])
        assert max_false_executions == 0
    finally:
        orch.close()


def test_reach_reconfirm_after_reject_does_not_resurrect_stale_token(tmp_path):
    """After a reject, a fresh confirm cycle must issue a genuinely NEW
    token (tokens_issued goes 0 -> 1, not reusing/reviving anything), and
    only that fresh cycle may execute."""
    config = _base_config(tmp_path)
    orch = build_system(config)
    try:
        orch.step()
        target_id = _reachable_target_id(orch, config)
        _commit_reach_to_object(orch, target_id)

        # First cycle: reach CONFIRMING, then reject.
        _install_scheduled_events(orch, config, confirm_frames=[5], cancel_frames=[15])
        reached_confirming, max_false_executions = _run_until(
            orch, 60, lambda: orch.state_machine.state == ArmUIState.CONFIRMING
        )
        assert reached_confirming
        idled, more_false = _run_until(
            orch, 30, lambda: orch.state_machine.state == ArmUIState.IDLE
        )
        max_false_executions = max(max_false_executions, more_false)
        assert idled
        assert orch.auth_manager.tokens_issued == 0

        # Reach is still committed (update_hand was never called again, and
        # nothing retracts it just from sitting idle) - re-lock naturally on
        # the next real confirm, exactly like a second genuine attempt would.
        _install_scheduled_events(orch, config, confirm_frames=[5, 15])
        # Reset the fake source's own frame counter context by reusing the
        # same relative schedule from here.
        reached_confirming_2, more_false = _run_until(
            orch, 60, lambda: orch.state_machine.state == ArmUIState.CONFIRMING
        )
        max_false_executions = max(max_false_executions, more_false)
        assert reached_confirming_2, "reach must be able to propose again after a reject"
        assert orch.auth_manager.tokens_issued == 0, (
            "still no token until this second cycle's own confirm"
        )

        executing, more_false = _run_until(
            orch, 60, lambda: orch.state_machine.state == ArmUIState.EXECUTING
        )
        max_false_executions = max(max_false_executions, more_false)
        assert executing
        assert orch.auth_manager.tokens_issued == 1, (
            "exactly one fresh token from the second cycle - nothing resurrected"
        )
        assert orch.executor.active_plan, "the fresh cycle's own plan must be running"
        assert max_false_executions == 0
    finally:
        orch.close()
