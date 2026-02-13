"""
Week 3 Smoke Test — Action translation + MuJoCo execution pipeline.

Run: python scripts/week3_smoke_test.py
"""
from __future__ import annotations

import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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


def _setup():
    from src.robot.mujoco.mujoco_simulator import MuJoCoSimulator, MuJoCoConfig
    from src.robot.mujoco.mujoco_controller import MuJoCoController
    from src.external.openvla.action_translator import ActionTranslator

    model_path = os.path.join("models", "kuka_iiwa", "messy_table.xml")
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model not found: {model_path}")

    sim = MuJoCoSimulator(MuJoCoConfig(model_path=model_path, use_gui=False))
    sim.load_robot()
    controller = MuJoCoController(sim)
    translator = ActionTranslator(sim._model, sim._data)
    return sim, controller, translator


def test_execution_pipeline():
    print("\n" + "=" * 60)
    print("TEST 1: Execution Pipeline (Translate -> Execute -> Verify)")
    print("=" * 60)

    sim, controller, translator = _setup()
    try:
        ee_start, _ = sim.get_end_effector_pose()
        print(f"  Initial EE position: {ee_start}")

        action = {
            "delta_position": [0.03, 0.01, -0.02],
            "delta_rotation": [0.0, 0.0, 0.05],
            "gripper": 0.0,
        }
        translated = translator.translate_from_metadata(action)
        print(f"  IK: success={translated.ik_success}, error={translated.ik_error:.4f}m")
        assert translated.ik_success, "IK failed"

        converged = controller.move_to_joint_positions(translated.joint_positions)
        ee_end, _ = sim.get_end_effector_pose()
        displacement = np.linalg.norm(ee_end - ee_start)
        print(f"  Converged={converged}, displacement={displacement:.4f}m")
        assert displacement > 0.005, "Arm didn't move"
    finally:
        sim.close()

    print("  PASS")


def test_proposal_to_execution():
    print("\n" + "=" * 60)
    print("TEST 2: Proposal -> Translation -> Execution")
    print("=" * 60)

    from src.external.openvla.adapter_fake import FakeOpenVLAAdapter
    from src.external.openvla.proposer_openvla import OpenVLAProposer

    sim, controller, translator = _setup()
    try:
        adapter = FakeOpenVLAAdapter()
        adapter.load_model()
        proposer = OpenVLAProposer(adapter, camera_provider=sim, camera_name="overhead")

        proposal = proposer.propose(_scene_summary())
        assert proposal is not None, "No proposal returned"
        translated = translator.translate_from_metadata(proposal.metadata)
        assert translated.ik_success, f"IK failed: {translated.ik_error:.4f}"

        ee_before, _ = sim.get_end_effector_pose()
        converged = controller.move_to_joint_positions(translated.joint_positions)
        ee_after, _ = sim.get_end_effector_pose()
        displacement = np.linalg.norm(ee_after - ee_before)
        print(f"  converged={converged}, displacement={displacement:.4f}m")
    finally:
        sim.close()

    print("  PASS")


def test_multi_step_trajectory():
    print("\n" + "=" * 60)
    print("TEST 3: Multi-Step Trajectory (5 actions)")
    print("=" * 60)

    sim, controller, translator = _setup()
    try:
        ee_start, _ = sim.get_end_effector_pose()
        trajectory = [
            {"delta_position": [0.02, 0.0, 0.0], "delta_rotation": [0, 0, 0], "gripper": 1.0},
            {"delta_position": [0.02, 0.0, 0.0], "delta_rotation": [0, 0, 0], "gripper": 1.0},
            {"delta_position": [0.0, 0.0, -0.03], "delta_rotation": [0, 0, 0], "gripper": 1.0},
            {"delta_position": [0.0, 0.0, 0.0], "delta_rotation": [0, 0, 0], "gripper": 0.0},
            {"delta_position": [0.0, 0.0, 0.05], "delta_rotation": [0, 0, 0], "gripper": 0.0},
        ]

        for i, action in enumerate(trajectory):
            translated = translator.translate_from_metadata(action)
            if translated.ik_success:
                converged = controller.move_to_joint_positions(translated.joint_positions)
                ee, _ = sim.get_end_effector_pose()
                print(f"  Step {i}: ee={ee[:2]}..., converged={converged}")
            else:
                print(f"  Step {i}: IK failed ({translated.ik_error:.4f}m)")

        ee_end, _ = sim.get_end_effector_pose()
        total_disp = np.linalg.norm(ee_end - ee_start)
        print(f"  Total displacement: {total_disp:.4f}m")
        joints = sim.get_joint_positions()
        assert not np.any(np.isnan(joints)), "NaN in joints!"
        assert not np.any(np.isinf(joints)), "Inf in joints!"
    finally:
        sim.close()

    print("  PASS")


def main():
    print("=" * 60)
    print("WEEK 3 SMOKE TEST")
    print("=" * 60)
    try:
        test_execution_pipeline()
        test_proposal_to_execution()
        test_multi_step_trajectory()
        print("\nALL WEEK 3 SMOKE TESTS PASSED")
        return 0
    except Exception as exc:
        print(f"\nSMOKE TEST FAILED: {exc}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
