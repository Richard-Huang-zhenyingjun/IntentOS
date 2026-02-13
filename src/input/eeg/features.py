"""
Feature extraction and quality scoring from preprocessed EEG windows.

Quality model: penalty-based, starting from 1.0.
Each quality penalty maps to a real-world failure mode:
- Dropouts → BLE packet loss
- Clipping → electrode saturation
- High amplitude → movement artifact
- Line noise → environmental interference
"""
import numpy as np
import logging
from src.input.eeg.types import EEGWindow, EEGFeatures

logger = logging.getLogger(__name__)


class FeatureExtractor:
    """
    Extracts features and computes quality score from preprocessed EEG window.
    """
    
    def __init__(self, config: dict):
        eeg_cfg = config.get('eeg', {})
        quality_cfg = config.get('eeg_quality', {})
        
        self.expected_sfreq = eeg_cfg.get('expected_sfreq', 512)
        
        # Quality penalty thresholds
        self.dropout_threshold = quality_cfg.get('dropout_threshold', 0.10)
        self.dropout_penalty = quality_cfg.get('dropout_penalty', 0.5)
        
        self.clipping_threshold = quality_cfg.get('clipping_threshold', 0.01)
        self.clipping_penalty = quality_cfg.get('clipping_penalty', 0.3)
        
        self.amplitude_low = quality_cfg.get('amplitude_low', 1.0)
        self.amplitude_high = quality_cfg.get('amplitude_high', 500.0)
        self.amplitude_penalty = quality_cfg.get('amplitude_penalty', 0.3)
        
        self.noise_ratio_threshold = quality_cfg.get('noise_ratio_threshold', 0.3)
        self.noise_penalty = quality_cfg.get('noise_penalty', 0.2)
        
        # Spike detection params (for blink/clench decoder)
        self.spike_z_threshold = config.get('decoder', {}).get('spike_z_thresh', 3.5)
    
    def extract(self, window: EEGWindow) -> EEGFeatures:
        """
        Extract features and compute quality from preprocessed window.
        
        Returns EEGFeatures with quality in [0, 1].
        Never raises exceptions — returns zero-quality on any error.
        """
        if not window.is_valid or len(window.data) < 10:
            return EEGFeatures(quality=0.0, dropout_fraction=window.dropout_fraction)
        
        try:
            data = window.data
            n = len(data)
            
            # Amplitude features
            rms = float(np.sqrt(np.mean(data ** 2)))
            peak_amplitude = float(np.max(np.abs(data)))
            
            # Clipping detection
            if peak_amplitude > 0:
                clip_val = peak_amplitude * 0.99
                clipping_fraction = float(np.mean(np.abs(data) > clip_val))
            else:
                clipping_fraction = 0.0
            
            # Spectral features (via FFT)
            bandpowers = self._compute_bandpowers(data, window.sfreq)
            
            # Line noise ratio
            line_noise_ratio = self._compute_line_noise_ratio(data, window.sfreq)
            
            # Spike detection
            spike_count, max_spike_z, spike_timestamps = self._detect_spikes(
                data, window.sfreq, window.start_time_ms
            )
            
            # Quality score (penalty-based)
            quality = self._compute_quality(
                dropout_fraction=window.dropout_fraction,
                clipping_fraction=clipping_fraction,
                rms=rms,
                peak_amplitude=peak_amplitude,
                line_noise_ratio=line_noise_ratio,
            )
            
            return EEGFeatures(
                rms=rms,
                peak_amplitude=peak_amplitude,
                bandpower_delta=bandpowers.get('delta', 0.0),
                bandpower_theta=bandpowers.get('theta', 0.0),
                bandpower_alpha=bandpowers.get('alpha', 0.0),
                bandpower_beta=bandpowers.get('beta', 0.0),
                line_noise_ratio=line_noise_ratio,
                clipping_fraction=clipping_fraction,
                dropout_fraction=window.dropout_fraction,
                spike_count=spike_count,
                max_spike_zscore=max_spike_z,
                spike_timestamps_ms=spike_timestamps,
                quality=quality,
            )
            
        except Exception as e:
            logger.warning(f"[FEATURES] Extraction failed: {e}")
            return EEGFeatures(quality=0.0, dropout_fraction=window.dropout_fraction)
    
    def _compute_bandpowers(self, data: np.ndarray, sfreq: float) -> dict:
        """Compute bandpower in standard EEG bands"""
        n = len(data)
        freqs = np.fft.rfftfreq(n, 1.0 / sfreq)
        psd = np.abs(np.fft.rfft(data)) ** 2 / n
        
        bands = {
            'delta': (1.0, 4.0),
            'theta': (4.0, 8.0),
            'alpha': (8.0, 13.0),
            'beta': (13.0, 30.0),
        }
        
        result = {}
        total_power = float(np.sum(psd))
        
        for band_name, (low, high) in bands.items():
            mask = (freqs >= low) & (freqs < high)
            band_power = float(np.sum(psd[mask]))
            result[band_name] = band_power / max(total_power, 1e-10)
        
        return result
    
    def _compute_line_noise_ratio(self, data: np.ndarray, sfreq: float) -> float:
        """Compute ratio of 60Hz power to total power"""
        n = len(data)
        if n < 10:
            return 0.0
        
        freqs = np.fft.rfftfreq(n, 1.0 / sfreq)
        psd = np.abs(np.fft.rfft(data)) ** 2 / n
        
        # 60 Hz ± 2 Hz band
        noise_mask = (freqs >= 58.0) & (freqs <= 62.0)
        noise_power = float(np.sum(psd[noise_mask]))
        total_power = float(np.sum(psd))
        
        return noise_power / max(total_power, 1e-10)
    
    def _detect_spikes(
        self, data: np.ndarray, sfreq: float, start_time_ms: float
    ) -> tuple:
        """
        Detect amplitude spikes (blinks, jaw clenches).
        Returns (count, max_zscore, timestamps_ms).
        """
        mean = np.mean(data)
        std = np.std(data)
        
        if std < 1e-10:
            return 0, 0.0, []
        
        zscores = np.abs((data - mean) / std)
        spike_mask = zscores > self.spike_z_threshold
        spike_indices = np.where(spike_mask)[0]
        
        if len(spike_indices) == 0:
            return 0, 0.0, []
        
        # Merge nearby spikes (within 50ms)
        merge_samples = int(0.05 * sfreq)
        merged_spikes = []
        last_idx = -merge_samples - 1
        
        for idx in spike_indices:
            if idx - last_idx > merge_samples:
                merged_spikes.append(idx)
            last_idx = idx
        
        spike_timestamps = [
            start_time_ms + (idx / sfreq) * 1000
            for idx in merged_spikes
        ]
        
        max_z = float(np.max(zscores[spike_mask]))
        
        return len(merged_spikes), max_z, spike_timestamps
    
    def _compute_quality(
        self,
        dropout_fraction: float,
        clipping_fraction: float,
        rms: float,
        peak_amplitude: float,
        line_noise_ratio: float,
    ) -> float:
        """
        Compute quality score via penalty model.
        Starts at 1.0, subtracts penalties for each issue.
        """
        quality = 1.0
        
        # Dropout penalty
        if dropout_fraction > self.dropout_threshold:
            quality -= self.dropout_penalty
        
        # Clipping penalty
        if clipping_fraction > self.clipping_threshold:
            quality -= self.clipping_penalty
        
        # Amplitude range penalty (poor contact or movement)
        if rms < self.amplitude_low or peak_amplitude > self.amplitude_high:
            quality -= self.amplitude_penalty
        
        # Line noise penalty
        if line_noise_ratio > self.noise_ratio_threshold:
            quality -= self.noise_penalty
        
        return float(np.clip(quality, 0.0, 1.0))



