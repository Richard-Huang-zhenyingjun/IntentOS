"""Tests for feature extraction and quality scoring"""
import pytest
import numpy as np
from src.input.eeg.features import FeatureExtractor
from src.input.eeg.types import EEGWindow


@pytest.fixture
def config():
    return {
        'eeg': {'expected_sfreq': 256},
        'eeg_quality': {
            'dropout_threshold': 0.10, 'dropout_penalty': 0.5,
            'clipping_threshold': 0.01, 'clipping_penalty': 0.3,
            'amplitude_low': 1.0, 'amplitude_high': 500.0, 'amplitude_penalty': 0.3,
            'noise_ratio_threshold': 0.3, 'noise_penalty': 0.2,
        },
        'decoder': {'spike_z_thresh': 3.5},
    }


def test_quality_in_range(config):
    extractor = FeatureExtractor(config)
    data = np.random.randn(256) * 20  # Normal EEG-like signal
    window = EEGWindow(
        data=data, sfreq=256.0,
        start_time_ms=0, end_time_ms=1000,
        n_raw_samples=256, dropout_fraction=0.0,
    )
    
    features = extractor.extract(window)
    assert 0.0 <= features.quality <= 1.0


def test_dropout_reduces_quality(config):
    extractor = FeatureExtractor(config)
    data = np.random.randn(256) * 20
    
    # Good window
    good_window = EEGWindow(
        data=data, sfreq=256.0,
        start_time_ms=0, end_time_ms=1000,
        n_raw_samples=256, dropout_fraction=0.0,
    )
    
    # Bad window (high dropout)
    bad_window = EEGWindow(
        data=data, sfreq=256.0,
        start_time_ms=0, end_time_ms=1000,
        n_raw_samples=256, dropout_fraction=0.5,
    )
    
    good_features = extractor.extract(good_window)
    bad_features = extractor.extract(bad_window)
    
    assert bad_features.quality < good_features.quality


def test_spike_detection(config):
    extractor = FeatureExtractor(config)
    
    data = np.random.randn(256) * 5
    data[100] = 200  # Big spike
    data[150] = 180  # Another spike
    
    window = EEGWindow(
        data=data, sfreq=256.0,
        start_time_ms=0, end_time_ms=1000,
        n_raw_samples=256, dropout_fraction=0.0,
    )
    
    features = extractor.extract(window)
    assert features.spike_count >= 1
    assert features.max_spike_zscore > 3.0


def test_invalid_window_returns_zero_quality(config):
    extractor = FeatureExtractor(config)
    
    window = EEGWindow(
        data=np.array([]), sfreq=256.0,
        start_time_ms=0, end_time_ms=0,
        n_raw_samples=0, dropout_fraction=1.0,
        is_valid=False,
    )
    
    features = extractor.extract(window)
    assert features.quality == 0.0



