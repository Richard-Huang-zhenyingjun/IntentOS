"""
EEG Decision Source — plugs raw EEG into the decision pipeline.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from src.input.source_base import DecisionSourceBase
from src.input.types import DecisionIntent, RawSourceReading, SourceType
from src.input.eeg.circuit_breaker import EEGCircuitBreaker
from src.input.eeg.decoder import EEGDecoder
from src.input.eeg.eeg_source import EEGSource
from src.input.eeg.features import FeatureExtractor
from src.input.eeg.mne_pipeline import MNEPipeline
from src.input.eeg.recorder import EEGRecorder
from src.input.eeg.ring_buffer import EEGRingBuffer

logger = logging.getLogger(__name__)


class EEGDecisionSource(DecisionSourceBase):
    """
    Raw EEG -> decision adapter.

    The router sees this as a standard decision source while the acquisition
    layer can swap between live, replay, and simulated EEG.
    """

    def __init__(self, source: EEGSource | None = None, config: dict | None = None, device: EEGSource | None = None):
        self.source = source or device
        if self.source is None:
            raise ValueError("EEGDecisionSource requires an EEGSource via 'source' or legacy 'device'")
        self.config = config or {}

        eeg_cfg = self.config.get("eeg", {})
        self.window_sec = eeg_cfg.get("window_sec", 1.0)
        self.step_sec = eeg_cfg.get("step_sec", 0.25)
        self.save_raw = self.config.get("logging", {}).get("eeg_save_raw", False)

        self.buffer = EEGRingBuffer(
            capacity_sec=self.window_sec * 3,
            expected_sfreq=self.source.sample_rate_hz,
        )
        self.mne_pipeline = MNEPipeline(self.config)
        self.feature_extractor = FeatureExtractor(self.config)
        self.decoder = EEGDecoder(self.config)
        self.circuit_breaker = EEGCircuitBreaker(self.config)

        self.recorder: Optional[EEGRecorder] = EEGRecorder() if self.save_raw else None
        self._latest_reading = RawSourceReading(
            intent=DecisionIntent.NONE,
            source_type=SourceType.EEG,
            quality=0.0,
        )
        self._reading_lock = threading.Lock()
        self._processing_thread: Optional[threading.Thread] = None
        self._running = False

        self.windows_processed = 0
        self.confirms_generated = 0

    def start(self) -> None:
        if self.recorder:
            self.recorder.start()
        if not self.source.connect():
            raise RuntimeError(f"Failed to connect EEG source: {self.source.__class__.__name__}")

        self._running = True
        self._processing_thread = threading.Thread(target=self._processing_loop, daemon=True)
        self._processing_thread.start()

        logger.info(
            "[EEG_SOURCE] Started (window=%.2fs, step=%.2fs, source=%s)",
            self.window_sec,
            self.step_sec,
            self.source.__class__.__name__,
        )

    def stop(self) -> None:
        self._running = False
        if self._processing_thread:
            self._processing_thread.join(timeout=3.0)

        self.source.disconnect()
        if self.recorder:
            self.recorder.stop()

        logger.info(
            "[EEG_SOURCE] Stopped. Windows processed: %d, Confirms: %d",
            self.windows_processed,
            self.confirms_generated,
        )

    def read_raw(self) -> RawSourceReading:
        if not self.circuit_breaker.is_allowing:
            return RawSourceReading(
                intent=DecisionIntent.NONE,
                source_type=SourceType.EEG,
                quality=0.0,
                metadata={"circuit_breaker": "open"},
            )

        with self._reading_lock:
            return self._latest_reading

    def source_type(self) -> SourceType:
        return SourceType.EEG

    def name(self) -> str:
        return f"eeg_{self.source.__class__.__name__.lower()}"

    def is_available(self) -> bool:
        return self.source.is_connected and self.circuit_breaker.is_allowing

    def _processing_loop(self) -> None:
        while self._running:
            start_time = time.time()

            try:
                self._ingest_available_samples()
                self._process_one_window()
                self.circuit_breaker.record_success()
            except Exception as exc:
                logger.warning("[EEG_SOURCE] Processing error: %s", exc)
                self.circuit_breaker.record_error(str(exc))
                with self._reading_lock:
                    self._latest_reading = RawSourceReading(
                        intent=DecisionIntent.NONE,
                        source_type=SourceType.EEG,
                        quality=0.0,
                        metadata={"error": str(exc)[:200]},
                    )

            if not self.source.is_connected:
                self.circuit_breaker.record_disconnect()

            elapsed = time.time() - start_time
            time.sleep(max(0.0, self.step_sec - elapsed))

    def _ingest_available_samples(self) -> None:
        max_samples = max(1, int(self.source.sample_rate_hz * self.step_sec * 2))
        ingested = 0
        while ingested < max_samples:
            sample = self.source.read_sample()
            if sample is None:
                break
            self.buffer.push(sample)
            if self.recorder:
                self.recorder.write_sample(sample)
            ingested += 1

    def _process_one_window(self) -> None:
        current_time_ms = time.time() * 1000.0
        raw_window = self.buffer.get_window(self.window_sec)

        if not raw_window.is_valid:
            with self._reading_lock:
                self._latest_reading = RawSourceReading(
                    intent=DecisionIntent.NONE,
                    source_type=SourceType.EEG,
                    quality=0.0,
                    metadata={"reason": "insufficient_data"},
                )
            return

        clean_window = self.mne_pipeline.process(raw_window)
        features = self.feature_extractor.extract(clean_window)
        intent, confidence, debug = self.decoder.decode(features, current_time_ms)

        combined_quality = (
            features.quality * confidence
            if intent == DecisionIntent.CONFIRM
            else features.quality
        )

        self.windows_processed += 1
        if intent == DecisionIntent.CONFIRM:
            self.confirms_generated += 1

        with self._reading_lock:
            self._latest_reading = RawSourceReading(
                intent=intent,
                source_type=SourceType.EEG,
                quality=combined_quality,
                raw_pressed=(intent == DecisionIntent.CONFIRM),
                metadata={
                    "decoder_debug": debug,
                    "features_quality": features.quality,
                    "decoder_confidence": confidence,
                    "spike_count": features.spike_count,
                    "window_id": self.windows_processed,
                },
            )
