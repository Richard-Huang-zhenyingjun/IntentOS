"""
Replay EEG source — reads recorded CSV samples.
Enables deterministic testing without hardware.
"""
import csv
import time
import logging
import numpy as np
from pathlib import Path
from typing import Callable, Optional

from src.input.eeg.eeg_source import EEGSample, EEGSource

logger = logging.getLogger(__name__)


class ReplayDevice(EEGSource):
    """
    Replays recorded EEG session from CSV file.
    
    CSV format:
        timestamp_ms,value,channel,valid
        0.0,12.5,0,1
        1.953,13.1,0,1
        ...
    
    Supports two modes:
    - real_time=True: replay at original timing (for demos)
    - real_time=False: feed all data immediately (for tests)
    """
    
    def __init__(self, filepath: str, real_time: bool = False):
        self.filepath = Path(filepath)
        self.real_time = real_time
        self._callback: Optional[Callable] = None
        self._connected = False
        self._sfreq = 512.0  # Will be estimated from data
        self._samples_fed = 0
        self._samples: list[EEGSample] = []
        self._cursor = 0
        self._start_wall_time = 0.0
        self._start_sample_time = 0.0

    def connect(self) -> bool:
        """Load recording and prepare replay."""
        if not self.filepath.exists():
            raise FileNotFoundError(f"Recording not found: {self.filepath}")
        self._samples = self._load_csv()
        self._cursor = 0
        self._connected = True
        self._start_wall_time = time.time()
        self._start_sample_time = self._samples[0].timestamp if self._samples else 0.0
        return True

    def disconnect(self) -> None:
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def sample_rate_hz(self) -> float:
        return self._sfreq

    @property
    def n_channels(self) -> int:
        return 1

    def set_callback(self, callback: Callable[[EEGSample], None]):
        self._callback = callback

    def start(self) -> None:
        """Legacy callback compatibility for collection scripts."""
        self.connect()
        while self.is_connected:
            sample = self.read_sample()
            if sample is None:
                time.sleep(0.001)
                continue
            if self._callback:
                self._callback(sample)

    def stop(self) -> None:
        self.disconnect()

    def get_sfreq(self) -> float:
        return self._sfreq

    def _load_csv(self) -> list[EEGSample]:
        """Load CSV into sample objects."""
        timestamps_ms = []
        values = []

        with open(self.filepath, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                timestamps_ms.append(float(row['timestamp_ms']))
                values.append(float(row['value']))

        timestamps = np.array(timestamps_ms, dtype=np.float64)
        values = np.array(values)

        # Estimate sfreq from timestamps
        if len(timestamps) > 1:
            dt_ms = np.median(np.diff(timestamps))
            if dt_ms > 0:
                self._sfreq = 1000.0 / dt_ms
        
        logger.info(
            f"[REPLAY] Loaded {len(values)} samples, "
            f"estimated sfreq={self._sfreq:.1f} Hz, "
            f"duration={timestamps[-1] - timestamps[0]:.0f} ms"
        )

        return [
            EEGSample(
                channels=np.array([values[i]], dtype=np.float64),
                timestamp=timestamps[i] / 1000.0,
                quality=1.0,
                source="replay",
                label="replay",
            )
            for i in range(len(values))
        ]

    def read_sample(self) -> Optional[EEGSample]:
        if not self._connected or self._cursor >= len(self._samples):
            self._connected = False
            return None

        sample = self._samples[self._cursor]
        if self.real_time:
            elapsed = time.time() - self._start_wall_time
            sample_elapsed = sample.timestamp - self._start_sample_time
            if sample_elapsed > elapsed:
                return None

        self._cursor += 1
        self._samples_fed += 1
        if self._cursor >= len(self._samples):
            self._connected = False
        return sample


