"""
Tests for EEG signal sources.

Run: pytest tests/test_eeg_source.py -v
"""
import numpy as np
import pytest

from src.input.eeg.eeg_source import EEGSample
from src.input.eeg.eeg_source_simulated import SimulatedEEGSource


class TestEEGSample:
    def test_sample_fields(self):
        s = EEGSample(channels=np.array([0.5]), timestamp=1.0)
        assert s.channels.shape == (1,)
        assert s.timestamp == 1.0
        assert s.quality == 1.0
        assert s.source == "unknown"


class TestSimulatedSource:
    @pytest.fixture
    def source(self):
        s = SimulatedEEGSource(mode="manual", seed=42)
        s.connect()
        yield s
        s.disconnect()

    def test_connect_disconnect(self):
        s = SimulatedEEGSource()
        assert not s.is_connected
        s.connect()
        assert s.is_connected
        s.disconnect()
        assert not s.is_connected

    def test_read_sample(self, source):
        sample = source.read_sample()
        assert sample is not None
        assert isinstance(sample, EEGSample)
        assert sample.channels.shape == (1,)
        assert sample.source == "simulated"

    def test_disconnected_returns_none(self):
        s = SimulatedEEGSource()
        assert s.read_sample() is None

    def test_manual_mode_default_idle(self, source):
        """Manual mode defaults to idle signal."""
        samples = [source.read_sample() for _ in range(20)]
        amplitudes = [np.abs(s.channels[0]) for s in samples]
        mean_amp = np.mean(amplitudes)
        assert mean_amp < 3.0

    def test_inject_confirm_changes_signal(self, source):
        """Injecting confirm should produce different signal."""
        idle_samples = [source.read_sample().channels[0] for _ in range(20)]

        source.inject_confirm(duration_samples=20)
        confirm_samples = [source.read_sample().channels[0] for _ in range(20)]

        idle_power = np.mean(np.array(idle_samples) ** 2)
        confirm_power = np.mean(np.array(confirm_samples) ** 2)
        assert confirm_power > idle_power, (
            f"Confirm power ({confirm_power:.2f}) should exceed idle ({idle_power:.2f})"
        )

    def test_scripted_mode(self):
        """Scripted mode follows explicit sequence."""
        source = SimulatedEEGSource(mode="scripted", seed=42)
        source.connect()
        source.set_script([
            ("idle", 10),
            ("confirm", 10),
            ("idle", 10),
        ])

        idle1 = [source.read_sample().channels[0] for _ in range(10)]
        confirm = [source.read_sample().channels[0] for _ in range(10)]
        idle2 = [source.read_sample().channels[0] for _ in range(10)]

        idle_power = np.mean(np.array(idle1 + idle2) ** 2)
        confirm_power = np.mean(np.array(confirm) ** 2)
        assert confirm_power > idle_power

        source.disconnect()

    def test_auto_mode_produces_mixed(self):
        """Auto mode should produce both confirm and idle."""
        source = SimulatedEEGSource(mode="auto", confirm_probability=0.5, seed=42)
        source.connect()
        for _ in range(200):
            source.read_sample()
        stats = source.stats
        assert stats["confirm_samples"] > 10
        assert stats["idle_samples"] > 10
        source.disconnect()

    def test_noise_level_affects_quality(self):
        """Higher noise = lower quality."""
        clean = SimulatedEEGSource(noise_level=0.1, seed=42)
        noisy = SimulatedEEGSource(noise_level=0.9, seed=42)
        clean.connect()
        noisy.connect()

        clean_q = clean.read_sample().quality
        noisy_q = noisy.read_sample().quality
        assert clean_q > noisy_q

        clean.disconnect()
        noisy.disconnect()

    def test_seed_reproducibility(self):
        """Same seed should produce same sequence."""
        s1 = SimulatedEEGSource(mode="auto", seed=123)
        s2 = SimulatedEEGSource(mode="auto", seed=123)
        s1.connect()
        s2.connect()

        for _ in range(50):
            sample1 = s1.read_sample()
            sample2 = s2.read_sample()
            np.testing.assert_array_equal(sample1.channels, sample2.channels)

        s1.disconnect()
        s2.disconnect()

    def test_no_nan_in_output(self, source):
        """No NaN should ever appear in EEG output."""
        source.inject_confirm(50)
        for _ in range(100):
            sample = source.read_sample()
            assert sample is not None
            assert not np.any(np.isnan(sample.channels))

    def test_stats_tracking(self, source):
        source.inject_confirm(5)
        for _ in range(5):
            source.read_sample()
        source.inject_idle(5)
        for _ in range(5):
            source.read_sample()

        stats = source.stats
        assert stats["samples"] == 10
        assert stats["confirm_samples"] == 5
        assert stats["idle_samples"] == 5
