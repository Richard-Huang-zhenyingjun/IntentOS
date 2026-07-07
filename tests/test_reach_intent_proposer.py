"""Fixture-based tests for ReachIntentProposer. No camera, no arm."""
from __future__ import annotations

import math
from typing import List, Tuple

from src.interfaces.hand_state import HandState
from src.interfaces.intent_proposal import ActionType
from src.interfaces.scene_summary import ObjectInfo, SceneSummary
from src.intelligence.proposer_reach import ReachIntentProposer


def _make_scene(object_specs: List[Tuple[int, Tuple[float, float]]]) -> SceneSummary:
    objs = tuple(
        ObjectInfo(object_id=oid, pos_xyz=(x, y, 0.63), on_table=True, confidence=1.0)
        for (oid, (x, y)) in object_specs
    )
    return SceneSummary(
        table_id=1,
        table_position=(0.0, 0.0, 0.3),
        bin_zone_center=(0.4, 0.0, 0.75),
        bin_zone_radius=0.12,
        objects=objs,
        objects_on_table=objs,
        clutter_score=0.5 if objs else 0.0,
        is_messy=bool(objs),
        timestamp_frame=1,
    )


def _make_hand_track(
    start_xy: Tuple[float, float],
    end_xy: Tuple[float, float],
    n_frames: int = 8,
    fps: float = 30.0,
    aperture: float = 0.15,
) -> List[HandState]:
    dt = 1.0 / fps
    sx, sy = start_xy
    ex, ey = end_xy
    dx = (ex - sx) / (n_frames - 1)
    dy = (ey - sy) / (n_frames - 1)
    vx, vy = dx / dt, dy / dt
    speed = math.hypot(vx, vy)
    n = math.hypot(dx, dy)
    direction_xy = (dx / n, dy / n) if n > 1e-9 else (0.0, 0.0)

    frames: List[HandState] = []
    for i in range(n_frames):
        px, py = sx + dx * i, sy + dy * i
        frames.append(
            HandState(
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
            )
        )
    return frames


def _make_still_track(
    at_xy: Tuple[float, float], n_frames: int = 8, fps: float = 30.0
) -> List[HandState]:
    dt = 1.0 / fps
    return [
        HandState(
            timestamp_s=i * dt,
            wrist_xy=at_xy,
            index_tip_xy=at_xy,
            thumb_tip_xy=(at_xy[0] + 0.15, at_xy[1]),
            velocity_xy=(0.0, 0.0),
            speed=0.0,
            reach_direction_xy=(0.0, 0.0),
            grasp_aperture=0.15,
            detection_confidence=1.0,
            hand_present=True,
        )
        for i in range(n_frames)
    ]


def _make_absent_track(n_frames: int = 8, fps: float = 30.0) -> List[HandState]:
    dt = 1.0 / fps
    return [HandState.absent(timestamp_s=i * dt) for i in range(n_frames)]


def _feed(proposer: ReachIntentProposer, track: List[HandState]) -> None:
    for hand in track:
        proposer.update_hand(hand)


def test_object_along_reach_ray_gets_highest_score():
    proposer = ReachIntentProposer()
    scene = _make_scene([(4, (0.8, 0.5)), (5, (0.5, 0.9))])
    _feed(proposer, _make_hand_track((0.2, 0.5), (0.6, 0.5)))

    decision = proposer.estimate(scene)

    assert decision.committed
    assert decision.target_object_id == 4
    assert decision.reason == "reach_points_to_object"


def test_ambiguous_two_object_case_flags_needs_confirmation():
    proposer = ReachIntentProposer()
    scene = _make_scene([(4, (0.8, 0.62)), (5, (0.8, 0.38))])
    _feed(proposer, _make_hand_track((0.2, 0.5), (0.6, 0.5)))

    decision = proposer.estimate(scene)
    proposal = proposer.propose(scene)

    assert decision.committed
    assert decision.reason == "ambiguous_target"
    assert proposal.action == ActionType.CLEAR_SPECIFIC
    assert proposal.confidence < 0.85
    assert proposal.metadata["requires_confirmation"] is True


def test_no_hand_returns_no_intent():
    proposer = ReachIntentProposer()
    scene = _make_scene([(4, (0.8, 0.5))])
    _feed(proposer, _make_absent_track())

    decision = proposer.estimate(scene)
    proposal = proposer.propose(scene)

    assert not decision.committed
    assert proposal.action == ActionType.IDLE
    assert proposal.confidence == 0.0


def test_still_hand_returns_no_intent():
    proposer = ReachIntentProposer()
    scene = _make_scene([(4, (0.8, 0.5))])
    _feed(proposer, _make_still_track((0.2, 0.5)))

    decision = proposer.estimate(scene)

    assert not proposer.committed()
    assert not decision.committed
    assert decision.reason == "no_committed_reach"


def test_low_confidence_never_yields_execution_grade_proposal():
    proposer = ReachIntentProposer()
    scene = _make_scene([(4, (0.8, 0.5)), (5, (0.5, 0.9))])
    _feed(proposer, _make_hand_track((0.2, 0.5), (0.6, 0.5)))

    proposal = proposer.propose(scene)

    assert proposal.confidence < 1.0
    assert proposal.metadata["requires_confirmation"] is True


def test_proposer_never_touches_robot_only_emits_proposal():
    proposer = ReachIntentProposer()
    public = [attr for attr in dir(proposer) if not attr.startswith("_")]
    for banned in ("execute", "move", "arm", "controller", "run_primitive"):
        assert banned not in public

    scene = _make_scene([(4, (0.8, 0.5))])
    _feed(proposer, _make_hand_track((0.2, 0.5), (0.6, 0.5)))
    out = proposer.propose(scene)

    assert out.__class__.__name__ == "IntentProposal"


def test_onset_does_not_false_fire_on_brief_twitch():
    proposer = ReachIntentProposer()
    track = _make_still_track((0.2, 0.5), n_frames=3)
    fast = _make_hand_track((0.2, 0.5), (0.25, 0.5), n_frames=2)[1:]
    track = track + fast + _make_still_track((0.25, 0.5), n_frames=3)
    _feed(proposer, track)

    assert not proposer.committed()


def test_committed_reach_then_retract_returns_to_idle():
    proposer = ReachIntentProposer()
    _feed(proposer, _make_hand_track((0.2, 0.5), (0.6, 0.5)))
    assert proposer.committed()

    _feed(proposer, _make_still_track((0.6, 0.5), n_frames=25))

    assert not proposer.committed()


def test_proposal_declares_delivery_zone_for_scope_checker():
    proposer = ReachIntentProposer()
    scene = _make_scene([(4, (0.8, 0.5)), (5, (0.5, 0.9))])
    _feed(proposer, _make_hand_track((0.2, 0.5), (0.6, 0.5)))

    proposal = proposer.propose(scene)

    assert proposal.action == ActionType.CLEAR_SPECIFIC
    assert "delivery_zone_name" in proposal.metadata
    assert "delivery_zone_xyz" in proposal.metadata
    assert len(proposal.metadata["delivery_zone_xyz"]) == 3


def test_no_objects_yields_fall_through_even_if_reaching():
    proposer = ReachIntentProposer()
    scene = _make_scene([])
    _feed(proposer, _make_hand_track((0.2, 0.5), (0.6, 0.5)))

    proposal = proposer.propose(scene)

    assert proposal.action == ActionType.IDLE
    assert proposal.confidence == 0.0


def test_target_object_id_matches_scene_object():
    proposer = ReachIntentProposer()
    scene = _make_scene([(7, (0.85, 0.5)), (9, (0.5, 0.85))])
    _feed(proposer, _make_hand_track((0.2, 0.5), (0.6, 0.5)))

    decision = proposer.estimate(scene)

    assert decision.target_object_id in {7, 9}
