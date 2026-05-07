"""
Single-joint movement test. Run after test_serial_connection.py passes.
Tests one joint at a time, returns to home after each test.

Usage:
    python scripts/test_arm_movement.py --port /dev/tty.usbserial-0001
    python scripts/test_arm_movement.py --port /dev/tty.usbserial-0001 --joint 0 --angle 15
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

JOINT_NAMES = ["base", "shoulder", "elbow", "wrist_pitch", "wrist_roll", "gripper"]


def test_movement(port: str, baud: int, joint_idx: int, angle_deg: float) -> None:
    from src.robot.hardware.arm_controller import HardwareArmController
    from src.robot.hardware.serial_controller import SerialConfig, SerialController

    cfg = SerialConfig(port=port, baud=baud)
    serial = SerialController(cfg)
    ctrl = HardwareArmController(serial_ctrl=serial)

    print(f"\n=== Arm Movement Test: joint {joint_idx} ({JOINT_NAMES[joint_idx]}) ===\n")

    print("Connecting...", end="  ")
    if not ctrl.connect():
        print("FAIL")
        sys.exit(1)
    print("OK")

    print(f"Moving joint {joint_idx} to {angle_deg:.1f} deg...", end="  ")
    target = np.zeros(6)
    target[joint_idx] = np.radians(angle_deg)

    steps = max(1, int(abs(angle_deg) / 10))
    success = True
    for step in range(1, steps + 1):
        intermediate = target * (step / steps)
        if not ctrl.move_to_joint_positions(intermediate):
            print(f"FAIL at step {step}/{steps}")
            success = False
            break
        time.sleep(0.5)

    if success:
        print("OK")
        time.sleep(1.0)

        print("Returning to home...", end="  ")
        if ctrl.home():
            print("OK")
        else:
            print("FAIL")

    ctrl.disconnect()
    print(f"\nStats: {ctrl.stats}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--joint", type=int, default=0, choices=range(6))
    parser.add_argument(
        "--angle",
        type=float,
        default=15.0,
        help="Target angle in degrees (conservative: 10-20)",
    )
    args = parser.parse_args()
    test_movement(args.port, args.baud, args.joint, args.angle)
