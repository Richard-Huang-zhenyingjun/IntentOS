"""
EEG signal source abstraction.

Provides a uniform interface for:
- Real BrainLink hardware
- Simulated EEG (for testing and demos)
- Recorded replay (from collected training data)

Every source produces the same output: a timestamped
EEG sample with channel data.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np


@dataclass(init=False)
class EEGSample:
    """Single EEG sample from any source."""
    channels: np.ndarray
    timestamp: float
    quality: float = 1.0
    source: str = "unknown"
    label: str = "idle"
    metadata: dict = field(default_factory=dict)

    def __init__(
        self,
        channels: np.ndarray | None = None,
        timestamp: float | None = None,
        quality: float = 1.0,
        source: str = "unknown",
        label: str = "idle",
        metadata: dict | None = None,
        timestamp_ms: float | None = None,
        value: float | None = None,
        channel: int = 0,
        valid: bool = True,
    ) -> None:
        if channels is None:
            if value is None:
                raise ValueError("EEGSample requires 'channels' or legacy 'value'")
            channels = np.array([value], dtype=np.float64)
        if timestamp is None:
            if timestamp_ms is None:
                raise ValueError("EEGSample requires 'timestamp' or legacy 'timestamp_ms'")
            timestamp = float(timestamp_ms) / 1000.0

        self.channels = np.asarray(channels, dtype=np.float64).reshape(-1)
        self.timestamp = float(timestamp)
        self.quality = float(np.clip(quality if valid else 0.0, 0.0, 1.0))
        self.source = source
        self.label = label
        self.metadata = {} if metadata is None else dict(metadata)

    def __post_init__(self) -> None:
        self.channels = np.asarray(self.channels, dtype=np.float64).reshape(-1)
        self.timestamp = float(self.timestamp)
        self.quality = float(np.clip(self.quality, 0.0, 1.0))

    @property
    def timestamp_ms(self) -> float:
        return self.timestamp * 1000.0

    @property
    def value(self) -> float:
        return float(self.channels[0]) if self.channels.size else 0.0

    @property
    def channel(self) -> int:
        return 0

    @property
    def valid(self) -> bool:
        return self.quality > 0.0


class EEGSource(ABC):
    """Abstract base for EEG signal sources."""

    @abstractmethod
    def connect(self) -> bool:
        """Connect to the EEG source. Returns True on success."""
        ...

    @abstractmethod
    def read_sample(self) -> EEGSample | None:
        """
        Read one sample. Returns None if no data available.
        Non-blocking — returns immediately.
        """
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the source."""
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        ...

    @property
    @abstractmethod
    def sample_rate_hz(self) -> float:
        """Nominal sample rate in Hz."""
        ...

    @property
    @abstractmethod
    def n_channels(self) -> int:
        """Number of EEG channels."""
        ...

def __getattr__(name: str):
    if name == "EEGDecisionSource":
        from src.input.eeg.decision_source import EEGDecisionSource
        return EEGDecisionSource
    raise AttributeError(name)


__all__ = ["EEGSample", "EEGSource", "EEGDecisionSource"]
