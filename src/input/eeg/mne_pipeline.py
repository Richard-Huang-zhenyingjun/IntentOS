"""
MNE preprocessing pipeline for single-channel EEG windows.

Bounded: must complete within max_compute_ms.
Stateless: each window processed independently.
Safe: returns invalid window on any error.
"""
import time
import logging
import numpy as np
from typing import Optional
from src.input.eeg.types import EEGWindow

logger = logging.getLogger(__name__)

# Lazy import MNE (heavy library)
_mne = None

def _get_mne():
    global _mne
    if _mne is None:
        try:
            import mne
            mne.set_log_level('WARNING')  # Suppress MNE verbose output
            _mne = mne
        except ImportError:
            logger.error("[MNE] mne-python not installed")
    return _mne


class MNEPipeline:
    """
    Applies MNE preprocessing to a single-channel EEG window.
    
    Steps:
    1. Create MNE RawArray from numpy data
    2. Apply notch filter (60Hz for Toronto)
    3. Apply bandpass filter (1-40 Hz)
    4. Optional: resample to fixed rate
    
    Compute budget: must complete within max_compute_ms.
    """
    
    def __init__(self, config: dict):
        mne_cfg = config.get('mne', {})
        eeg_cfg = config.get('eeg', {})
        
        self.notch_hz = mne_cfg.get('notch_hz', 60.0)
        self.bandpass_low = mne_cfg.get('bandpass_hz', [1.0, 40.0])[0]
        self.bandpass_high = mne_cfg.get('bandpass_hz', [1.0, 40.0])[1]
        self.resample_hz = mne_cfg.get('resample_hz', None)
        self.max_compute_ms = eeg_cfg.get('max_compute_ms', 15)
        
        # Channel info
        self.ch_names = ['Fp1']  # BrainLink Lite is forehead (Fp1)
        self.ch_types = ['eeg']
        
        # Check MNE availability
        self._mne_available = _get_mne() is not None
    
    def process(self, window: EEGWindow) -> EEGWindow:
        """
        Preprocess a raw EEG window.
        
        Returns:
            New EEGWindow with cleaned data and updated sfreq.
            Returns window with is_valid=False on any error.
        """
        if not window.is_valid:
            return window
        
        if not self._mne_available:
            logger.warning("[MNE] MNE not available, returning raw window")
            return window
        
        if len(window.data) < 10:
            return EEGWindow(
                data=window.data, sfreq=window.sfreq,
                start_time_ms=window.start_time_ms,
                end_time_ms=window.end_time_ms,
                n_raw_samples=window.n_raw_samples,
                dropout_fraction=window.dropout_fraction,
                is_valid=False,
            )
        
        mne = _get_mne()
        start_time = time.time()
        
        try:
            # Step 1: Create MNE RawArray
            data_2d = window.data.reshape(1, -1)  # (1, n_samples)
            
            # Scale to volts if data is in microvolts
            # BrainLink raw values are typically arbitrary units
            # MNE expects volts, but for our purposes scaling doesn't matter
            # as long as it's consistent
            data_volts = data_2d * 1e-6  # Assume microvolts → volts
            
            info = mne.create_info(
                ch_names=self.ch_names,
                sfreq=window.sfreq,
                ch_types=self.ch_types,
            )
            raw = mne.io.RawArray(data_volts, info, verbose=False)
            
            # Step 2: Notch filter (remove line noise)
            if self.notch_hz and window.sfreq > 2 * self.notch_hz:
                raw.notch_filter(
                    freqs=self.notch_hz,
                    verbose=False,
                )
            
            # Step 3: Bandpass filter
            if window.sfreq > 2 * self.bandpass_high:
                raw.filter(
                    l_freq=self.bandpass_low,
                    h_freq=self.bandpass_high,
                    verbose=False,
                )
            
            # Step 4: Optional resample
            out_sfreq = window.sfreq
            if self.resample_hz and self.resample_hz != window.sfreq:
                raw.resample(self.resample_hz, verbose=False)
                out_sfreq = self.resample_hz
            
            # Extract processed data
            processed_data = raw.get_data()[0]  # (n_samples,)
            processed_data = processed_data / 1e-6  # Back to microvolts
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            if elapsed_ms > self.max_compute_ms:
                logger.warning(
                    f"[MNE] Processing took {elapsed_ms:.1f}ms "
                    f"(budget={self.max_compute_ms}ms)"
                )
            
            return EEGWindow(
                data=processed_data,
                sfreq=out_sfreq,
                start_time_ms=window.start_time_ms,
                end_time_ms=window.end_time_ms,
                n_raw_samples=window.n_raw_samples,
                dropout_fraction=window.dropout_fraction,
                is_valid=True,
            )
            
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(f"[MNE] Processing failed ({elapsed_ms:.1f}ms): {e}")
            
            return EEGWindow(
                data=window.data,
                sfreq=window.sfreq,
                start_time_ms=window.start_time_ms,
                end_time_ms=window.end_time_ms,
                n_raw_samples=window.n_raw_samples,
                dropout_fraction=window.dropout_fraction,
                is_valid=False,
            )


