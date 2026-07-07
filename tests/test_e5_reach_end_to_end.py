"""
E5: reach-intent (assistive-reach / CLEAR_SPECIFIC) end-to-end through the
real Orchestrator, authorization, and execution pipeline - not
PlanCompiler.compile()-isolated (see tests/test_plan_compiler.py for that
level).

Confirms the hard rule from the wiring decision: reach travels the SAME
state machine -> _handle_confirm -> _authorize_and_start_phase2_execution ->
_execute_task_with_trust path the heuristic CLEAN_TABLE proposer uses. No
reach-specific execution branch, no path to execution that skips
authorization. Also proves the scope gate holds when driven end-to-end:
wrong object, missing/broken zone config, and an attacker-controlled
arbitrary xyz in proposal metadata must all fail to produce unauthorized
motion, with false_executions staying 0 throughout.

Known limitation (not fixed here, flagged for the record): ReachIntentProposer
scores hand position against scene object positions assuming they share a
coordinate frame. In the real system, hand coordinates are normalized
image-plane [0,1] but SceneSummary object positions are real-world meters.
The happy-path/cancel-mid-grasp tests below sidestep this by constructing the
synthetic hand track's endpoint numerically equal to the real target object's
(x, y) - the scoring math is frame-agnostic (relative distances only), so
this exercises the real estimator/registry/compiler pipeline correctly, but a
real camera would need an actual image-plane -> world projection this system
does not yet have.
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
from src.interfaces.intent_proposal import ActionType, IntentProposal
from src.interfaces.proposer_base import ProposerBase


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


def _install_scheduled_confirms(orch, config, confirm_frames):
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


def _commit_reach_to_object(orch, target_object_id):
    """Feed a real hand track through the registered reach proposer so it
    commits to target_object_id, using that object's own scene position as
    the reach endpoint (see module docstring's coordinate-frame note)."""
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


class _FixedDecision:
    """Minimal stand-in for ReachDecision, just enough for
    Orchestrator._reach_committed_target_id()'s duck-typed read."""

    def __init__(self, target_object_id):
        self.committed = True
        self.target_object_id = target_object_id


class _TamperedReachProposer(ProposerBase):
    """
    Test double standing in for "reach_intent": always proposes a fixed,
    possibly attacker-tampered CLEAR_SPECIFIC IntentProposal. Registered in
    place of the real proposer so these adversarial cases drive the REAL
    end-to-end pipeline (state machine, authorization, PlanCompiler's scope
    gate) rather than constructing an IntentProposal and calling
    PlanCompiler.compile() directly.
    """

    def __init__(self, proposal: IntentProposal, lock_target_id):
        self._proposal = proposal
        self._lock_target_id = lock_target_id

    def name(self) -> str:
        return "tampered_reach"

    def is_available(self) -> bool:
        return True

    def propose(self, scene) -> IntentProposal:
        return self._proposal

    def committed(self) -> bool:
        return True

    def estimate(self, scene):
        return _FixedDecision(self._lock_target_id)


def _run_until(orch, max_steps, predicate):
    max_false_executions = 0
    for _ in range(max_steps):
        snapshot = orch.step()
        max_false_executions = max(max_false_executions, snapshot.false_executions)
        if predicate():
            return True, max_false_executions
    return False, max_false_executions


def test_reach_confirm_authorizes_and_executes_via_generic_path(tmp_path):
    """Happy path: CLEAR_SPECIFIC travels confirm -> authorize -> execute
    identically to CLEAN_TABLE - no reach-specific execution branch."""
    config = _base_config(tmp_path)
    orch = build_system(config)
    try:
        orch.step()  # populate current_scene with real object positions
        target_id = orch.world_artifacts.object_ids[0]
        _commit_reach_to_object(orch, target_id)

        _install_scheduled_confirms(orch, config, confirm_frames=[5, 15])

        reached_executing, max_false_executions = _run_until(
            orch, 60, lambda: orch.state_machine.state == ArmUIState.EXECUTING
        )
        assert reached_executing, "never reached EXECUTING"
        assert orch.current_proposal.action == ActionType.CLEAR_SPECIFIC
        assert orch.state_machine.target_id == target_id
        assert orch.auth_manager.get_active_token_id() is not None

        completed, more_false = _run_until(
            orch, 900,
            lambda: orch.executor.status == ExecutorStatus.COMPLETE
            or not orch.auth_manager.is_authorized(),
        )
        max_false_executions = max(max_false_executions, more_false)
        assert completed, "plan never completed"
        assert max_false_executions == 0

        # bring_closer holds the object at the delivery zone - no RELEASE
        # primitive - so attached_object_id should still be the target.
        assert orch.grasp.attached_object_id == target_id

        zone_center = np.array(
            config["planning"]["assistive_reach"]["delivery_zone_center_xyz"]
        )
        final_world = orch._read_world_state()
        assert final_world.ee_position is not None
        assert np.linalg.norm(final_world.ee_position - zone_center) < 0.35
    finally:
        orch.close()


def test_reach_cancel_mid_grasp_ends_safe(tmp_path):
    """Test #12 for the reach path: revoke after GRASP, before the final
    deliver MOVE_TO, via the same _trigger_reauth/SafePauseHelper mechanism
    already fixed and proven for CLEAN_TABLE - no reach-specific handling."""
    config = _base_config(tmp_path)
    orch = build_system(config)
    try:
        orch.step()
        target_id = orch.world_artifacts.object_ids[0]
        _commit_reach_to_object(orch, target_id)

        _install_scheduled_confirms(orch, config, confirm_frames=[5, 15])

        reached_executing, max_false_executions = _run_until(
            orch, 60, lambda: orch.state_machine.state == ArmUIState.EXECUTING
        )
        assert reached_executing

        grasped, more_false = _run_until(
            orch, 900,
            lambda: (
                orch.grasp.is_holding()
                and orch.state_machine.state == ArmUIState.EXECUTING
                and not orch._safe_pause_active
                and orch.executor.plan_index > 2
            ),
        )
        max_false_executions = max(max_false_executions, more_false)
        assert grasped, "never reached a genuine mid-execution grasped state"
        assert orch.auth_manager.is_authorized()

        orch._trigger_reauth("test_reach_cancel_mid_execution")
        assert orch._safe_pause_active is True

        safe_pause_completed, more_false = _run_until(
            orch, 600, lambda: not orch._safe_pause_active
        )
        max_false_executions = max(max_false_executions, more_false)
        assert safe_pause_completed, "safe pause never completed"
        assert max_false_executions == 0

        # SafePauseHelper's own deposit-then-home always releases into the
        # bin regardless of which proposal triggered the grasp - that is the
        # correct generic safety behavior, not reach-specific handling.
        assert orch.grasp.attached_object_id is None, (
            "object still attached after revoke - unauthorized-position risk"
        )
        assert not orch.auth_manager.is_authorized()
        assert orch.state_machine.state == ArmUIState.CONFIRMING
        assert orch._awaiting_reauth is True
    finally:
        orch.close()


def test_reach_rejects_wrong_object_end_to_end(tmp_path):
    """Proposal claims a different object than the one actually locked as
    target - PlanCompiler's scope gate must reject before any primitive
    executes, driven through the real confirm/authorize path."""
    config = _base_config(tmp_path)
    orch = build_system(config)
    try:
        orch.step()
        locked_id, wrong_id = orch.world_artifacts.object_ids[:2]

        tampered = _TamperedReachProposer(
            proposal=IntentProposal(
                action=ActionType.CLEAR_SPECIFIC,
                description="bring object closer (tampered: wrong object)",
                source="tampered_reach",
                confidence=0.85,
                suggested_object_ids=[wrong_id],
                metadata={
                    "assist_action": "bring_closer",
                    "target_object_id": wrong_id,
                    "requires_confirmation": True,
                },
            ),
            lock_target_id=locked_id,
        )
        orch.proposer_registry.register("reach_intent", tampered, priority=20)

        _install_scheduled_confirms(orch, config, confirm_frames=[5, 15])

        _, max_false_executions = _run_until(
            orch, 60, lambda: orch.state_machine.state == ArmUIState.CONFIRMING
        )

        idled, more_false = _run_until(
            orch, 30, lambda: orch.state_machine.state == ArmUIState.IDLE
        )
        max_false_executions = max(max_false_executions, more_false)
        assert idled, "expected rejection to reset the state machine to IDLE"
        assert max_false_executions == 0
        assert orch.executor.active_plan in (None, [])
        assert orch.grasp.attached_object_id is None
    finally:
        orch.close()


def test_reach_rejects_missing_zone_end_to_end(tmp_path):
    """A real, valid reach commit must still fail to execute anything if the
    compiler's own delivery-zone config is missing/broken - through the real
    pipeline, not a direct PlanCompiler.compile() call."""
    config = _base_config(tmp_path)
    config["planning"].pop("assistive_reach", None)
    orch = build_system(config)
    try:
        orch.step()
        target_id = orch.world_artifacts.object_ids[0]
        _commit_reach_to_object(orch, target_id)

        _install_scheduled_confirms(orch, config, confirm_frames=[5, 15])

        idled, max_false_executions = _run_until(
            orch, 60, lambda: orch.state_machine.state == ArmUIState.IDLE
        )
        assert idled, "expected rejection (missing zone config) to reset to IDLE"
        assert max_false_executions == 0
        assert orch.executor.active_plan in (None, [])
        assert orch.grasp.attached_object_id is None
    finally:
        orch.close()


def test_reach_ignores_arbitrary_attacker_xyz_end_to_end(tmp_path):
    """Proposal metadata claims a wild delivery_zone_xyz. Object/zone are
    otherwise valid, so the plan DOES execute - but the arm must physically
    end up at the compiler's CONFIGURED zone, never near the attacker value,
    confirmed via real physics execution, not just inspecting the compiled
    Primitive object."""
    config = _base_config(tmp_path)
    orch = build_system(config)
    try:
        orch.step()
        target_id = orch.world_artifacts.object_ids[0]

        tampered = _TamperedReachProposer(
            proposal=IntentProposal(
                action=ActionType.CLEAR_SPECIFIC,
                description="bring object closer (tampered: arbitrary xyz)",
                source="tampered_reach",
                confidence=0.85,
                suggested_object_ids=[target_id],
                metadata={
                    "assist_action": "bring_closer",
                    "target_object_id": target_id,
                    "requires_confirmation": True,
                    "delivery_zone_name": "attacker_zone",
                    "delivery_zone_xyz": (99.0, 99.0, 99.0),
                },
            ),
            lock_target_id=target_id,
        )
        orch.proposer_registry.register("reach_intent", tampered, priority=20)

        _install_scheduled_confirms(orch, config, confirm_frames=[5, 15])

        reached_executing, max_false_executions = _run_until(
            orch, 60, lambda: orch.state_machine.state == ArmUIState.EXECUTING
        )
        assert reached_executing

        completed, more_false = _run_until(
            orch, 900,
            lambda: orch.executor.status == ExecutorStatus.COMPLETE
            or not orch.auth_manager.is_authorized(),
        )
        max_false_executions = max(max_false_executions, more_false)
        assert completed, "plan never completed"
        assert max_false_executions == 0

        zone_center = np.array(
            config["planning"]["assistive_reach"]["delivery_zone_center_xyz"]
        )
        final_world = orch._read_world_state()
        assert final_world.ee_position is not None
        assert np.linalg.norm(final_world.ee_position - zone_center) < 0.35
        # Never anywhere close to the attacker-controlled coordinates.
        assert np.linalg.norm(final_world.ee_position - np.array([99.0, 99.0, 99.0])) > 50
    finally:
        orch.close()
