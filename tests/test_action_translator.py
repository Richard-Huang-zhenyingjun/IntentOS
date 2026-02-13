"""
Tests for OpenVLA -> robot joint action translation.

Run: pytest tests/test_action_translator.py -v
"""
from __future__ import annotations

import os

import numpy as np
import pytest

from src.external.openvla.action_translator import TranslatedAction
from src.external.openvla.action_translator_fake import FakeActionTranslator


class TestTranslatedAction:
    def test_fields(self):
        action = TranslatedAction(
            joint_positions=np.zeros(7),
            gripper_command=0.5,
            target_ee_position=np.array([0.5, 0.0, 0.5]),
            target_ee_rotation=np.eye(3),
            ik_success=True,
            ik_error=0.001,
            clamped=False,
        )
        assert action.joint_positions.shape == (7,)
        assert action.ik_success is True
        assert action.ik_error < 0.01

    def test_gripper_range(self):
        action = TranslatedAction(
            joint_positions=np.zeros(7),
            gripper_command=0.0,
            target_ee_position=np.zeros(3),
            target_ee_rotation=np.eye(3),
            ik_success=True,
            ik_error=0.0,
            clamped=False,
        )
        assert 0.0 <= action.gripper_command <= 1.0


class TestFakeTranslator:
    @pytest.fixture
    def translator(self):
        return FakeActionTranslator(num_joints=7)

    def test_translate_returns_valid_action(self, translator):
        result = translator.translate(
            delta_position=np.array([0.01, 0.0, -0.02]),
            delta_rotation=np.array([0.0, 0.0, 0.0]),
            gripper=0.0,
        )
        assert isinstance(result, TranslatedAction)
        assert result.joint_positions.shape == (7,)
        assert result.ik_success is True

    def test_zero_deltas_produce_near_zero_joints(self, translator):
        result = translator.translate(
            delta_position=np.zeros(3),
            delta_rotation=np.zeros(3),
            gripper=0.5,
        )
        assert np.allclose(result.joint_positions, 0.0, atol=0.01)

    def test_nonzero_deltas_move_joints(self, translator):
        result = translator.translate(
            delta_position=np.array([0.05, 0.0, -0.03]),
            delta_rotation=np.array([0.1, 0.0, 0.0]),
            gripper=0.0,
        )
        assert not np.allclose(result.joint_positions, 0.0)

    def test_gripper_passthrough(self, translator):
        close = translator.translate(np.zeros(3), np.zeros(3), gripper=0.0)
        assert close.gripper_command == 0.0

        open_ = translator.translate(np.zeros(3), np.zeros(3), gripper=1.0)
        assert open_.gripper_command == 1.0

    def test_gripper_clamped(self, translator):
        result = translator.translate(np.zeros(3), np.zeros(3), gripper=5.0)
        assert result.gripper_command == 1.0

        result = translator.translate(np.zeros(3), np.zeros(3), gripper=-2.0)
        assert result.gripper_command == 0.0

    def test_translate_from_metadata(self, translator):
        meta = {
            "delta_position": [0.01, 0.0, -0.02],
            "delta_rotation": [0.0, 0.0, 0.0],
            "gripper": 0.0,
        }
        result = translator.translate_from_metadata(meta)
        assert isinstance(result, TranslatedAction)
        assert result.joint_positions.shape == (7,)

    def test_trajectory_translation(self, translator):
        actions = [
            {"delta_position": [0.01, 0, -0.01], "delta_rotation": [0, 0, 0], "gripper": 1.0},
            {"delta_position": [0.01, 0, -0.01], "delta_rotation": [0, 0, 0], "gripper": 1.0},
            {"delta_position": [0, 0, -0.02], "delta_rotation": [0, 0, 0], "gripper": 0.0},
            {"delta_position": [0, 0, 0.03], "delta_rotation": [0, 0, 0], "gripper": 0.0},
        ]
        trajectory = translator.translate_trajectory(actions)
        assert len(trajectory) == 4
        assert all(isinstance(a, TranslatedAction) for a in trajectory)
        assert trajectory[2].gripper_command == 0.0

    def test_trajectory_max_steps_limit(self, translator):
        actions = [
            {"delta_position": [0.01, 0, 0], "delta_rotation": [0, 0, 0], "gripper": 0.5}
        ] * 100
        trajectory = translator.translate_trajectory(actions, max_steps=10)
        assert len(trajectory) == 10

    def test_no_nan_in_output(self, translator):
        for _ in range(20):
            dp = np.random.uniform(-0.05, 0.05, 3)
            dr = np.random.uniform(-0.2, 0.2, 3)
            g = np.random.uniform(0, 1)
            result = translator.translate(dp, dr, g)
            assert not np.any(np.isnan(result.joint_positions))
            assert not np.any(np.isinf(result.joint_positions))

    def test_call_count(self, translator):
        assert translator.call_count == 0
        translator.translate(np.zeros(3), np.zeros(3), 0.5)
        translator.translate(np.zeros(3), np.zeros(3), 0.5)
        assert translator.call_count == 2


class TestRealTranslator:
    """Tests requiring MuJoCo + messy_table model."""

    @pytest.fixture
    def mujoco_env(self):
        try:
            import mujoco
        except ImportError:
            pytest.skip("MuJoCo not installed")

        model_path = os.path.join("models", "kuka_iiwa", "messy_table.xml")
        if not os.path.exists(model_path):
            pytest.skip(f"Model not found: {model_path}")

        model = mujoco.MjModel.from_xml_path(model_path)
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        return model, data

    @pytest.fixture
    def translator(self, mujoco_env):
        from src.external.openvla.action_translator import ActionTranslator

        model, data = mujoco_env
        return ActionTranslator(model, data)

    def test_small_delta_succeeds(self, translator):
        result = translator.translate(
            delta_position=np.array([0.01, 0.0, 0.0]),
            delta_rotation=np.zeros(3),
            gripper=0.5,
        )
        assert result.ik_success, f"IK failed with error {result.ik_error}"
        assert result.joint_positions.shape == (7,)

    def test_zero_delta_stays_in_place(self, translator):
        result = translator.translate(
            delta_position=np.zeros(3),
            delta_rotation=np.zeros(3),
            gripper=0.5,
        )
        assert result.ik_success
        assert result.ik_error < 0.01

    def test_large_delta_clamped(self, translator):
        result = translator.translate(
            delta_position=np.array([1.0, 1.0, 1.0]),
            delta_rotation=np.zeros(3),
            gripper=0.5,
        )
        # Relative movement should be clipped to <= 5cm per axis.
        mujoco_target_delta = result.target_ee_position - np.array([0.0, 0.0, 0.0])
        assert np.all(np.abs(mujoco_target_delta) < 5.0)

    def test_joint_limits_respected(self, translator, mujoco_env):
        model, _ = mujoco_env
        result = translator.translate(
            delta_position=np.array([0.03, -0.02, 0.01]),
            delta_rotation=np.array([0.05, 0.0, -0.05]),
            gripper=0.0,
        )
        for i in range(min(7, model.njnt)):
            if model.jnt_limited[i]:
                assert result.joint_positions[i] >= model.jnt_range[i, 0] - 0.01
                assert result.joint_positions[i] <= model.jnt_range[i, 1] + 0.01

    def test_repeated_small_deltas_stable(self, translator):
        for step in range(20):
            dp = np.random.uniform(-0.01, 0.01, 3)
            dr = np.random.uniform(-0.05, 0.05, 3)
            result = translator.translate(dp, dr, gripper=0.5)
            assert not np.any(np.isnan(result.joint_positions)), f"NaN at step {step}"
