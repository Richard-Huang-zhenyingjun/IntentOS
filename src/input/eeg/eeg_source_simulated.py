"""
Simulated EEG source for testing and demos.

Generates synthetic EEG-like signals with controllable properties:
- Background noise (alpha rhythm, muscle artifacts)
- Confirm events (amplitude spike + frequency shift)
- Idle periods (baseline noise only)
- Configurable signal quality (SNR)

The simulation is NOT neurophysiologically accurate. It produces
signals that are statistically distinguishable between confirm
and idle states, matching what a real classifier would see after
training on real data.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import numpy as np

from src.input.eeg.eeg_source import EEGSample, EEGSource

logger = logging.getLogger(__name__)


class SimulatedEEGSource(EEGSource):
    """
    Generates synthetic EEG signals for testing.

    Modes:
    - "auto": Randomly alternates between confirm and idle based on probability
    - "scripted": Follows an explicit sequence of confirm/idle events
    - "manual": Only produces confirm when inject_confirm() is called
    """

    def __init__(
        self,
        mode: str | dict = "auto",
        confirm_probability: float = 0.3,
        sample_rate_hz: float = 128.0,
        n_channels: int = 1,
        noise_level: float = 0.3,
        confirm_amplitude: float = 2.0,
        seed: Optional[int] = None,
    ):
        # Backward compatibility: allow a config dict as the first argument.
        if isinstance(mode, dict):
            config = mode
            eeg_cfg = config.get("eeg", {})
            sim_cfg = eeg_cfg.get("simulated", {})
            mode = sim_cfg.get("mode", "manual")
            confirm_probability = float(sim_cfg.get("confirm_probability", confirm_probability))
            sample_rate_hz = float(sim_cfg.get("sample_rate_hz", eeg_cfg.get("expected_sfreq", sample_rate_hz)))
            n_channels = int(sim_cfg.get("n_channels", n_channels))
            noise_level = float(sim_cfg.get("noise_level", noise_level))
            confirm_amplitude = float(
                sim_cfg.get(
                    "confirm_amplitude",
                    sim_cfg.get("confirm_spike_amplitude", confirm_amplitude),
                )
            )
            seed = sim_cfg.get("seed", seed)

        self._mode = str(mode)
        self._confirm_prob = float(np.clip(confirm_probability, 0.0, 1.0))
        self._sample_rate = float(sample_rate_hz)
        self._n_channels = int(n_channels)
        self._noise_level = float(np.clip(noise_level, 0.0, 1.0))
        self._confirm_amp = float(confirm_amplitude)
        self._rng = np.random.RandomState(seed)

        self._connected = False
        self._sample_count = 0
        self._connect_time = 0.0

        # State for manual/scripted mode
        self._current_state = "idle"
        self._state_remaining = 0

        # Scripted mode support
        self._script: list[tuple[str, int]] = []
        self._script_index = 0

        # Tracking
        self._confirm_samples_generated = 0
        self._idle_samples_generated = 0

    def connect(self) -> bool:
        self._connected = True
        self._connect_time = time.time()
        self._sample_count = 0
        self._confirm_samples_generated = 0
        self._idle_samples_generated = 0
        logger.info(
            "Simulated EEG connected (mode=%s, rate=%.1fHz)",
            self._mode,
            self._sample_rate,
        )
        return True

    def read_sample(self) -> Optional[EEGSample]:
        if not self._connected:
            return None

        self._sample_count += 1
        now = time.time()
        is_confirm = self._get_current_state()
        channels = self._generate_signal(is_confirm)

        if is_confirm:
            self._confirm_samples_generated += 1
            label = "confirm"
        else:
            self._idle_samples_generated += 1
            label = "idle"

        return EEGSample(
            channels=channels,
            timestamp=now,
            quality=1.0 - self._noise_level * 0.5,
            source="simulated",
            label=label,
        )

    def disconnect(self) -> None:
        self._connected = False
        logger.info(
            "Simulated EEG disconnected: %d samples (%d confirm, %d idle)",
            self._sample_count,
            self._confirm_samples_generated,
            self._idle_samples_generated,
        )

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def sample_rate_hz(self) -> float:
        return self._sample_rate

    @property
    def n_channels(self) -> int:
        return self._n_channels

    def inject_confirm(self, duration_samples: int = 20) -> None:
        """Force next N samples to be confirm-like."""
        self._current_state = "confirm"
        self._state_remaining = max(0, int(duration_samples))
        if self._mode != "scripted":
            self._mode = "manual"

    def inject_idle(self, duration_samples: int = 20) -> None:
        """Force next N samples to be idle-like."""
        self._current_state = "idle"
        self._state_remaining = max(0, int(duration_samples))
        if self._mode != "scripted":
            self._mode = "manual"

    def set_script(self, script: list[tuple[str, int]]) -> None:
        """Set a sequence of states for scripted mode."""
        self._script = list(script)
        self._script_index = 0
        self._mode = "scripted"
        if self._script:
            self._current_state = self._script[0][0]
            self._state_remaining = int(self._script[0][1])

    def set_confirm_probability(self, prob: float) -> None:
        """Update confirm probability for auto mode."""
        self._confirm_prob = float(np.clip(prob, 0.0, 1.0))

    def force_label(
        self,
        label: str,
        duration_sec: float = 1.0,
        quality: Optional[float] = None,
    ) -> None:
        """
        Backward-compatible helper from the earlier simulated source.
        Converts duration in seconds to samples and routes through manual mode.
        """
        if quality is not None:
            self._noise_level = float(np.clip((1.0 - quality) / 0.5, 0.0, 1.0))
        duration_samples = max(1, int(round(duration_sec * self._sample_rate)))
        if label == "confirm":
            self.inject_confirm(duration_samples)
        else:
            self.inject_idle(duration_samples)

    def _get_current_state(self) -> bool:
        if self._mode == "auto":
            return bool(self._rng.random() < self._confirm_prob)

        if self._mode == "manual":
            if self._state_remaining > 0:
                self._state_remaining -= 1
                return self._current_state == "confirm"
            return False

        if self._mode == "scripted":
            if self._state_remaining > 0:
                self._state_remaining -= 1
                is_confirm = self._current_state == "confirm"
                if self._state_remaining == 0:
                    self._script_index += 1
                    if self._script_index < len(self._script):
                        state, dur = self._script[self._script_index]
                        self._current_state = state
                        self._state_remaining = int(dur)
                return is_confirm
            return False

        return False

    def _generate_signal(self, is_confirm: bool) -> np.ndarray:
        t = self._sample_count / max(self._sample_rate, 1.0)
        channels = np.zeros(self._n_channels, dtype=np.float64)

        for ch in range(self._n_channels):
            noise = self._rng.randn() * self._noise_level
            if is_confirm:
                alpha = 0.3 * np.sin(2 * np.pi * 10 * t + ch)
                beta = 0.8 * np.sin(2 * np.pi * 20 * t + ch)
                erp = self._confirm_amp * np.exp(-((t % 0.5) ** 2) / 0.01)
                channels[ch] = (alpha + beta + erp) * self._confirm_amp + noise
            else:
                alpha = 0.5 * np.sin(2 * np.pi * 10 * t + ch)
                channels[ch] = alpha + noise

        return channels

    @property
    def stats(self) -> dict:
        return {
            "mode": self._mode,
            "samples": self._sample_count,
            "confirm_samples": self._confirm_samples_generated,
            "idle_samples": self._idle_samples_generated,
            "confirm_ratio": self._confirm_samples_generated / max(self._sample_count, 1),
        }
