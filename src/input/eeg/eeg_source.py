"""
EEG Decision Source — plugs into Week 5 pipeline.

Orchestrates: Device → Buffer → Window → MNE → Features → Decoder → RawSourceReading

This is the main integration point. The router sees this as just another
DecisionSourceBase that returns RawSourceReading.
"""
import time
import threading
import logging
from typing import Optional
import numpy as np

from src.input.source_base import DecisionSourceBase
from src.input.types import RawSourceReading, DecisionIntent, SourceType
from src.input.eeg.device_base import EEGDeviceBase
from src.input.eeg.ring_buffer import EEGRingBuffer
from src.input.eeg.mne_pipeline import MNEPipeline
from src.input.eeg.features import FeatureExtractor
from src.input.eeg.decoder import EEGDecoder
from src.input.eeg.circuit_breaker import EEGCircuitBreaker
from src.input.eeg.recorder import EEGRecorder
from src.input.eeg.types import EEGSample

logger = logging.getLogger(__name__)


class EEGDecisionSource(DecisionSourceBase):
    """
    Real EEG decision source using BrainLink → MNE pipeline.
    
    Architecture:
    - Device pushes samples into ring buffer (BLE thread)
    - Processing runs at decision_rate (separate thread or timer)
    - Main thread reads latest_frame (thread-safe)
    
    The sim never waits for EEG processing.
    """
    
    def __init__(
        self,
        device: EEGDeviceBase,
        config: dict,
    ):
        self.device = device
        self.config = config
        
        eeg_cfg = config.get('eeg', {})
        self.window_sec = eeg_cfg.get('window_sec', 1.0)
        self.step_sec = eeg_cfg.get('step_sec', 0.25)
        self.save_raw = config.get('logging', {}).get('eeg_save_raw', False)
        
        # Pipeline components
        self.buffer = EEGRingBuffer(
            capacity_sec=self.window_sec * 3,
            expected_sfreq=device.get_sfreq(),
        )
        self.mne_pipeline = MNEPipeline(config)
        self.feature_extractor = FeatureExtractor(config)
        self.decoder = EEGDecoder(config)
        self.circuit_breaker = EEGCircuitBreaker(config)
        
        # Optional recorder
        self.recorder: Optional[EEGRecorder] = None
        if self.save_raw:
            self.recorder = EEGRecorder()
        
        # Latest frame (thread-safe via lock)
        self._latest_reading = RawSourceReading(
            intent=DecisionIntent.NONE,
            source_type=SourceType.EEG,
            quality=0.0,
        )
        self._reading_lock = threading.Lock()
        
        # Processing thread
        self._processing_thread: Optional[threading.Thread] = None
        self._running = False
        
        # Metrics
        self.windows_processed: int = 0
        self.confirms_generated: int = 0
    
    def start(self):
        """Start device and processing pipeline"""
        # Set up device callback → buffer
        self.device.set_callback(self._on_sample)
        
        # Start recorder if enabled
        if self.recorder:
            self.recorder.start()
        
        # Start device
        self.device.start()
        
        # Start processing thread
        self._running = True
        self._processing_thread = threading.Thread(
            target=self._processing_loop, daemon=True
        )
        self._processing_thread.start()
        
        logger.info(
            f"[EEG_SOURCE] Started (window={self.window_sec}s, "
            f"step={self.step_sec}s, device={self.device.__class__.__name__})"
        )
    
    def stop(self):
        """Stop everything cleanly"""
        self._running = False
        
        if self._processing_thread:
            self._processing_thread.join(timeout=3.0)
        
        self.device.stop()
        
        if self.recorder:
            self.recorder.stop()
        
        logger.info(
            f"[EEG_SOURCE] Stopped. "
            f"Windows processed: {self.windows_processed}, "
            f"Confirms: {self.confirms_generated}"
        )
    
    def read_raw(self) -> RawSourceReading:
        """
        Return latest processed reading (called by router at sim rate).
        Non-blocking: returns cached result from processing thread.
        """
        if not self.circuit_breaker.is_allowing:
            return RawSourceReading(
                intent=DecisionIntent.NONE,
                source_type=SourceType.EEG,
                quality=0.0,
                metadata={'circuit_breaker': 'open'},
            )
        
        with self._reading_lock:
            return self._latest_reading
    
    def source_type(self) -> SourceType:
        return SourceType.EEG
    
    def name(self) -> str:
        return "eeg_brainlink"
    
    def is_available(self) -> bool:
        return (
            self.device.is_connected()
            and self.circuit_breaker.is_allowing
        )
    
    # === Internal Methods ===
    
    def _on_sample(self, sample: EEGSample):
        """Callback from device (BLE thread)"""
        self.buffer.push(sample)
        
        if self.recorder:
            self.recorder.write_sample(sample)
    
    def _processing_loop(self):
        """
        Background thread: process windows at decision rate.
        Runs at ~4Hz (every step_sec seconds).
        """
        while self._running:
            start_time = time.time()
            
            try:
                self._process_one_window()
                self.circuit_breaker.record_success()
                
            except Exception as e:
                logger.warning(f"[EEG_SOURCE] Processing error: {e}")
                self.circuit_breaker.record_error(str(e))
                
                # On error, set reading to NONE
                with self._reading_lock:
                    self._latest_reading = RawSourceReading(
                        intent=DecisionIntent.NONE,
                        source_type=SourceType.EEG,
                        quality=0.0,
                        metadata={'error': str(e)[:200]},
                    )
            
            # Check device connection
            if not self.device.is_connected():
                self.circuit_breaker.record_disconnect()
            
            # Sleep until next window
            elapsed = time.time() - start_time
            sleep_time = max(0, self.step_sec - elapsed)
            time.sleep(sleep_time)
    
    def _process_one_window(self):
        """Process one EEG window through the full pipeline"""
        current_time_ms = time.time() * 1000
        
        # Step 1: Extract window from buffer
        raw_window = self.buffer.get_window(self.window_sec)
        
        if not raw_window.is_valid:
            with self._reading_lock:
                self._latest_reading = RawSourceReading(
                    intent=DecisionIntent.NONE,
                    source_type=SourceType.EEG,
                    quality=0.0,
                    metadata={'reason': 'insufficient_data'},
                )
            return
        
        # Step 2: MNE preprocessing
        clean_window = self.mne_pipeline.process(raw_window)
        
        # Step 3: Feature extraction + quality
        features = self.feature_extractor.extract(clean_window)
        
        # Step 4: Decode intent
        intent, confidence, debug = self.decoder.decode(features, current_time_ms)
        
        # Step 5: Combine quality
        combined_quality = features.quality * confidence if intent == DecisionIntent.CONFIRM else features.quality
        
        self.windows_processed += 1
        if intent == DecisionIntent.CONFIRM:
            self.confirms_generated += 1
        
        # Step 6: Update latest reading
        with self._reading_lock:
            self._latest_reading = RawSourceReading(
                intent=intent,
                source_type=SourceType.EEG,
                quality=combined_quality,
                raw_pressed=(intent == DecisionIntent.CONFIRM),
                metadata={
                    'decoder_debug': debug,
                    'features_quality': features.quality,
                    'decoder_confidence': confidence,
                    'spike_count': features.spike_count,
                    'window_id': self.windows_processed,
                },
            )



