"""
Fake Action Translator for testing without MuJoCo.

Returns plausible joint positions without actual IK solving.
Used in unit tests that verify the execution pipeline logic
without requiring a loaded MuJoCo model.
"""
from __future__ import annotations

import numpy as np

from src.external.openvla.action_translator import TranslatedAction


class FakeActionTranslator:
    """
    Drop-in replacement for ActionTranslator in tests.

    Returns deterministic joint positions based on input deltas.
    Always reports IK success.
    """

    def __init__(self, num_joints: int = 7):
        self._num_joints = num_joints
        self._call_count = 0
        self._base_joints = np.zeros(num_joints)

    def translate(
        self,
        delta_position: np.ndarray,
        delta_rotation: np.ndarray,
        gripper: float,
    ) -> TranslatedAction:
        self._call_count += 1

        joint_deltas = np.zeros(self._num_joints)
        joint_deltas[0] = delta_position[1] * 2.0
        joint_deltas[1] = -delta_position[2] * 3.0
        joint_deltas[2] = delta_position[0] * 2.0
        joint_deltas[3] = delta_rotation[0] * 1.0
        joint_deltas[4] = delta_rotation[1] * 1.0
        joint_deltas[5] = delta_rotation[2] * 1.0
        joint_deltas[6] = 0.0

        self._base_joints += joint_deltas
        target = np.clip(self._base_joints, -2.9, 2.9)

        return TranslatedAction(
            joint_positions=target.copy(),
            gripper_command=float(np.clip(gripper, 0.0, 1.0)),
            target_ee_position=np.array([0.5, 0.0, 0.5]) + delta_position,
            target_ee_rotation=np.eye(3),
            ik_success=True,
            ik_error=0.001,
            clamped=False,
        )

    def translate_from_metadata(self, metadata: dict) -> TranslatedAction:
        dp = np.array(metadata["delta_position"], dtype=np.float64)
        dr = np.array(metadata["delta_rotation"], dtype=np.float64)
        gripper = float(metadata["gripper"])
        return self.translate(dp, dr, gripper)

    def translate_trajectory(
        self, actions: list[dict], max_steps: int = 50
    ) -> list[TranslatedAction]:
        return [self.translate_from_metadata(a) for a in actions[:max_steps]]

    @property
    def call_count(self) -> int:
        return self._call_count

    def reset(self):
        self._base_joints = np.zeros(self._num_joints)
        self._call_count = 0
