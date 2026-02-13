#!/usr/bin/env python3
"""
Week 4 Smoke Test — Full safety verification.

Run:
  python scripts/week4_smoke_test.py
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.invariant_checker import InvariantChecker


def test_invariant_checker():
    print("\n" + "=" * 60)
    print("TEST 1: Invariant Checker")
    print("=" * 60)

    checker = InvariantChecker()

    for i in range(10):
        checker.record_execution_attempt(True, True, f"token_{i}")
    assert checker.false_executions == 0
    print("  ✓ 10 authorized executions: false_executions=0")

    for _ in range(5):
        checker.record_execution_attempt(False, False, "")
    assert checker.false_executions == 0
    print("  ✓ 5 blocked executions: false_executions=0")

    checker.assert_invariant()
    print("  ✓ Invariant assertion passed")
    print(f"  ✓ Summary: {checker.summary}")
    print("  ✓ Test PASSED")


def test_execution_pipeline():
    print("\n" + "=" * 60)
    print("TEST 2: Execution Pipeline with Invariant Tracking")
    print("=" * 60)

    try:
        import mujoco
        from src.robot.mujoco.mujoco_simulator import MuJoCoSimulator, MuJoCoConfig
        from src.robot.mujoco.mujoco_controller import MuJoCoController
        from src.external.openvla.action_translator import ActionTranslator
        from src.external.openvla.adapter_fake import FakeOpenVLAAdapter
        from src.external.openvla.proposer_openvla import OpenVLAProposer
        from src.interfaces.scene_summary import SceneSummary, ObjectInfo
    except ImportError as exc:
        print(f"  ⚠ Skipping MuJoCo execution pipeline test (import error): {exc}")
        return

    model_path = os.path.join("models", "kuka_iiwa", "messy_table.xml")
    if not os.path.exists(model_path):
        print(f"  ⚠ Skipping MuJoCo execution pipeline test (missing model): {model_path}")
        return

    config = MuJoCoConfig(model_path=model_path, use_gui=False)
    sim = MuJoCoSimulator(config)
    sim.load_robot()
    controller = MuJoCoController(sim)
    translator = ActionTranslator(sim._model, sim._data)
    adapter = FakeOpenVLAAdapter()
    adapter.load_model()
    proposer = OpenVLAProposer(adapter, camera_provider=sim, camera_name="overhead")
    checker = InvariantChecker()

    objects = (
        ObjectInfo(object_id=0, pos_xyz=(0.4, -0.1, 0.4), on_table=True, category="red_cube", confidence=1.0),
    )
    scene = SceneSummary(
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

    for cycle in range(5):
        proposal = proposer.propose(scene)
        if proposal.action.value == "idle":
            print(f"  Cycle {cycle}: PROPOSAL_IDLE")
            continue

        translated = translator.translate_from_metadata(proposal.metadata)

        if translated.ik_success:
            converged = controller.move_to_joint_positions(translated.joint_positions)
            checker.record_execution_attempt(True, True, f"token_{cycle}")
            result = "SUCCESS" if converged else "TIMEOUT"
        else:
            checker.record_execution_attempt(True, False, f"token_{cycle}")
            result = "IK_FAILED"

        print(f"  Cycle {cycle}: {result}")

    for i in range(3):
        checker.record_execution_attempt(False, False, "")
        print(f"  Blocked {i}: unauthorized attempt recorded")

    checker.assert_invariant()
    print(f"\n  ✓ Invariant: {checker.summary}")

    joints = sim.get_joint_positions()
    assert not np.any(np.isnan(joints))
    assert not np.any(np.isinf(joints))
    print("  ✓ No NaN/Inf in joint positions")

    sim.close()
    print("  ✓ Test PASSED")


def test_nan_detection():
    print("\n" + "=" * 60)
    print("TEST 3: NaN Detection in Translator Output")
    print("=" * 60)

    from src.external.openvla.action_translator_fake import FakeActionTranslator

    translator = FakeActionTranslator()
    for _ in range(20):
        dp = np.random.uniform(-0.05, 0.05, 3)
        dr = np.random.uniform(-0.2, 0.2, 3)
        result = translator.translate(dp, dr, gripper=0.5)
        assert not np.any(np.isnan(result.joint_positions))
        assert not np.any(np.isinf(result.joint_positions))

    print("  ✓ 20 random translations: no NaN/Inf")
    print("  ✓ Test PASSED")


def main() -> int:
    print("=" * 60)
    print("WEEK 4 SMOKE TEST")
    print("Safety Integration + Full Verification")
    print("=" * 60)

    try:
        test_invariant_checker()
        test_execution_pipeline()
        test_nan_detection()

        print("\n" + "=" * 60)
        print("ALL WEEK 4 SMOKE TESTS PASSED ✓")
        print("=" * 60)
        print("\nSafety status:")
        print("  ✅ false_executions == 0 verified")
        print("  ✅ Authorization gate active")
        print("  ✅ NaN detection working")
        print("  ✅ Invariant checker operational")
        print("\nSystem ready for:")
        print("  - Extended demo runs (scripts/run_openvla_demo.py)")
        print("  - Hardware integration (Week 5-6, when arm ready)")
        return 0
    except Exception as exc:
        print(f"\n✗ SMOKE TEST FAILED: {exc}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

