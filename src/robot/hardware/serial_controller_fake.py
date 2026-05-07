"""
Fake serial controller for testing without hardware.
Simulates firmware ACK/NAK behavior and state tracking.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from .serial_controller import SerialConfig


class FakeSerialController:
    """
    Drop-in replacement for SerialController in tests.
    Tracks sent commands and returns configurable responses.
    """

    def __init__(
        self,
        cfg: Optional[SerialConfig] = None,
        fail_commands: Optional[set] = None,
        simulate_nak_joint: bool = False,
    ):
        self._cfg = cfg
        self._fail_commands = fail_commands or set()
        self._simulate_nak_joint = simulate_nak_joint
        self._connected = False
        self.sent_commands: list[str] = []
        self._current_angles = np.zeros(6)

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def ping(self) -> bool:
        return "ping" not in self._fail_commands

    def send_joint_angles(self, angles_deg: np.ndarray) -> bool:
        self.sent_commands.append(
            "JOINT " + " ".join(f"{float(angle):.2f}" for angle in angles_deg)
        )
        if "joint" in self._fail_commands or self._simulate_nak_joint:
            return False
        self._current_angles = np.array(angles_deg, dtype=float)
        return True

    def send_home(self) -> bool:
        self.sent_commands.append("HOME")
        if "home" in self._fail_commands:
            return False
        self._current_angles = np.zeros_like(self._current_angles)
        return True

    def send_gripper(self, open_: bool) -> bool:
        self.sent_commands.append(f"GRIPPER {'open' if open_ else 'close'}")
        return "gripper" not in self._fail_commands

    def send_stop(self) -> None:
        self.sent_commands.append("STOP")

    def query_position(self) -> Optional[np.ndarray]:
        return self._current_angles.copy()

    def query_limits(self) -> Optional[list[tuple[float, float]]]:
        return [(-90.0, 90.0)] * 6
