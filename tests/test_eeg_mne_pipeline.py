"""Tests for MNE preprocessing pipeline"""
import pytest
import numpy as np


@pytest.fixture
def config():
    return {
        'mne': {'notch_hz': 60.0, 'bandpass_hz': [1.0, 40.0], 'resample_hz': None},
        'eeg': {'max_compute_ms': 100, 'expected_sfreq': 256},
    }


def test_pipeline_output_shape(config):
    try:
        from src.input.eeg.mne_pipeline import MNEPipeline
        from src.input.eeg.types import EEGWindow
    except ImportError:
        pytest.skip("MNE not installed")
    
    pipeline = MNEPipeline(config)
    
    data = np.random.randn(256)  # 1 second at 256 Hz
    window = EEGWindow(
        data=data, sfreq=256.0,
        start_time_ms=0, end_time_ms=1000,
        n_raw_samples=256, dropout_fraction=0.0,
    )
    
    result = pipeline.process(window)
    assert result.is_valid
    assert len(result.data) > 0


def test_pipeline_handles_short_window(config):
    try:
        from src.input.eeg.mne_pipeline import MNEPipeline
        from src.input.eeg.types import EEGWindow
        import mne
    except ImportError:
        pytest.skip("MNE not installed")
    
    pipeline = MNEPipeline(config)
    
    # Only test short window rejection if MNE is actually available
    if not pipeline._mne_available:
        pytest.skip("MNE not available, skipping short window test")
    
    window = EEGWindow(
        data=np.array([1.0, 2.0, 3.0]),
        sfreq=256.0,
        start_time_ms=0, end_time_ms=12,
        n_raw_samples=3, dropout_fraction=0.0,
        is_valid=True,
    )
    
    result = pipeline.process(window)
    assert not result.is_valid  # Too short

