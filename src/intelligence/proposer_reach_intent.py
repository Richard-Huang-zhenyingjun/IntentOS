"""
Reach-intent proposer.

Turns an implicit reaching gesture into an IntentProposal that flows through the
same proposer -> registry -> authorization -> execution spine as every other
proposer. It is not a bypass path: it only ever emits a proposal, never touches
the arm.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional, Tuple

from src.interfaces.hand_state import HandState
from src.interfaces.intent_proposal import ActionType, IntentProposal
from src.interfaces.proposer_base import ProposerBase
from src.interfaces.scene_summary import SceneSummary


MIN_REACH_SPEED = 0.15
ONSET_COMMIT_FRAMES = 3
RETRACT_FRAMES = 22
HISTORY_LEN = 30

W_ALIGNMENT = 0.10
W_PROXIMITY = 0.75
W_CLOSING = 0.05
W_DETECT = 0.10
PROXIMITY_SIGMA = 0.10

AMBIGUITY_GAP = 0.08
CONF_AMBIGUOUS = 0.5
CONF_CONFIDENT = 0.85

DEFAULT_DELIVERY_ZONE_NAME = "user_delivery_zone"
DEFAULT_DELIVERY_ZONE_XYZ = (0.15, 0.0, 0.65)


class _OnsetState:
    IDLE = "idle"
    POSSIBLE = "possible_reach"
    COMMITTED = "committed_reach"


@dataclass
class ReachDecision:
    """Internal decision object, useful for tests and logging."""

    target_object_id: Optional[int]
    confidence: float
    alternatives: List[Tuple[int, float]]
    ambiguity: float
    reason: str
    committed: bool


def _unit(v: Tuple[float, float]) -> Tuple[float, float]:
    x, y = v
    n = math.hypot(x, y)
    if n < 1e-9:
        return (0.0, 0.0)
    return (x / n, y / n)


def _dot(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _dist_point_to_point(
    a: Tuple[float, float],
    b: Tuple[float, float],
) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _softmax(scores: List[float]) -> List[float]:
    if not scores:
        return []
    m = max(scores)
    exps = [math.exp(score - m) for score in scores]
    total = sum(exps)
    if total < 1e-12:
        return [1.0 / len(scores)] * len(scores)
    return [value / total for value in exps]


class ReachIntentProposer(ProposerBase):
    """
    Proposes assistive-reach actions from hand trajectory plus scene objects.

    Call update_hand(hand_state) once per frame. propose(scene) remains the
    normal ProposerBase entry point and returns an IntentProposal.
    """

    def __init__(
        self,
        config: Optional[dict] = None,
        delivery_zone_name: str = DEFAULT_DELIVERY_ZONE_NAME,
        delivery_zone_xyz: Tuple[float, float, float] = DEFAULT_DELIVERY_ZONE_XYZ,
    ):
        cfg = config or {}
        reach_cfg = cfg.get("reach_intent", {})
        self._min_reach_speed = reach_cfg.get("min_reach_speed", MIN_REACH_SPEED)
        self._commit_frames = reach_cfg.get("onset_commit_frames", ONSET_COMMIT_FRAMES)
        self._retract_frames = reach_cfg.get("retract_frames", RETRACT_FRAMES)
        self._history_len = reach_cfg.get("history_len", HISTORY_LEN)
        self._ambiguity_gap = reach_cfg.get("ambiguity_gap", AMBIGUITY_GAP)

        self._delivery_zone_name = delivery_zone_name
        self._delivery_zone_xyz = tuple(delivery_zone_xyz)

        self._history: Deque[HandState] = deque(maxlen=self._history_len)
        self._onset = _OnsetState.IDLE
        self._reach_streak = 0
        self._slow_streak = 0

    def name(self) -> str:
        return "reach_intent"

    def is_available(self) -> bool:
        return True

    def update_hand(self, hand: HandState) -> None:
        """Push one frame of hand state into the side-channel buffer."""

        self._history.append(hand)

        reaching = hand.hand_present and hand.speed >= self._min_reach_speed
        if reaching:
            self._reach_streak += 1
            self._slow_streak = 0
        else:
            self._slow_streak += 1
            self._reach_streak = 0

        if self._onset == _OnsetState.IDLE:
            if self._reach_streak >= 1:
                self._onset = _OnsetState.POSSIBLE
        elif self._onset == _OnsetState.POSSIBLE:
            if self._reach_streak >= self._commit_frames:
                self._onset = _OnsetState.COMMITTED
            elif self._slow_streak >= self._retract_frames:
                self._onset = _OnsetState.IDLE
        elif self._onset == _OnsetState.COMMITTED:
            if self._slow_streak >= self._retract_frames:
                self._onset = _OnsetState.IDLE

    def committed(self) -> bool:
        return self._onset == _OnsetState.COMMITTED

    def reset(self) -> None:
        self._history.clear()
        self._onset = _OnsetState.IDLE
        self._reach_streak = 0
        self._slow_streak = 0

    def estimate(self, scene: SceneSummary) -> ReachDecision:
        """Estimate the target object from the hand buffer and scene objects."""

        if self._onset != _OnsetState.COMMITTED:
            return ReachDecision(
                target_object_id=None,
                confidence=0.0,
                alternatives=[],
                ambiguity=0.0,
                reason="no_committed_reach",
                committed=False,
            )

        objects = list(scene.objects_on_table) or list(scene.objects)
        if not objects:
            return ReachDecision(
                target_object_id=None,
                confidence=0.0,
                alternatives=[],
                ambiguity=0.0,
                reason="no_objects",
                committed=True,
            )

        hand = self._history[-1] if self._history else None
        if hand is None or not hand.hand_present:
            return ReachDecision(
                target_object_id=None,
                confidence=0.0,
                alternatives=[],
                ambiguity=0.0,
                reason="no_hand",
                committed=True,
            )

        origin = hand.index_tip_xy
        direction = _unit(hand.reach_direction_xy)
        velocity = hand.velocity_xy

        raw_scores: List[float] = []
        for obj in objects:
            obj_xy = (obj.pos_xyz[0], obj.pos_xyz[1])
            to_obj = _unit((obj_xy[0] - origin[0], obj_xy[1] - origin[1]))
            alignment = max(0.0, _dot(direction, to_obj))
            proximity_distance = _dist_point_to_point(obj_xy, origin)
            proximity_term = math.exp(-proximity_distance / PROXIMITY_SIGMA)
            closing = max(0.0, _dot(velocity, to_obj))
            closing_term = min(1.0, closing / max(self._min_reach_speed, 1e-6))
            score = (
                W_ALIGNMENT * alignment
                + W_PROXIMITY * proximity_term
                + W_CLOSING * closing_term
                + W_DETECT * obj.confidence
            )
            raw_scores.append(score)

        probabilities = _softmax(raw_scores)
        ranked = sorted(
            zip((obj.object_id for obj in objects), probabilities),
            key=lambda item: item[1],
            reverse=True,
        )
        top_id, top_probability = ranked[0]
        second_probability = ranked[1][1] if len(ranked) > 1 else 0.0
        gap = top_probability - second_probability

        if gap < self._ambiguity_gap:
            return ReachDecision(
                target_object_id=top_id,
                confidence=CONF_AMBIGUOUS,
                alternatives=ranked[:3],
                ambiguity=1.0 - gap,
                reason="ambiguous_target",
                committed=True,
            )

        return ReachDecision(
            target_object_id=top_id,
            confidence=CONF_CONFIDENT,
            alternatives=ranked[:3],
            ambiguity=1.0 - gap,
            reason="reach_points_to_object",
            committed=True,
        )

    def propose(self, scene: SceneSummary) -> IntentProposal:
        decision = self.estimate(scene)

        if not decision.committed or decision.target_object_id is None:
            return IntentProposal(
                action=ActionType.IDLE,
                description="no assistive reach",
                source="reach_intent",
                confidence=0.0,
                metadata={"reason": decision.reason},
            )

        target = decision.target_object_id
        return IntentProposal(
            action=ActionType.CLEAR_SPECIFIC,
            description=f"bring object {target} closer",
            source="reach_intent",
            confidence=decision.confidence,
            suggested_object_ids=[target],
            metadata={
                "assist_action": "bring_closer",
                "target_object_id": target,
                "alternatives": decision.alternatives,
                "ambiguity": decision.ambiguity,
                "reason": decision.reason,
                "requires_confirmation": True,
                "delivery_zone_name": self._delivery_zone_name,
                "delivery_zone_xyz": self._delivery_zone_xyz,
            },
        )
