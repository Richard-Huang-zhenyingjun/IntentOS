"""
Action Translator — converts OpenVLA actions to robot joint commands.

OpenVLA outputs:  [dx, dy, dz, droll, dpitch, dyaw, gripper]
                  (delta end-effector in Cartesian space)

Robot needs:      [j1, j2, j3, j4, j5, j6, j7]
                  (absolute joint positions in radians)

Translation pipeline:
  1. Get current EE pose from simulator
  2. Apply OpenVLA deltas -> target EE pose
  3. Solve IK (target EE pose -> joint positions)
  4. Clamp to joint limits
  5. Return joint positions + gripper command
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import mujoco
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TranslatedAction:
    """Result of translating an OpenVLA action to robot commands."""

    joint_positions: np.ndarray
    gripper_command: float
    target_ee_position: np.ndarray
    target_ee_rotation: np.ndarray
    ik_success: bool
    ik_error: float
    clamped: bool


class ActionTranslator:
    """
    Translates OpenVLA delta actions to absolute joint commands.

    Requires MuJoCo model/data to read EE pose, compute Jacobians, and solve IK.
    """

    def __init__(
        self,
        model: mujoco.MjModel,
        data: mujoco.MjData,
        ee_site_name: str = "end_effector",
        ik_max_iterations: int = 100,
        ik_tolerance: float = 0.005,
        ik_step_size: float = 0.5,
        position_delta_limit: float = 0.05,
        rotation_delta_limit: float = 0.25,
    ):
        self._model = model
        self._data = data
        self._ee_site_name = ee_site_name
        self._ik_max_iter = ik_max_iterations
        self._ik_tol = ik_tolerance
        self._ik_step = ik_step_size
        self._pos_limit = position_delta_limit
        self._rot_limit = rotation_delta_limit

        self._ee_site_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_SITE, ee_site_name
        )
        if self._ee_site_id < 0:
            raise ValueError(f"Site '{ee_site_name}' not found in model")

        self._num_joints = model.nu
        self._joint_limits_low = np.zeros(self._num_joints)
        self._joint_limits_high = np.zeros(self._num_joints)
        for i in range(self._num_joints):
            joint_id = model.actuator_trnid[i, 0]
            if model.jnt_limited[joint_id]:
                self._joint_limits_low[i] = model.jnt_range[joint_id, 0]
                self._joint_limits_high[i] = model.jnt_range[joint_id, 1]
            else:
                self._joint_limits_low[i] = -np.pi
                self._joint_limits_high[i] = np.pi

        logger.info(
            "ActionTranslator initialized: site='%s', joints=%d, ik_tol=%.4fm",
            ee_site_name,
            self._num_joints,
            ik_tolerance,
        )

    def translate(
        self,
        delta_position: np.ndarray,
        delta_rotation: np.ndarray,
        gripper: float,
    ) -> TranslatedAction:
        """
        Translate OpenVLA delta action to absolute joint commands.
        """
        dp = np.clip(delta_position, -self._pos_limit, self._pos_limit)
        dr = np.clip(delta_rotation, -self._rot_limit, self._rot_limit)

        mujoco.mj_forward(self._model, self._data)
        current_pos = self._data.site_xpos[self._ee_site_id].copy()
        current_rot = self._data.site_xmat[self._ee_site_id].reshape(3, 3).copy()

        target_pos = current_pos + dp
        dR = self._rotation_vector_to_matrix(dr)
        target_rot = dR @ current_rot

        joint_positions, ik_success, ik_error = self._solve_ik(target_pos, target_rot)

        clamped_positions = np.clip(
            joint_positions, self._joint_limits_low, self._joint_limits_high
        )
        was_clamped = not np.allclose(joint_positions, clamped_positions, atol=1e-6)
        if was_clamped:
            logger.debug("Joint limits reached - clamped to bounds")

        return TranslatedAction(
            joint_positions=clamped_positions,
            gripper_command=float(np.clip(gripper, 0.0, 1.0)),
            target_ee_position=target_pos,
            target_ee_rotation=target_rot,
            ik_success=ik_success,
            ik_error=ik_error,
            clamped=was_clamped,
        )

    def translate_from_metadata(self, metadata: dict) -> TranslatedAction:
        """
        Translate directly from an IntentProposal metadata dict.
        """
        dp = np.array(metadata["delta_position"], dtype=np.float64)
        dr = np.array(metadata["delta_rotation"], dtype=np.float64)
        gripper = float(metadata["gripper"])
        return self.translate(dp, dr, gripper)

    def translate_trajectory(
        self, actions: list[dict], max_steps: int = 50
    ) -> list[TranslatedAction]:
        """
        Translate a sequence of OpenVLA actions (trajectory).
        """
        trajectory: list[TranslatedAction] = []
        for i, action in enumerate(actions[:max_steps]):
            translated = self.translate_from_metadata(action)
            trajectory.append(translated)

            if not translated.ik_success:
                logger.warning("IK failed at trajectory step %d, truncating", i)
                break

            self._data.ctrl[: self._num_joints] = translated.joint_positions
            mujoco.mj_step(self._model, self._data)

        return trajectory

    def _solve_ik(
        self,
        target_pos: np.ndarray,
        target_rot: np.ndarray,
    ) -> tuple[np.ndarray, bool, float]:
        """
        Solve inverse kinematics using damped least-squares Jacobian pseudoinverse.
        """
        saved_qpos = self._data.qpos.copy()
        saved_qvel = self._data.qvel.copy()
        saved_ctrl = self._data.ctrl.copy()

        jacp = np.zeros((3, self._model.nv))
        jacr = np.zeros((3, self._model.nv))

        best_error = float("inf")
        best_qpos = saved_qpos[: self._num_joints].copy()

        for _ in range(self._ik_max_iter):
            mujoco.mj_forward(self._model, self._data)

            current_pos = self._data.site_xpos[self._ee_site_id]
            current_rot = self._data.site_xmat[self._ee_site_id].reshape(3, 3)

            pos_error = target_pos - current_pos
            pos_error_norm = np.linalg.norm(pos_error)

            rot_error = self._rotation_error(current_rot, target_rot)
            rot_error_norm = np.linalg.norm(rot_error)

            total_error = pos_error_norm + 0.1 * rot_error_norm
            if total_error < best_error:
                best_error = total_error
                best_qpos = self._data.qpos[: self._num_joints].copy()

            if pos_error_norm < self._ik_tol:
                self._data.qpos[:] = saved_qpos
                self._data.qvel[:] = saved_qvel
                self._data.ctrl[:] = saved_ctrl
                mujoco.mj_forward(self._model, self._data)
                return best_qpos, True, pos_error_norm

            mujoco.mj_jacSite(self._model, self._data, jacp, jacr, self._ee_site_id)

            J_pos = jacp[:, : self._num_joints]
            J_rot = jacr[:, : self._num_joints]

            error_vec = np.concatenate([pos_error, 0.1 * rot_error])
            J = np.vstack([J_pos, 0.1 * J_rot])

            lambda_sq = 1e-4
            JJT = J @ J.T + lambda_sq * np.eye(6)
            dq = J.T @ np.linalg.solve(JJT, error_vec)

            self._data.qpos[: self._num_joints] += self._ik_step * dq

        self._data.qpos[:] = saved_qpos
        self._data.qvel[:] = saved_qvel
        self._data.ctrl[:] = saved_ctrl
        mujoco.mj_forward(self._model, self._data)

        logger.debug(
            "IK finished: %d iterations, error=%.4fm, success=%s",
            self._ik_max_iter,
            best_error,
            best_error < self._ik_tol * 5,
        )
        return best_qpos, best_error < self._ik_tol * 5, best_error

    @staticmethod
    def _rotation_vector_to_matrix(rotvec: np.ndarray) -> np.ndarray:
        """Convert axis-angle vector to 3x3 rotation matrix."""
        angle = np.linalg.norm(rotvec)
        if angle < 1e-10:
            return np.eye(3)

        axis = rotvec / angle
        K = np.array(
            [
                [0, -axis[2], axis[1]],
                [axis[2], 0, -axis[0]],
                [-axis[1], axis[0], 0],
            ]
        )
        return np.eye(3) + np.sin(angle) * K + (1 - np.cos(angle)) * (K @ K)

    @staticmethod
    def _rotation_error(R_current: np.ndarray, R_target: np.ndarray) -> np.ndarray:
        """
        Compute rotation error as axis-angle vector.
        """
        R_err = R_target @ R_current.T
        angle = np.arccos(np.clip((np.trace(R_err) - 1) / 2, -1, 1))
        if angle < 1e-10:
            return np.zeros(3)

        axis = np.array(
            [
                R_err[2, 1] - R_err[1, 2],
                R_err[0, 2] - R_err[2, 0],
                R_err[1, 0] - R_err[0, 1],
            ]
        ) / (2 * np.sin(angle) + 1e-10)
        return angle * axis
