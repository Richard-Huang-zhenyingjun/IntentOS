"""
Hardware connection test. Run once after assembling arm before code integration.

Usage:
    python scripts/test_serial_connection.py --port /dev/tty.usbserial-0001
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.robot.hardware.serial_controller import SerialConfig, SerialController


def test_connection(port: str, baud: int) -> None:
    print(f"\n=== Serial Connection Test: {port} @{baud} ===\n")
    cfg = SerialConfig(port=port, baud=baud, timeout_s=3.0)
    ctrl = SerialController(cfg)

    print("1. Connecting...", end="  ")
    if not ctrl.connect():
        print("FAIL - check port and firmware")
        sys.exit(1)
    print("OK")

    print("2. PING...", end="  ")
    if not ctrl.ping():
        print("FAIL - firmware not responding")
        sys.exit(1)
    print("OK")

    print("3. POS query...", end="  ")
    pos = ctrl.query_position()
    if pos is None:
        print("FAIL - no position response")
    else:
        print(f"OK -> {[f'{p:.1f} deg' for p in pos]}")

    print("4. LIMITS query...", end="  ")
    limits = ctrl.query_limits()
    if limits is None:
        print("FAIL - no limits response")
    else:
        print(f"OK -> {limits}")

    if pos is not None:
        print("5. JOINT (home position)...", end="  ")
        import numpy as np

        success = ctrl.send_joint_angles(np.zeros(len(pos)))
        print("OK" if success else "FAIL")
        time.sleep(1.0)

    print("6. STOP...", end="  ")
    ctrl.send_stop()
    print("OK (fire-and-forget)")

    ctrl.disconnect()
    print("\nConnection test complete. Ready for Batch 2C.2.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()
    test_connection(args.port, args.baud)
