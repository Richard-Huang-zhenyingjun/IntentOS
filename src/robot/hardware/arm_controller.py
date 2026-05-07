"""
Hardware arm controller - BCN3D Moveo (6 joints).

Public API uses radians (matching MuJoCo convention).
Internal protocol uses degrees (firmware expectation).

Safety pipeline per move_to_joint_positions() call:
  1. radians -> degrees
  2. Clamp to joint limits
  3. Compute step on the clamped target
  4. Segment into safe increments when needed
  5. Verify ACK per segment
  6. Update _current_deg only on full success

Emergency stop is fire-and-forget, never raises, and always available.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .serial_controller import SerialController

logger = logging.getLogger(__name__)

N_JOINTS = 6

DEFAULT_LIMITS_DEG: list[tuple[float, float]] = [
    (-90.0, 90.0),
    (-45.0, 90.0),
    (-90.0, 45.0),
    (-90.0, 90.0),
    (-180.0, 180.0),
    (0.0, 80.0),
]
HOME_POSITION_DEG = np.zeros(N_JOINTS)
MAX_STEP_DEG = 10.0


@dataclass
class ControllerStats:
    moves_attempted: int = 0
    moves_succeeded: int = 0
    moves_clamped: int = 0
    moves_segmented: int = 0
    segments_sent: int = 0
    naks_received: int = 0
    emergency_stops: int = 0

    @property
    def moves_sent(self) -> int:
        return self.segments_sent

    @property
    def moves_rejected_limits(self) -> int:
        return self.moves_clamped

    @property
    def moves_rejected_step(self) -> int:
        return 0


class HardwareArmController:
    """
    Safe, unit-converting interface to the physical BCN3D Moveo arm.
    All public methods use radians. Serial protocol uses degrees.
    """

    def __init__(
        self,
        serial_ctrl: SerialController,
        limits_deg: Optional[list[tuple[float, float]]] = None,
        max_step_deg: float = MAX_STEP_DEG,
    ):
        self._serial = serial_ctrl
        self._limits_deg = [(float(lo), float(hi)) for lo, hi in (limits_deg or DEFAULT_LIMITS_DEG)]
        self._max_step_deg = float(max_step_deg)
        self._current_deg = HOME_POSITION_DEG.copy()
        self._stats = ControllerStats()

    @classmethod
    def from_config(
        cls,
        cfg: dict,
        serial_ctrl: Optional[SerialController] = None,
    ) -> "HardwareArmController":
        hw = cfg.get("hardware", {})
        limits_raw = hw.get("joint_limits", DEFAULT_LIMITS_DEG)
        limits_deg = [(float(lo), float(hi)) for lo, hi in limits_raw]
        max_step = float(hw.get("max_step_deg", MAX_STEP_DEG))
        if serial_ctrl is None:
            from .serial_controller import SerialConfig

            real_cfg = hw.get("real", {})
            serial_cfg = SerialConfig(
                port=real_cfg["port"],
                baud=int(real_cfg.get("baud", 115200)),
                arduino_reset_delay_s=float(real_cfg.get("arduino_reset_delay_s", 2.0)),
            )
            serial_ctrl = SerialController(serial_cfg)
        return cls(serial_ctrl=serial_ctrl, limits_deg=limits_deg, max_step_deg=max_step)

    def connect(self) -> bool:
        ok = self._serial.connect()
        if ok:
            fw_limits = self._serial.query_limits()
            if fw_limits and len(fw_limits) == N_JOINTS:
                self._limits_deg = [(float(lo), float(hi)) for lo, hi in fw_limits]
                logger.info("Joint limits loaded from firmware: %s", fw_limits)
            pos = self._serial.query_position()
            if pos is not None and len(pos) == N_JOINTS:
                self._current_deg = np.array(pos, dtype=float)
                logger.info("Initial position loaded from firmware: %s", np.round(self._current_deg, 1))
        return ok

    def disconnect(self) -> None:
        self._serial.disconnect()

    def move_to_joint_positions(self, positions_rad: np.ndarray) -> bool:
        """
        Move all joints to target positions in radians.

        Returns True if every segment was ACK'd, False on any NAK or error.
        """
        if len(positions_rad) != N_JOINTS:
            logger.error("Expected %d joints, got %d", N_JOINTS, len(positions_rad))
            return False

        self._stats.moves_attempted += 1
        target_deg = np.degrees(np.asarray(positions_rad, dtype=float))
        clamped_deg = self._clamp_to_limits(target_deg)
        segments = self._compute_segments(self._current_deg, clamped_deg)

        if len(segments) > 1:
            self._stats.moves_segmented += 1
            logger.debug("Move segmented into %d steps", len(segments))

        checkpoint = self._current_deg.copy()
        for seg_target in segments:
            ok = self._serial.send_joint_angles(seg_target)
            self._stats.segments_sent += 1
            if not ok:
                self._stats.naks_received += 1
                logger.warning(
                    "Firmware NAK at segment %s - halting move, staying at %s",
                    np.round(seg_target, 1),
                    np.round(checkpoint, 1),
                )
                return False
            checkpoint = seg_target.copy()

        self._current_deg = clamped_deg.copy()
        self._stats.moves_succeeded += 1
        return True

    def home(self) -> bool:
        ok = self._serial.send_home()
        if ok:
            self._current_deg = HOME_POSITION_DEG.copy()
        return ok

    def get_joint_positions(self) -> np.ndarray:
        pos_deg = self._serial.query_position()
        if pos_deg is not None and len(pos_deg) == N_JOINTS:
            self._current_deg = np.array(pos_deg, dtype=float)
        return np.radians(self._current_deg)

    def open_gripper(self) -> bool:
        return self._serial.send_gripper(open_=True)

    def close_gripper(self) -> bool:
        return self._serial.send_gripper(open_=False)

    def emergency_stop(self) -> None:
        self._stats.emergency_stops += 1
        try:
            self._serial.send_stop()
        except Exception:
            pass

    @property
    def stats(self) -> ControllerStats:
        return self._stats

    @property
    def current_position_rad(self) -> np.ndarray:
        return np.radians(self._current_deg)

    def _clamp_to_limits(self, target_deg: np.ndarray) -> np.ndarray:
        clamped = np.array(
            [
                np.clip(target_deg[i], self._limits_deg[i][0], self._limits_deg[i][1])
                for i in range(N_JOINTS)
            ],
            dtype=float,
        )

        delta = np.abs(clamped - target_deg)
        if np.any(delta > 0.05):
            self._stats.moves_clamped += 1
            logger.warning(
                "Joint target clamped to limits. Requested: %s  Clamped: %s  Delta: %s",
                np.round(target_deg, 1),
                np.round(clamped, 1),
                np.round(delta, 1),
            )
        return clamped

    def _compute_segments(
        self,
        current_deg: np.ndarray,
        target_deg: np.ndarray,
    ) -> list[np.ndarray]:
        step = np.abs(target_deg - current_deg)
        max_joint_step = float(np.max(step))

        if max_joint_step <= self._max_step_deg:
            return [target_deg.copy()]

        n_steps = math.ceil(max_joint_step / self._max_step_deg)
        return [
            current_deg + (k / n_steps) * (target_deg - current_deg)
            for k in range(1, n_steps + 1)
        ]
