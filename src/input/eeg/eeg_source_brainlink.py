"""
BrainLink Lite EEG source adapter.

Wraps the existing BrainLink device connection
behind the EEGSource interface.
"""
from __future__ import annotations

import logging
from typing import Optional

from src.input.eeg.eeg_source import EEGSample, EEGSource

logger = logging.getLogger(__name__)


class BrainLinkEEGSource(EEGSource):
    """
    Real BrainLink Lite hardware adapter.

    This adapts the existing `BrainLinkDevice` implementation to the
    Phase 2A raw `EEGSource` interface without duplicating the low-level
    ThinkGear/serial parsing code.
    """

    def __init__(self, device_name: str = "BrainLink", config: Optional[dict] = None):
        self._device_name = device_name
        self._config = config or {}
        self._device = None
        self._connected = False
        self._sample_rate = 4.0
        self._n_channels = 1

    def connect(self) -> bool:
        """
        Connect to BrainLink Lite using the existing device driver.
        """
        try:
            from src.input.eeg.device_brainlink import BrainLinkDevice

            self._device = BrainLinkDevice(self._config or self._device_name)
            connected = bool(self._device.connect())
            self._connected = connected

            if connected:
                try:
                    self._sample_rate = float(self._device.sample_rate_hz)
                except Exception:
                    pass
                try:
                    self._n_channels = int(self._device.n_channels)
                except Exception:
                    pass
                logger.info(
                    "BrainLink connected (%s, %.1fHz, %d channel(s))",
                    self._device_name,
                    self._sample_rate,
                    self._n_channels,
                )
            else:
                logger.warning(
                    "BrainLink connection failed. Use SimulatedEEGSource for testing."
                )

            return connected

        except Exception as e:
            logger.error("BrainLink connection failed: %s", e)
            self._connected = False
            self._device = None
            return False

    def read_sample(self) -> Optional[EEGSample]:
        """
        Read one EEG sample from BrainLink.
        """
        if not self._connected or self._device is None:
            return None

        try:
            sample = self._device.read_sample()
            if sample is None:
                return None
            return sample

        except Exception as e:
            logger.error("BrainLink read error: %s", e)
            return None

    def disconnect(self) -> None:
        if self._device is not None:
            try:
                self._device.disconnect()
            except Exception:
                pass
        self._connected = False

    @property
    def is_connected(self) -> bool:
        if self._device is not None:
            try:
                return bool(self._device.is_connected)
            except Exception:
                pass
        return self._connected

    @property
    def sample_rate_hz(self) -> float:
        return self._sample_rate

    @property
    def n_channels(self) -> int:
        return self._n_channels
