"""
Serial controller for Arduino-based arm firmware.
Implements the canonical PING/JOINT/HOME/STOP/POS/LIMITS protocol.

All commands except STOP are synchronous: they send and wait for OK/ERR.
STOP is fire-and-forget: it writes and returns immediately.

Thread safety: external locking required - this class is not thread-safe.
Use one instance per thread, or lock externally.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

ACK = "OK"
ERR_PREFIX = "ERR"


@dataclass(frozen=True)
class SerialConfig:
    port: str
    baud: int = 115200
    timeout_s: float = 2.0
    ack_timeout_s: float = 5.0
    arduino_reset_delay_s: float = 2.0
    max_retries: int = 2


class SerialController:
    """
    Low-level serial interface to Arduino firmware.
    Higher-level callers (HardwareArmController, HardwareBridge) use this.
    """

    def __init__(self, cfg: SerialConfig):
        self._cfg = cfg
        self._serial = None
        self._connected = False

    def connect(self) -> bool:
        """Open serial port and verify firmware responds to PING."""
        import serial

        try:
            self._serial = serial.Serial(
                self._cfg.port,
                self._cfg.baud,
                timeout=self._cfg.timeout_s,
            )
            time.sleep(self._cfg.arduino_reset_delay_s)
            self._serial.reset_input_buffer()

            response = self._send_and_wait(
                "PING",
                timeout_s=self._cfg.timeout_s,
                require_connected=False,
            )
            if response and "PONG" in response:
                self._connected = True
                logger.info("SerialController connected on %s", self._cfg.port)
                return True

            logger.error("PING failed - got: %r", response)
            return False
        except Exception as exc:
            logger.error("Serial connect failed: %s", exc)
            self._connected = False
            return False

    def disconnect(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._serial is not None and self._serial.is_open

    def ping(self) -> bool:
        """Returns True if firmware responds OK PONG."""
        response = self._send_and_wait("PING")
        return response is not None and "PONG" in response

    def send_joint_angles(self, angles_deg: np.ndarray) -> bool:
        """
        Send all joint angles in degrees.

        angles_deg: shape (N,) where N matches firmware joint count.
        Returns True on OK, False on ERR or timeout.
        """
        cmd = "JOINT " + " ".join(f"{float(angle):.2f}" for angle in angles_deg)
        response = self._send_and_wait(cmd)
        if response is None or not response.startswith(ACK):
            logger.warning("JOINT rejected: %r -> %r", cmd, response)
            return False
        return True

    def send_home(self) -> bool:
        """Command arm to home position. Uses longer timeout for slow moves."""
        response = self._send_and_wait("HOME", timeout_s=self._cfg.ack_timeout_s)
        return response is not None and response.startswith(ACK)

    def send_gripper(self, open_: bool) -> bool:
        cmd = "GRIPPER open" if open_ else "GRIPPER close"
        response = self._send_and_wait(cmd)
        return response is not None and response.startswith(ACK)

    def send_stop(self) -> None:
        """Fire-and-forget emergency stop. Does not wait for ACK. Must never raise."""
        try:
            if self._serial and self._serial.is_open:
                self._serial.write(b"STOP\n")
                self._serial.flush()
        except Exception:
            pass

    def query_position(self) -> Optional[np.ndarray]:
        """Query current joint positions. Returns degrees or None on failure."""
        response = self._send_and_wait("POS")
        if response is None or not response.startswith("OK POS"):
            return None
        try:
            parts = response.split()[2:]
            return np.array([float(part) for part in parts])
        except (ValueError, IndexError):
            logger.warning("Could not parse POS response: %r", response)
            return None

    def query_limits(self) -> Optional[list[tuple[float, float]]]:
        """Query joint limits from firmware."""
        response = self._send_and_wait("LIMITS")
        if response is None or not response.startswith("OK LIMITS"):
            return None
        try:
            parts = [float(part) for part in response.split()[2:]]
            if len(parts) % 2 != 0:
                return None
            return [(parts[i], parts[i + 1]) for i in range(0, len(parts), 2)]
        except (ValueError, IndexError):
            return None

    def _send_and_wait(
        self,
        cmd: str,
        timeout_s: Optional[float] = None,
        require_connected: bool = True,
    ) -> Optional[str]:
        """Send command, read one line response. Returns stripped line or None."""
        if require_connected and not self.is_connected:
            logger.error("Not connected - cannot send: %s", cmd)
            return None
        if self._serial is None or not self._serial.is_open:
            logger.error("Serial port closed - cannot send: %s", cmd)
            return None

        timeout = timeout_s or self._cfg.timeout_s
        self._serial.timeout = timeout

        for attempt in range(self._cfg.max_retries + 1):
            try:
                self._serial.reset_input_buffer()
                self._serial.write(f"{cmd}\n".encode("ascii"))
                self._serial.flush()
                line = self._serial.readline().decode(errors="replace").strip()
                if line:
                    return line
                if attempt < self._cfg.max_retries:
                    logger.warning("Empty response for %r, retrying (%d)", cmd, attempt + 1)
            except Exception as exc:
                logger.error("Serial I/O error on %r: %s", cmd, exc)
                self._connected = False
                return None

        logger.error("No response after %d attempts for: %s", self._cfg.max_retries + 1, cmd)
        return None
