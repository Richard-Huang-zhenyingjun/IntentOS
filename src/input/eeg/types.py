"""
EEG data types — internal to the EEG pipeline.
Nothing in src/core/ or src/execution/ imports these directly.
"""
from dataclasses import dataclass, field
from typing import List
import numpy as np
from src.input.eeg.eeg_source import EEGSample


@dataclass
class EEGWindow:
    """
    Fixed-size window of preprocessed EEG data.
    Ready for feature extraction and decoding.
    """
    data: np.ndarray          # Shape: (n_samples,) for single channel
    sfreq: float              # Sampling frequency after resampling
    start_time_ms: float      # Window start timestamp
    end_time_ms: float        # Window end timestamp
    n_raw_samples: int        # Samples received before resampling
    dropout_fraction: float   # Fraction of expected samples that were missing
    is_valid: bool = True     # False if insufficient data


@dataclass
class EEGFeatures:
    """
    Extracted features from a preprocessed window.
    Used for quality scoring and decoding.
    """
    # Amplitude
    rms: float = 0.0
    peak_amplitude: float = 0.0
    
    # Spectral
    bandpower_delta: float = 0.0    # 1-4 Hz
    bandpower_theta: float = 0.0    # 4-8 Hz
    bandpower_alpha: float = 0.0    # 8-13 Hz
    bandpower_beta: float = 0.0     # 13-30 Hz
    
    # Quality indicators
    line_noise_ratio: float = 0.0   # 60Hz power / total
    clipping_fraction: float = 0.0  # Fraction of samples at rail
    dropout_fraction: float = 0.0
    
    # Spike detection (for blink/clench decoder)
    spike_count: int = 0
    max_spike_zscore: float = 0.0
    spike_timestamps_ms: List[float] = field(default_factory=list)
    
    # Computed quality
    quality: float = 0.0            # 0.0-1.0, computed by features.py
    
    # Debug
    compute_time_ms: float = 0.0


