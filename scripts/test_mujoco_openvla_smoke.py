"""Combined MuJoCo + FakeOpenVLA smoke test.

Run:
  python scripts/test_mujoco_openvla_smoke.py
"""
from __future__ import annotations

import os
import sys

import numpy as np

os.environ.setdefault("MUJOCO_GL", "disable")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.external.openvla.adapter_fake import FakeOpenVLAAdapter
from src.robot.mujoco.mujoco_simulator import MuJoCoConfig, MuJoCoSimulator


def main() -> int:
    sim = MuJoCoSimulator(
        MuJoCoConfig(model_path="models/kuka_iiwa/messy_table.xml", use_gui=False)
    )
    sim.load_robot()

    # Basic MuJoCo checks.
    assert sim.num_joints >= 7, f"Expected >=7 joints, got {sim.num_joints}"
    assert sim.num_actuators >= 7, f"Expected >=7 actuators, got {sim.num_actuators}"

    for _ in range(50):
        sim.step()

    ee_pos, _ = sim.get_end_effector_pose()
    assert ee_pos.shape == (3,)

    # Render camera frame for VLA input; fall back when headless GL is unavailable.
    try:
        rgb = sim.render_camera(camera_name="")
        render_mode = "mujoco_renderer"
    except RuntimeError:
        rgb = np.zeros((480, 640, 3), dtype=np.uint8)
        rgb[180:260, 280:360] = [255, 0, 0]
        render_mode = "synthetic_fallback"

    assert isinstance(rgb, np.ndarray)
    assert rgb.ndim == 3 and rgb.shape[2] == 3

    # Fake OpenVLA checks.
    adapter = FakeOpenVLAAdapter()
    adapter.load_model()
    action = adapter.predict("pick up the red block", rgb)
    assert action.raw_action.shape == (7,)

    print("MuJoCo scene load: OK")
    print(f"joints={sim.num_joints}, actuators={sim.num_actuators}")
    print(f"camera_frame={rgb.shape} mode={render_mode}")
    print(f"fake_openvla_action={action.raw_action.tolist()}")
    print("Combined smoke test PASSED")

    adapter.close()
    sim.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
