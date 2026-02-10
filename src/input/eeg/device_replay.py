"""
Replay device — reads recorded CSV and feeds samples at original timing.
Enables deterministic testing without hardware.
"""
import csv
import time
import threading
import logging
import numpy as np
from pathlib import Path
from typing import Callable, Optional
from src.input.eeg.device_base import EEGDeviceBase
from src.input.eeg.types import EEGSample

logger = logging.getLogger(__name__)


class ReplayDevice(EEGDeviceBase):
    """
    Replays recorded EEG session from CSV file.
    
    CSV format:
        timestamp_ms,value,channel,valid
        0.0,12.5,0,1
        1.953,13.1,0,1
        ...
    
    Supports two modes:
    - real_time=True: replay at original timing (for demos)
    - real_time=False: feed all data immediately (for tests)
    """
    
    def __init__(self, filepath: str, real_time: bool = False):
        self.filepath = Path(filepath)
        self.real_time = real_time
        self._callback: Optional[Callable] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._sfreq = 512.0  # Will be estimated from data
        self._samples_fed = 0
    
    def start(self):
        """Begin replaying data"""
        if not self.filepath.exists():
            raise FileNotFoundError(f"Recording not found: {self.filepath}")
        
        self._running = True
        
        if self.real_time:
            self._thread = threading.Thread(target=self._replay_realtime, daemon=True)
            self._thread.start()
        else:
            self._replay_instant()
    
    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
    
    def is_connected(self) -> bool:
        return self._running
    
    def set_callback(self, callback: Callable[[EEGSample], None]):
        self._callback = callback
    
    def get_sfreq(self) -> float:
        return self._sfreq
    
    def _load_csv(self):
        """Load CSV into arrays"""
        timestamps = []
        values = []
        
        with open(self.filepath, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                timestamps.append(float(row['timestamp_ms']))
                values.append(float(row['value']))
        
        timestamps = np.array(timestamps)
        values = np.array(values)
        
        # Estimate sfreq from timestamps
        if len(timestamps) > 1:
            dt_ms = np.median(np.diff(timestamps))
            if dt_ms > 0:
                self._sfreq = 1000.0 / dt_ms
        
        logger.info(
            f"[REPLAY] Loaded {len(values)} samples, "
            f"estimated sfreq={self._sfreq:.1f} Hz, "
            f"duration={timestamps[-1] - timestamps[0]:.0f} ms"
        )
        
        return timestamps, values
    
    def _replay_instant(self):
        """Feed all data immediately (for tests)"""
        timestamps, values = self._load_csv()
        
        for i in range(len(values)):
            if not self._running:
                break
            if self._callback:
                sample = EEGSample(
                    timestamp_ms=timestamps[i],
                    value=values[i],
                    channel=0,
                    valid=True,
                )
                self._callback(sample)
                self._samples_fed += 1
        
        self._running = False
    
    def _replay_realtime(self):
        """Feed data at original timing (for demos)"""
        timestamps, values = self._load_csv()
        
        if len(timestamps) == 0:
            self._running = False
            return
        
        start_real = time.time()
        start_recording = timestamps[0] / 1000.0
        
        for i in range(len(values)):
            if not self._running:
                break
            
            # Wait until real-time matches recording time
            target_real = start_real + (timestamps[i] / 1000.0 - start_recording)
            now = time.time()
            if target_real > now:
                time.sleep(target_real - now)
            
            if self._callback:
                sample = EEGSample(
                    timestamp_ms=timestamps[i],
                    value=values[i],
                    channel=0,
                    valid=True,
                )
                self._callback(sample)
                self._samples_fed += 1
        
        self._running = False


