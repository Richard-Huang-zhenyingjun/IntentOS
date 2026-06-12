import numpy as np
from dataclasses import dataclass
from typing import List, Optional


class IKOutOfLimitsError(ValueError):
    """Raised when PyBullet IK returns an unreachable joint configuration."""


TOOL_OFFSET_M = 0.1


def get_ik_limits(
    robot_id: int,
    arm_joint_indices: list[int],
    rest_pose: Optional[list[float]] = None,
):
    """Return PyBullet null-space IK limits for the arm joints."""
    import pybullet as p

    lower, upper, ranges, rest = [], [], [], []
    for i, joint_idx in enumerate(arm_joint_indices):
        info = p.getJointInfo(robot_id, joint_idx)
        lo, hi = float(info[8]), float(info[9])
        lower.append(lo)
        upper.append(hi)
        ranges.append(hi - lo)
        if rest_pose is not None and i < len(rest_pose):
            rest.append(float(rest_pose[i]))
        else:
            rest.append(0.0)
    return lower, upper, ranges, rest


def normalize_ik_solution(
    ik,
    lower: list[float],
    upper: list[float],
    joint_count: int,
    rest_pose: Optional[list[float]] = None,
) -> list[float]:
    """Normalize revolute IK angles by 2*pi before limit checks."""
    import math

    normalized: list[float] = []
    for idx, q in enumerate(ik[:joint_count]):
        q = float(q)
        candidates = [q + k * 2.0 * math.pi for k in range(-2, 3)]
        in_range = [
            c
            for c in candidates
            if lower[idx] - 1e-9 <= c <= upper[idx] + 1e-9
        ]
        if in_range:
            if rest_pose is not None and idx < len(rest_pose):
                target = float(rest_pose[idx])
            else:
                target = 0.0
            q = min(in_range, key=lambda c: abs(c - target))
        normalized.append(q)
    return normalized


def validate_ik_solution(
    ik,
    lower: list[float],
    upper: list[float],
    joint_count: int,
    eps: float = 0.01,
) -> None:
    """Reject IK solutions that exceed joint limits."""
    for idx, q in enumerate(ik[:joint_count]):
        q = float(q)
        if q < lower[idx] - eps or q > upper[idx] + eps:
            raise IKOutOfLimitsError(
                f"joint {idx} q={q:.3f} outside "
                f"[{lower[idx]:.3f},{upper[idx]:.3f}]"
            )


def _tool_down_orientation_candidates():
    import math
    import pybullet as p

    offsets = []
    for yaw in (0.0, 0.4, -0.4, 0.8, -0.8, 1.2, -1.2, math.pi / 2.0, -math.pi / 2.0, math.pi):
        for roll_off, pitch_off in (
            (0.0, 0.0),
            (0.15, 0.0),
            (-0.15, 0.0),
            (0.0, 0.15),
            (0.0, -0.15),
            (0.15, 0.15),
            (0.15, -0.15),
            (-0.15, 0.15),
            (-0.15, -0.15),
            (0.30, 0.0),
            (-0.30, 0.0),
            (0.0, 0.30),
            (0.0, -0.30),
            (0.45, 0.0),
            (-0.45, 0.0),
            (0.0, 0.45),
            (0.0, -0.45),
            (0.45, 0.45),
            (0.45, -0.45),
            (-0.45, 0.45),
            (-0.45, -0.45),
        ):
            offsets.append((roll_off, pitch_off, yaw))
    return [
        (
            roll_off,
            pitch_off,
            yaw,
            p.getQuaternionFromEuler([math.pi + roll_off, pitch_off, yaw]),
        )
        for roll_off, pitch_off, yaw in offsets
    ]


def _compensated_link6_target(desired_link7_position, orientation) -> list[float]:
    """Return link6 target that places link7 at desired_link7_position."""
    import pybullet as p

    offset, _ = p.multiplyTransforms(
        [0.0, 0.0, 0.0],
        orientation,
        [0.0, 0.0, TOOL_OFFSET_M],
        [0.0, 0.0, 0.0, 1.0],
    )
    return [
        float(desired_link7_position[0]) - offset[0],
        float(desired_link7_position[1]) - offset[1],
        float(desired_link7_position[2]) - offset[2],
    ]


def calculate_limited_tool_down_ik(
    robot_id: int,
    ee_link_index: int,
    desired_link7_position,
    lower: list[float],
    upper: list[float],
    ranges: list[float],
    rest: list[float],
    joint_count: int,
):
    """Solve IK for link6 while placing the magnet/link7 at the target."""
    import pybullet as p

    errors: list[str] = []
    valid_candidates = []
    saved_joint_states = [
        p.getJointState(robot_id, joint_idx)[0]
        for joint_idx in range(p.getNumJoints(robot_id))
    ]
    for roll_off, pitch_off, yaw, orientation in _tool_down_orientation_candidates():
        link6_target = _compensated_link6_target(desired_link7_position, orientation)
        try:
            ik = p.calculateInverseKinematics(
                bodyUniqueId=robot_id,
                endEffectorLinkIndex=ee_link_index,
                targetPosition=link6_target,
                targetOrientation=orientation,
                lowerLimits=lower,
                upperLimits=upper,
                jointRanges=ranges,
                restPoses=rest,
                maxNumIterations=100,
                residualThreshold=0.001,
            )
        except TypeError:
            ik = p.calculateInverseKinematics(
                bodyUniqueId=robot_id,
                endEffectorLinkIndex=ee_link_index,
                targetPosition=link6_target,
                targetOrientation=orientation,
            )

        normalized = normalize_ik_solution(
            ik,
            lower,
            upper,
            joint_count,
            rest_pose=rest,
        )
        try:
            validate_ik_solution(normalized, lower, upper, joint_count)
        except IKOutOfLimitsError as exc:
            errors.append(str(exc))
            continue

        for joint_idx, joint_value in enumerate(normalized):
            p.resetJointState(robot_id, joint_idx, joint_value)
        link7_pos = p.getLinkState(
            robot_id,
            7,
            computeForwardKinematics=True,
        )[4]
        cartesian_error = sum(
            (float(link7_pos[i]) - float(desired_link7_position[i])) ** 2
            for i in range(3)
        ) ** 0.5
        for joint_idx, joint_value in enumerate(saved_joint_states):
            p.resetJointState(robot_id, joint_idx, joint_value)
        if cartesian_error > 0.04:
            errors.append(f"cartesian error {cartesian_error:.3f}m")
            continue

        joint_distance = sum(
            (float(q) - float(r)) ** 2
            for q, r in zip(normalized, rest[:joint_count])
        ) ** 0.5
        margins = [
            min(float(q) - lo, hi - float(q))
            for q, lo, hi in zip(normalized, lower, upper)
        ]
        min_margin = min(margins, default=0.0)
        margin_penalty = sum(
            max(0.0, 0.25 - margin) ** 2
            for margin in margins
        )
        tilt_penalty = abs(roll_off) + abs(pitch_off) + 0.1 * abs(yaw)
        cost = joint_distance + 8.0 * margin_penalty + 0.2 * tilt_penalty + 5.0 * cartesian_error
        valid_candidates.append(
            (
                cost,
                -min_margin,
                normalized,
                orientation,
                (roll_off, pitch_off, yaw),
                link6_target,
            )
        )

    if valid_candidates:
        _, _, normalized, orientation, offsets, link6_target = min(
            valid_candidates,
            key=lambda item: (item[0], item[1]),
        )
        return normalized, orientation, offsets, link6_target

    raise IKOutOfLimitsError(errors[-1] if errors else "no IK solution")


@dataclass
class Waypoint:
    """Single waypoint in joint space."""
    joint_positions: np.ndarray
    time: float


class TrajectoryInterpolator:
    """Generate smooth joint-space trajectories."""

    def __init__(self, duration: float = 2.0, timestep: float = 1.0 / 60.0):
        self.duration = duration
        self.timestep = timestep
        self.last_orientation = None
        self.last_orientation_offsets = None

    def interpolate(
        self,
        start_positions: np.ndarray,
        end_positions: np.ndarray,
        num_waypoints: Optional[int] = None,
    ) -> List[Waypoint]:
        if num_waypoints is None:
            num_waypoints = max(1, int(self.duration / self.timestep))

        waypoints: List[Waypoint] = []
        for i in range(num_waypoints + 1):
            t = i / num_waypoints
            t_smooth = self._smooth_step(t)
            positions = start_positions + (end_positions - start_positions) * t_smooth
            waypoints.append(Waypoint(joint_positions=positions, time=t * self.duration))
        return waypoints

    def _smooth_step(self, t: float) -> float:
        """Cubic ease-in-out."""
        return t * t * (3.0 - 2.0 * t)

    def interpolate_cartesian(
        self,
        robot_id: int,
        ee_link_index: int,
        joint_count: int,
        start_cart: np.ndarray,
        end_cart: np.ndarray,
        num_waypoints: Optional[int] = None,
        arm_joint_indices: Optional[list[int]] = None,
        rest_pose: Optional[list[float]] = None,
    ) -> List[Waypoint]:
        import pybullet as p

        if num_waypoints is None:
            num_waypoints = max(1, int(self.duration / self.timestep))

        if arm_joint_indices is None:
            arm_joint_indices = list(range(joint_count))
        lower, upper, ranges, rest = get_ik_limits(
            robot_id,
            arm_joint_indices,
            rest_pose=rest_pose,
        )

        ik, orientation, offsets, _ = calculate_limited_tool_down_ik(
            robot_id=robot_id,
            ee_link_index=ee_link_index,
            desired_link7_position=end_cart.tolist(),
            lower=lower,
            upper=upper,
            ranges=ranges,
            rest=rest,
            joint_count=joint_count,
        )
        self.last_orientation = orientation
        self.last_orientation_offsets = offsets
        return self.interpolate(
            start_positions=np.array(rest[:joint_count], dtype=float),
            end_positions=np.array(ik, dtype=float),
            num_waypoints=num_waypoints,
        )
