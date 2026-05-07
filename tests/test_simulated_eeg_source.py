"""Tests for simulated raw EEG source."""
import time

from src.input.eeg.eeg_source_simulated import SimulatedEEGSource


def test_simulated_source_emits_samples():
    config = {
        "eeg": {
            "simulated": {
                "sample_rate_hz": 64,
                "n_channels": 1,
                "seed": 123,
            }
        }
    }
    source = SimulatedEEGSource(config)
    assert source.connect()

    sample = None
    deadline = time.time() + 0.2
    while sample is None and time.time() < deadline:
        sample = source.read_sample()
        time.sleep(0.002)

    source.disconnect()

    assert sample is not None
    assert sample.channels.shape == (1,)
    assert sample.source == "simulated"


def test_simulated_source_can_force_confirm_segment():
    config = {
        "eeg": {
            "simulated": {
                "sample_rate_hz": 128,
                "n_channels": 1,
                "confirm_spike_amplitude": 250.0,
                "seed": 7,
            }
        }
    }
    source = SimulatedEEGSource(config)
    source.force_label("confirm", duration_sec=0.5, quality=0.9)
    assert source.connect()

    samples = []
    deadline = time.time() + 0.3
    while len(samples) < 8 and time.time() < deadline:
        sample = source.read_sample()
        if sample is not None:
            samples.append(sample)
        time.sleep(0.001)

    source.disconnect()

    assert samples
    assert any(sample.label == "confirm" for sample in samples)
    assert max(sample.value for sample in samples) > 100.0
