"""
EEG decoder: window features → intent + confidence.

Week 6 decoder: simple spike/threshold heuristic.
Detects blink or jaw clench patterns as CONFIRM signals.
No ML training required.
"""
import time
import logging
from src.input.eeg.types import EEGFeatures
from src.input.types import DecisionIntent

logger = logging.getLogger(__name__)


class EEGDecoder:
    """
    Heuristic decoder for single-channel BrainLink EEG.
    
    Strategy: Detect deliberate double-blink or jaw clench pattern.
    
    Detection logic:
    1. Look for spike events (z-score > threshold)
    2. Require specific pattern (e.g., 2 spikes within 1 second)
    3. Enforce minimum interval between confirms
    
    This is a demo-grade decoder. Replace with ML in later weeks.
    """
    
    def __init__(self, config: dict):
        decoder_cfg = config.get('decoder', {})
        
        self.decoder_type = decoder_cfg.get('type', 'blink_spike')
        self.spike_z_thresh = decoder_cfg.get('spike_z_thresh', 3.5)
        self.min_spikes_for_confirm = decoder_cfg.get('min_spikes_for_confirm', 2)
        self.min_interval_ms = decoder_cfg.get('min_interval_ms', 1200)
        self.confidence_scale = decoder_cfg.get('confidence_scale', 1.0)
        
        # Beta sustain alternative
        self.beta_threshold = decoder_cfg.get('beta_threshold', 0.3)
        self.sustain_windows = decoder_cfg.get('sustain_windows', 3)
        
        # State
        self._last_confirm_time_ms: float = -999999.0  # Allow first confirm immediately
        self._consecutive_beta_high: int = 0
    
    def decode(self, features: EEGFeatures, current_time_ms: float) -> tuple:
        """
        Decode features into intent + confidence.
        
        Args:
            features: Extracted EEG features for this window
            current_time_ms: Current time for interval enforcement
            
        Returns:
            (intent: DecisionIntent, confidence: float, debug: dict)
        """
        if features.quality < 0.1:
            return (
                DecisionIntent.NONE, 0.0,
                {'reason': 'quality_too_low', 'quality': features.quality}
            )
        
        if self.decoder_type == 'blink_spike':
            return self._decode_blink_spike(features, current_time_ms)
        elif self.decoder_type == 'beta_sustain':
            return self._decode_beta_sustain(features, current_time_ms)
        else:
            return (DecisionIntent.NONE, 0.0, {'reason': 'unknown_decoder_type'})
    
    def _decode_blink_spike(
        self, features: EEGFeatures, current_time_ms: float
    ) -> tuple:
        """
        Detect deliberate blink/clench pattern.
        
        Confirm if:
        - At least min_spikes_for_confirm spikes detected
        - Max z-score above threshold
        - Sufficient time since last confirm
        """
        debug = {
            'decoder': 'blink_spike',
            'spike_count': features.spike_count,
            'max_zscore': features.max_spike_zscore,
            'quality': features.quality,
        }
        
        # Check spike pattern
        if features.spike_count < self.min_spikes_for_confirm:
            self._consecutive_beta_high = 0
            return (DecisionIntent.NONE, 0.0, debug)
        
        if features.max_spike_zscore < self.spike_z_thresh:
            return (DecisionIntent.NONE, 0.0, debug)
        
        # Check interval
        elapsed = current_time_ms - self._last_confirm_time_ms
        if elapsed < self.min_interval_ms:
            debug['blocked'] = 'min_interval'
            debug['elapsed_ms'] = elapsed
            return (DecisionIntent.NONE, 0.0, debug)
        
        # Confirm!
        confidence = min(
            1.0,
            (features.max_spike_zscore / self.spike_z_thresh) * 0.5
            * features.quality
            * self.confidence_scale
        )
        
        self._last_confirm_time_ms = current_time_ms
        
        debug['confirmed'] = True
        debug['confidence'] = confidence
        
        logger.info(
            f"[DECODER] CONFIRM detected: "
            f"spikes={features.spike_count}, "
            f"z={features.max_spike_zscore:.1f}, "
            f"conf={confidence:.2f}"
        )
        
        return (DecisionIntent.CONFIRM, confidence, debug)
    
    def _decode_beta_sustain(
        self, features: EEGFeatures, current_time_ms: float
    ) -> tuple:
        """
        Detect sustained beta power increase (attention/focus proxy).
        
        Confirm if beta bandpower exceeds threshold for N consecutive windows.
        """
        debug = {
            'decoder': 'beta_sustain',
            'beta_power': features.bandpower_beta,
            'consecutive': self._consecutive_beta_high,
            'quality': features.quality,
        }
        
        if features.bandpower_beta > self.beta_threshold:
            self._consecutive_beta_high += 1
        else:
            self._consecutive_beta_high = 0
        
        if self._consecutive_beta_high >= self.sustain_windows:
            # Check interval
            elapsed = current_time_ms - self._last_confirm_time_ms
            if elapsed < self.min_interval_ms:
                debug['blocked'] = 'min_interval'
                return (DecisionIntent.NONE, 0.0, debug)
            
            confidence = min(1.0, features.quality * self.confidence_scale)
            self._last_confirm_time_ms = current_time_ms
            self._consecutive_beta_high = 0
            
            debug['confirmed'] = True
            debug['confidence'] = confidence
            
            return (DecisionIntent.CONFIRM, confidence, debug)
        
        return (DecisionIntent.NONE, 0.0, debug)

