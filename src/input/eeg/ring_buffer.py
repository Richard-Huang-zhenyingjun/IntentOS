"""
Thread-safe ring buffer for streaming EEG samples.

The BLE ingestion thread pushes samples.
The EEG processing thread extracts windows.
These run on different clocks.
"""
import threading
import numpy as np
import logging
from typing import Optional, Tuple
from src.input.eeg.types import EEGSample, EEGWindow

logger = logging.getLogger(__name__)


class EEGRingBuffer:
    """
    Thread-safe ring buffer for continuous EEG data.
    
    Stores last `capacity_sec` seconds of data.
    Supports window extraction for MNE processing.
    """
    
    def __init__(self, capacity_sec: float, expected_sfreq: float):
        """
        Args:
            capacity_sec: How many seconds of data to store
            expected_sfreq: Expected sampling frequency for sizing
        """
        self.capacity_sec = capacity_sec
        self.expected_sfreq = expected_sfreq
        self.capacity_samples = int(capacity_sec * expected_sfreq * 1.2)  # 20% headroom
        
        # Pre-allocate arrays
        self._values = np.zeros(self.capacity_samples, dtype=np.float64)
        self._timestamps = np.zeros(self.capacity_samples, dtype=np.float64)
        self._valid = np.ones(self.capacity_samples, dtype=bool)
        
        # Write position
        self._write_pos: int = 0
        self._total_written: int = 0
        
        # Thread safety
        self._lock = threading.Lock()
        
        # Metrics
        self.total_samples: int = 0
        self.dropped_samples: int = 0
    
    def push(self, sample: EEGSample):
        """Push a single sample (called from BLE thread)"""
        with self._lock:
            idx = self._write_pos % self.capacity_samples
            self._values[idx] = sample.value
            self._timestamps[idx] = sample.timestamp_ms
            self._valid[idx] = sample.valid
            self._write_pos += 1
            self._total_written += 1
            self.total_samples += 1
    
    def push_batch(self, values: np.ndarray, timestamps: np.ndarray):
        """Push multiple samples at once (for replay)"""
        with self._lock:
            n = len(values)
            for i in range(n):
                idx = (self._write_pos + i) % self.capacity_samples
                self._values[idx] = values[i]
                self._timestamps[idx] = timestamps[i]
                self._valid[idx] = True
            self._write_pos += n
            self._total_written += n
            self.total_samples += n
    
    def get_window(self, window_sec: float) -> EEGWindow:
        """
        Extract the most recent `window_sec` seconds of data.
        
        Returns:
            EEGWindow with data, timestamps, and dropout info.
            is_valid=False if insufficient data.
        """
        with self._lock:
            if self._total_written == 0:
                return EEGWindow(
                    data=np.array([]),
                    sfreq=self.expected_sfreq,
                    start_time_ms=0, end_time_ms=0,
                    n_raw_samples=0, dropout_fraction=1.0,
                    is_valid=False,
                )
            
            # Determine how many samples to extract
            n_available = min(self._total_written, self.capacity_samples)
            n_requested = int(window_sec * self.expected_sfreq)
            n_extract = min(n_requested, n_available)
            
            if n_extract < n_requested * 0.5:
                # Less than 50% of expected data → invalid window
                return EEGWindow(
                    data=np.array([]),
                    sfreq=self.expected_sfreq,
                    start_time_ms=0, end_time_ms=0,
                    n_raw_samples=n_extract,
                    dropout_fraction=1.0 - (n_extract / max(n_requested, 1)),
                    is_valid=False,
                )
            
            # Extract from ring buffer
            end_pos = self._write_pos
            start_pos = max(0, end_pos - n_extract)
            
            indices = np.arange(start_pos, end_pos) % self.capacity_samples
            data = self._values[indices].copy()
            timestamps = self._timestamps[indices].copy()
            valid = self._valid[indices]
            
            # Compute dropout
            n_invalid = int(np.sum(~valid))
            dropout_fraction = n_invalid / max(len(data), 1)
            
            # Also check for expected vs actual sample count
            if len(timestamps) >= 2:
                actual_duration_ms = timestamps[-1] - timestamps[0]
                expected_samples = actual_duration_ms / 1000.0 * self.expected_sfreq
                if expected_samples > 0:
                    sample_ratio = len(data) / expected_samples
                    if sample_ratio < 0.8:
                        dropout_fraction = max(dropout_fraction, 1.0 - sample_ratio)
            
            return EEGWindow(
                data=data,
                sfreq=self.expected_sfreq,
                start_time_ms=timestamps[0] if len(timestamps) > 0 else 0,
                end_time_ms=timestamps[-1] if len(timestamps) > 0 else 0,
                n_raw_samples=len(data),
                dropout_fraction=min(dropout_fraction, 1.0),
                is_valid=True,
            )
    
    def get_sample_count(self) -> int:
        with self._lock:
            return self._total_written


