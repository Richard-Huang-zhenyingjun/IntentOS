from __future__ import annotations
import time
from typing import Optional, Union

import numpy as np

from src.input.eeg.brainlink_stream import ThinkGearStream
from src.input.eeg.eeg_source import EEGSample, EEGSource


class BrainLinkDevice(EEGSource):
    def __init__(
        self,
        port: Union[str, dict] = "/dev/tty.BrainLink_Lite",
        baud: int = 57600,
    ):
        if isinstance(port, dict):
            eeg_cfg = port.get("eeg", {})
            resolved_port = eeg_cfg.get("port", "/dev/tty.BrainLink_Lite")
            resolved_baud = int(eeg_cfg.get("baud_rate", baud))
        else:
            resolved_port = port
            resolved_baud = baud

        self.stream = ThinkGearStream(port=resolved_port, baud=resolved_baud)
        self._connected = False

    def connect(self) -> bool:
        try:
            self.stream.connect()
            self._connected = True
            return True
        except Exception:
            self._connected = False
            return False

    def read_sample(self) -> Optional[EEGSample]:
        """Return one raw EEG sample or None."""
        s = self.stream.read_sample(max_wait_s=0.01)
        if s is None:
            return None
        if s.raw_eeg is None:
            return None
        quality = 0.0 if (s.poor_signal is not None and s.poor_signal >= 200) else 1.0
        return EEGSample(
            channels=np.array([float(s.raw_eeg)], dtype=np.float64),
            timestamp=float(getattr(s, "t", time.time())),
            quality=quality,
            source="brainlink",
            label="live",
            metadata={
                "attention": s.attention,
                "meditation": s.meditation,
                "poor_signal": s.poor_signal,
                "blink_strength": s.blink_strength,
            },
        )

    def disconnect(self):
        self.stream.close()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def sample_rate_hz(self) -> float:
        return 512.0

    @property
    def n_channels(self) -> int:
        return 1
