"""
MuJoCo motor controller.

Provides smooth position control for the KUKA IIWA arm in MuJoCo.
Unlike PyBullet, MuJoCo's built-in position actuators with PD gains
handle trajectory smoothing natively — no need for external interpolation.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from src.robot.mujoco.mujoco_simulator import MuJoCoSimulator

logger = logging.getLogger(__name__)


class MuJoCoController:
    """
    Position controller for MuJoCo robot arm.

    Key difference from PyBullet controller:
    - MuJoCo's position actuators have built-in PD control
    - We just set ctrl[] = target_positions
    - MuJoCo handles smooth convergence (no jitter!)
    - Convergence check: compare current positions to targets
    """

    def __init__(
        self,
        simulator: MuJoCoSimulator,
        convergence_threshold: float = 0.02,
        max_convergence_steps: int = 2000,
    ):
        self._sim = simulator
        self._convergence_threshold = convergence_threshold
        self._max_steps = max_convergence_steps

    def move_to_joint_positions(
        self,
        target_positions: np.ndarray,
        timeout_steps: Optional[int] = None,
    ) -> bool:
        """
        Command arm to target joint positions and wait for convergence.

        Args:
            target_positions: Target angles for each joint (radians).
            timeout_steps: Max physics steps to wait. None = use default.

        Returns:
            True if converged within timeout, False otherwise.
        """
        max_steps = timeout_steps or self._max_steps
        self._sim.set_joint_targets(target_positions)

        error = float("inf")
        for step in range(max_steps):
            self._sim.step()

            current = self._sim.get_joint_positions()[: len(target_positions)]
            error = np.max(np.abs(current - target_positions))

            if error < self._convergence_threshold:
                logger.debug("Converged in %d steps (error=%.4f)", step + 1, error)
                return True

        logger.warning(
            "Failed to converge after %d steps (error=%.4f, threshold=%.4f)",
            max_steps,
            error,
            self._convergence_threshold,
        )
        return False

    def move_end_effector_to(
        self,
        target_position: np.ndarray,
        target_orientation: Optional[np.ndarray] = None,
    ) -> bool:
        """
        Move end effector to a Cartesian target using IK.

        This is a placeholder for Week 3 when we integrate OpenVLA's
        delta EE commands. For now, use move_to_joint_positions().

        Args:
            target_position: [x, y, z] target in world frame.
            target_orientation: Optional quaternion [w, x, y, z].

        Returns:
            True if reached target.
        """
        raise NotImplementedError(
            "Cartesian control not yet implemented. Use move_to_joint_positions(). "
            "This will be implemented in Week 3 with OpenVLA integration."
        )

    def get_current_error(self) -> float:
        """Return max joint position error from current targets."""
        current = self._sim.get_joint_positions()
        targets = self._sim._data.ctrl[: self._sim.num_actuators]
        return float(np.max(np.abs(current[: len(targets)] - targets)))

    def is_stable(self, velocity_threshold: float = 0.01) -> bool:
        """Check if arm has settled (low velocity)."""
        velocities = self._sim.get_joint_velocities()
        return bool(np.max(np.abs(velocities)) < velocity_threshold)
