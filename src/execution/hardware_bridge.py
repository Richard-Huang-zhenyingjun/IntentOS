"""
Hardware bridge. Translates joint positions to either MuJoCo (sim) or
serial commands (real arm).

Backend controlled by config:
  hardware.backend: "simulator" | "hardware"

Default: "simulator". The real backend is inactive until physical arm is ready.
Switching to "hardware" is a config change once serial port and limits are set.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JointCommand:
    """Single joint position command."""

    joint_idx: int
    angle_rad: float
    angle_deg: float

    @classmethod
    def from_radians(cls, joint_idx: int, angle_rad: float) -> "JointCommand":
        return cls(
            joint_idx=joint_idx,
            angle_rad=float(angle_rad),
            angle_deg=float(np.degrees(angle_rad)),
        )


class ArmBackendBase(ABC):
    @abstractmethod
    def apply_joints(self, commands: list[JointCommand]) -> None:
        """Apply joint commands. Blocks until complete or timeout."""
        ...

    @abstractmethod
    def emergency_stop(self) -> None:
        """Fire-and-forget emergency stop. Must not block."""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        ...


class SimBackend(ArmBackendBase):
    """Applies joints to MuJoCo. Wraps existing direct-qpos sim behavior."""

    def __init__(self, mujoco_model, mujoco_data):
        self._model = mujoco_model
        self._data = mujoco_data

    def apply_joints(self, commands: list[JointCommand]) -> None:
        for cmd in commands:
            if cmd.joint_idx < len(self._data.qpos):
                self._data.qpos[cmd.joint_idx] = cmd.angle_rad
        try:
            import mujoco

            mujoco.mj_forward(self._model, self._data)
        except Exception as exc:
            logger.debug("Skipping MuJoCo forward after qpos write: %s", exc)

    def emergency_stop(self) -> None:
        pass

    def is_connected(self) -> bool:
        return True


class RealArmBackend(ArmBackendBase):
    """
    Real arm backend. Delegates to HardwareArmController which speaks the
    canonical JOINT protocol via SerialController.

    This class is a thin adapter so HardwareBridge.execute() works unchanged.
    """

    def __init__(self, arm_controller):
        self._ctrl = arm_controller

    @classmethod
    def from_config(cls, cfg: dict) -> "RealArmBackend":
        """Build from hardware config and connect immediately."""
        from src.robot.hardware.arm_controller import HardwareArmController
        from src.robot.hardware.serial_controller import SerialConfig, SerialController

        hw_cfg = cfg.get("hardware", {})
        real_cfg = hw_cfg.get("real", {})
        serial_cfg = SerialConfig(
            port=real_cfg["port"],
            baud=int(real_cfg.get("baud", 115200)),
            arduino_reset_delay_s=float(real_cfg.get("arduino_reset_delay_s", 2.0)),
        )
        serial = SerialController(serial_cfg)
        ctrl = HardwareArmController.from_config(cfg, serial_ctrl=serial)
        if not ctrl.connect():
            raise RuntimeError(
                f"RealArmBackend: failed to connect to arm on {real_cfg['port']}. "
                "Run scripts/test_serial_connection.py to diagnose."
            )
        return cls(ctrl)

    def apply_joints(self, commands: list[JointCommand]) -> None:
        """
        Convert JointCommand list to a joint array and delegate to controller.

        HardwareArmController handles segmentation, limit clamping, and ACK
        verification using the canonical JOINT wire protocol.
        """
        try:
            from src.robot.hardware.arm_controller import N_JOINTS

            positions_rad = np.zeros(N_JOINTS, dtype=float)
            for cmd in commands:
                if cmd.joint_idx < N_JOINTS:
                    positions_rad[cmd.joint_idx] = cmd.angle_rad
            ok = self._ctrl.move_to_joint_positions(positions_rad)
        except Exception:
            logger.exception("RealArmBackend: move failed")
            raise
        if not ok:
            logger.warning(
                "RealArmBackend: move rejected by HardwareArmController. "
                "Check controller stats: %s",
                self._ctrl.stats,
            )

    def emergency_stop(self) -> None:
        self._ctrl.emergency_stop()

    def is_connected(self) -> bool:
        return bool(getattr(self._ctrl._serial, "is_connected", False))


class HardwareBridge:
    """
    Single entry point for joint execution. Backend-agnostic.
    PrimitiveExecutor can call this instead of directly commanding a controller.
    """

    def __init__(
        self,
        backend: ArmBackendBase,
        joint_limits: Optional[list[tuple[float, float]]] = None,
    ):
        self._backend = backend
        self._limits = joint_limits or []

    def execute(self, joint_positions: np.ndarray) -> None:
        """
        Apply joint positions. Clamps to limits if configured.

        Args:
            joint_positions: np.ndarray shape (N,), radians
        """
        commands = []
        for i, angle_rad in enumerate(np.asarray(joint_positions, dtype=float).reshape(-1)):
            if not np.isfinite(angle_rad):
                raise ValueError(f"Non-finite joint position at index {i}: {angle_rad}")
            if i < len(self._limits):
                lo, hi = self._limits[i]
                angle_rad = float(np.clip(angle_rad, lo, hi))
            commands.append(JointCommand.from_radians(i, angle_rad))
        self._backend.apply_joints(commands)

    def emergency_stop(self) -> None:
        self._backend.emergency_stop()

    def is_connected(self) -> bool:
        return self._backend.is_connected()
