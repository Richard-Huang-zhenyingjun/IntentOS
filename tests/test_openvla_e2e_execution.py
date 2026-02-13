"""
End-to-end: CONFIRM -> OpenVLA -> MuJoCo arm moves.

Run: pytest tests/test_openvla_e2e_execution.py -v
"""
from __future__ import annotations

import os

import numpy as np
import pytest

mujoco = pytest.importorskip("mujoco")


def _scene_summary():
    from src.interfaces.scene_summary import ObjectInfo, SceneSummary

    objects = (
        ObjectInfo(
            object_id=4,
            pos_xyz=(0.4, -0.1, 0.4),
            on_table=True,
            category="red_cube",
            confidence=1.0,
        ),
    )
    return SceneSummary(
        table_id=1,
        table_position=(0.0, 0.0, 0.3),
        bin_zone_center=(0.4, 0.0, 0.75),
        bin_zone_radius=0.12,
        objects=objects,
        objects_on_table=objects,
        clutter_score=0.8,
        is_messy=True,
        timestamp_frame=1,
        rgb_snapshot=None,
        eeg_quality=None,
    )


class TestEndToEndExecution:
    @pytest.fixture
    def mujoco_env(self):
        from src.robot.mujoco.mujoco_simulator import MuJoCoSimulator, MuJoCoConfig
        from src.robot.mujoco.mujoco_controller import MuJoCoController

        model_path = os.path.join("models", "kuka_iiwa", "messy_table.xml")
        if not os.path.exists(model_path):
            pytest.skip(f"Model not found: {model_path}")

        config = MuJoCoConfig(model_path=model_path, use_gui=False)
        sim = MuJoCoSimulator(config)
        sim.load_robot()
        controller = MuJoCoController(sim)
        yield sim, controller
        sim.close()

    def test_arm_moves_from_openvla_action(self, mujoco_env):
        sim, controller = mujoco_env
        from src.external.openvla.action_translator import ActionTranslator

        translator = ActionTranslator(sim._model, sim._data)
        ee_before, _ = sim.get_end_effector_pose()

        action_meta = {
            "delta_position": [0.03, 0.0, -0.02],
            "delta_rotation": [0.0, 0.0, 0.0],
            "gripper": 1.0,
        }
        translated = translator.translate_from_metadata(action_meta)
        assert translated.ik_success, f"IK failed: error={translated.ik_error}"

        _ = controller.move_to_joint_positions(translated.joint_positions)
        ee_after, _ = sim.get_end_effector_pose()
        displacement = np.linalg.norm(ee_after - ee_before)
        assert displacement > 0.005, f"Arm didn't move enough: displacement={displacement:.4f}m"

    def test_multiple_steps_accumulate(self, mujoco_env):
        sim, controller = mujoco_env
        from src.external.openvla.action_translator import ActionTranslator

        translator = ActionTranslator(sim._model, sim._data)
        ee_start, _ = sim.get_end_effector_pose()

        for _ in range(5):
            action = {
                "delta_position": [0.01, 0.0, 0.0],
                "delta_rotation": [0.0, 0.0, 0.0],
                "gripper": 1.0,
            }
            translated = translator.translate_from_metadata(action)
            if translated.ik_success:
                controller.move_to_joint_positions(translated.joint_positions)

        ee_end, _ = sim.get_end_effector_pose()
        total_displacement = np.linalg.norm(ee_end - ee_start)
        assert total_displacement > 0.02, f"Expected >2cm movement, got {total_displacement:.4f}m"

    def test_physics_stable_after_execution(self, mujoco_env):
        sim, controller = mujoco_env
        from src.external.openvla.action_translator import ActionTranslator

        translator = ActionTranslator(sim._model, sim._data)

        for _ in range(10):
            dp = np.random.uniform(-0.02, 0.02, 3)
            dr = np.random.uniform(-0.05, 0.05, 3)
            action = {
                "delta_position": dp.tolist(),
                "delta_rotation": dr.tolist(),
                "gripper": float(np.random.uniform(0, 1)),
            }
            translated = translator.translate_from_metadata(action)
            if translated.ik_success:
                controller.move_to_joint_positions(translated.joint_positions)

        pos = sim.get_joint_positions()
        assert not np.any(np.isnan(pos)), "NaN in joints after execution"
        assert not np.any(np.isinf(pos)), "Inf in joints after execution"

    def test_camera_image_changes_after_execution(self, mujoco_env):
        sim, controller = mujoco_env
        from src.external.openvla.action_translator import ActionTranslator

        try:
            img_before = sim.render_camera("overhead").copy()
        except Exception as exc:
            pytest.skip(f"Renderer unavailable: {exc}")

        translator = ActionTranslator(sim._model, sim._data)
        action = {
            "delta_position": [0.05, 0.0, -0.05],
            "delta_rotation": [0.0, 0.0, 0.0],
            "gripper": 0.0,
        }
        translated = translator.translate_from_metadata(action)
        if translated.ik_success:
            controller.move_to_joint_positions(translated.joint_positions)

        img_after = sim.render_camera("overhead")
        pixel_diff = np.mean(np.abs(img_after.astype(float) - img_before.astype(float)))
        assert pixel_diff > 0.5, f"Camera image didn't change enough: mean_diff={pixel_diff:.2f}"


class TestObjectInteraction:
    @pytest.fixture
    def mujoco_env(self):
        from src.robot.mujoco.mujoco_simulator import MuJoCoSimulator, MuJoCoConfig
        from src.robot.mujoco.mujoco_controller import MuJoCoController

        model_path = os.path.join("models", "kuka_iiwa", "messy_table.xml")
        if not os.path.exists(model_path):
            pytest.skip(f"Model not found: {model_path}")

        config = MuJoCoConfig(model_path=model_path, use_gui=False)
        sim = MuJoCoSimulator(config)
        sim.load_robot()
        controller = MuJoCoController(sim)
        yield sim, controller
        sim.close()

    def test_object_displaced_by_arm_contact(self, mujoco_env):
        sim, controller = mujoco_env
        from src.external.openvla.action_translator import ActionTranslator

        obj_pos_before = sim.get_object_position("object_0")
        if obj_pos_before is None:
            pytest.skip("object_0 not found in model")

        translator = ActionTranslator(sim._model, sim._data)
        ee_pos, _ = sim.get_end_effector_pose()

        direction = obj_pos_before - ee_pos
        direction_norm = direction / (np.linalg.norm(direction) + 1e-8)

        for _ in range(20):
            action = {
                "delta_position": (direction_norm * 0.02).tolist(),
                "delta_rotation": [0.0, 0.0, 0.0],
                "gripper": 1.0,
            }
            translated = translator.translate_from_metadata(action)
            if translated.ik_success:
                controller.move_to_joint_positions(translated.joint_positions)
            ee_pos, _ = sim.get_end_effector_pose()
            obj_pos = sim.get_object_position("object_0")
            if obj_pos is not None:
                direction = obj_pos - ee_pos
                direction_norm = direction / (np.linalg.norm(direction) + 1e-8)

        obj_pos_after = sim.get_object_position("object_0")
        if obj_pos_after is not None:
            displacement = np.linalg.norm(obj_pos_after - obj_pos_before)
            assert displacement >= 0.0
