"""
Frozen hand-state contract for reach-intent inference.

This is the one genuinely new type the reach module needs. Object positions
already come from scene_summary.ObjectInfo; only hand tracking has no existing
type in the contracts.

Coordinate convention:
- All positions are in the image plane, normalized [0, 1] x [0, 1], origin
  top-left.
- This deliberately keeps V0 2D. Depth is a later upgrade, not a V0 dependency.
"""
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class HandState:
    """
    Immutable single-frame hand observation.

    Produced once per camera frame by the capture loop, then pushed into the
    reach proposer's internal buffer via update_hand().
    """

    timestamp_s: float
    wrist_xy: Tuple[float, float]
    index_tip_xy: Tuple[float, float]
    thumb_tip_xy: Tuple[float, float]
    velocity_xy: Tuple[float, float]
    speed: float
    reach_direction_xy: Tuple[float, float]
    grasp_aperture: float
    detection_confidence: float = 1.0
    hand_present: bool = True

    @staticmethod
    def absent(timestamp_s: float) -> "HandState":
        """Construct a no-hand-detected observation."""

        return HandState(
            timestamp_s=timestamp_s,
            wrist_xy=(0.0, 0.0),
            index_tip_xy=(0.0, 0.0),
            thumb_tip_xy=(0.0, 0.0),
            velocity_xy=(0.0, 0.0),
            speed=0.0,
            reach_direction_xy=(0.0, 0.0),
            grasp_aperture=0.0,
            detection_confidence=0.0,
            hand_present=False,
        )
