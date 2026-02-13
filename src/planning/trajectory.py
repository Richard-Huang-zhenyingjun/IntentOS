import numpy as np
from dataclasses import dataclass
from typing import List, Optional


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
    ) -> List[Waypoint]:
        import pybullet as p

        if num_waypoints is None:
            num_waypoints = max(1, int(self.duration / self.timestep))

        waypoints: List[Waypoint] = []
        for i in range(num_waypoints + 1):
            t = i / num_waypoints
            t_smooth = self._smooth_step(t)
            cart_pos = start_cart + (end_cart - start_cart) * t_smooth
            try:
                ik = p.calculateInverseKinematics(
                    bodyUniqueId=robot_id,
                    endEffectorLinkIndex=ee_link_index,
                    targetPosition=cart_pos.tolist(),
                    maxNumIterations=100,
                    residualThreshold=0.001,
                )
            except TypeError:
                ik = p.calculateInverseKinematics(
                    bodyUniqueId=robot_id,
                    endEffectorLinkIndex=ee_link_index,
                    targetPosition=cart_pos.tolist(),
                )
            waypoints.append(
                Waypoint(
                    joint_positions=np.array(ik[:joint_count], dtype=float),
                    time=t * self.duration,
                )
            )
        return waypoints
