"""
Mock EEG decision source for testing the pipeline without hardware.

Simulates realistic EEG behavior:
- Quality fluctuates (noisy signal)
- Occasional "confirm" signals at configurable probability
- Artifact bursts (quality drops to 0)
- Can be controlled programmatically for tests
"""
import numpy as np
import logging
from src.input.source_base import DecisionSourceBase
from src.input.types import RawSourceReading, DecisionIntent, SourceType

logger = logging.getLogger(__name__)


class MockEEGSource(DecisionSourceBase):
    """
    Simulated EEG decision source.
    
    Produces noisy confirm/cancel signals with variable quality.
    Useful for testing quality gating without real hardware.
    """
    
    def __init__(self, config: dict):
        eeg_cfg = config.get('eeg_mock', {})
        
        self.enabled = eeg_cfg.get('enabled', False)
        self.confirm_probability = eeg_cfg.get('confirm_probability', 0.02)
        self.quality_mean = eeg_cfg.get('quality_mean', 0.5)
        self.quality_std = eeg_cfg.get('quality_std', 0.15)
        self.artifact_probability = eeg_cfg.get('artifact_probability', 0.05)
        self.seed = eeg_cfg.get('seed', None)
        
        self._rng = np.random.RandomState(self.seed)
        
        # Manual override for testing
        self._override_intent: DecisionIntent = None
        self._override_quality: float = None
    
    def read_raw(self) -> RawSourceReading:
        """Generate simulated EEG reading"""
        if not self.enabled:
            return RawSourceReading(
                intent=DecisionIntent.NONE,
                source_type=SourceType.MOCK_EEG,
                quality=0.0,
            )
        
        # Check manual override first
        if self._override_intent is not None:
            intent = self._override_intent
            quality = self._override_quality if self._override_quality is not None else self.quality_mean
            self._override_intent = None
            self._override_quality = None
            
            return RawSourceReading(
                intent=intent,
                source_type=SourceType.MOCK_EEG,
                quality=np.clip(quality, 0.0, 1.0),
                raw_pressed=(intent == DecisionIntent.CONFIRM),
                metadata={'override': True}
            )
        
        # Simulate quality fluctuation
        if self._rng.random() < self.artifact_probability:
            # Artifact burst → quality drops to near zero
            quality = self._rng.uniform(0.0, 0.1)
        else:
            quality = np.clip(
                self._rng.normal(self.quality_mean, self.quality_std),
                0.0, 1.0
            )
        
        # Simulate confirm signal
        if self._rng.random() < self.confirm_probability:
            intent = DecisionIntent.CONFIRM
        else:
            intent = DecisionIntent.NONE
        
        return RawSourceReading(
            intent=intent,
            source_type=SourceType.MOCK_EEG,
            quality=quality,
            raw_pressed=(intent == DecisionIntent.CONFIRM),
            metadata={'simulated': True, 'artifact': quality < 0.1}
        )
    
    def source_type(self) -> SourceType:
        return SourceType.MOCK_EEG
    
    def name(self) -> str:
        return "mock_eeg"
    
    def is_available(self) -> bool:
        return self.enabled
    
    # === Test Control Methods ===
    
    def inject_confirm(self, quality: float = 0.8):
        """Inject a confirm signal for next read"""
        self._override_intent = DecisionIntent.CONFIRM
        self._override_quality = quality
    
    def inject_cancel(self, quality: float = 0.8):
        """Inject a cancel signal for next read"""
        self._override_intent = DecisionIntent.CANCEL
        self._override_quality = quality
    
    def inject_none(self, quality: float = 0.5):
        """Inject no-signal for next read"""
        self._override_intent = DecisionIntent.NONE
        self._override_quality = quality


