"""
Records raw EEG samples to CSV for replay and debugging.
"""
import csv
import time
import logging
from pathlib import Path
from typing import Optional
from src.input.eeg.types import EEGSample

logger = logging.getLogger(__name__)


class EEGRecorder:
    """
    Records raw EEG samples to CSV file.
    Thread-safe: can be called from BLE callback thread.
    """
    
    def __init__(self, output_dir: str = "runs"):
        self.output_dir = Path(output_dir)
        self._writer = None
        self._file = None
        self._filepath: Optional[Path] = None
        self._sample_count = 0
    
    def start(self, session_name: Optional[str] = None):
        """Begin recording to a new CSV file"""
        if session_name is None:
            session_name = time.strftime("%Y%m%d_%H%M%S")
        
        session_dir = self.output_dir / session_name
        session_dir.mkdir(parents=True, exist_ok=True)
        
        self._filepath = session_dir / "eeg_raw.csv"
        self._file = open(self._filepath, 'w', newline='')
        self._writer = csv.writer(self._file)
        self._writer.writerow(['timestamp_ms', 'value', 'channel', 'valid'])
        self._sample_count = 0
        
        logger.info(f"[RECORDER] Recording to {self._filepath}")
    
    def write_sample(self, sample: EEGSample):
        """Write a single sample (thread-safe with CSV writer)"""
        if self._writer:
            self._writer.writerow([
                f"{sample.timestamp_ms:.3f}",
                f"{sample.value:.6f}",
                sample.channel,
                1 if sample.valid else 0,
            ])
            self._sample_count += 1
            
            # Flush periodically
            if self._sample_count % 512 == 0:
                self._file.flush()
    
    def stop(self) -> Optional[str]:
        """Stop recording, return filepath"""
        if self._file:
            self._file.close()
            self._file = None
            self._writer = None
            
            logger.info(f"[RECORDER] Saved {self._sample_count} samples to {self._filepath}")
            return str(self._filepath)
        return None



