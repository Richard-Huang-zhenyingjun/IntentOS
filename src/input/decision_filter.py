"""Decision filtering for EEG signals (hysteresis, windowing, quality checks)."""

from collections import deque
import time
from src.core.schema import DecisionSignal


class DecisionFilter:
    """Filter noisy EEG signals before accepting as decision."""
    
    def __init__(self, config: dict):
        self.window_seconds = config.get('eeg_window_seconds', 1.5)
        self.cooldown_seconds = config.get('eeg_cooldown_seconds', 1.5)
        self.confirm_threshold = config.get('eeg_confirm_threshold', 70.0)
        
        self.decision_window = deque(maxlen=50)
        self.last_output_time = None
        self.current_signal = DecisionSignal.IDLE
    
    def process(self, sample, timestamp: float):
        """Process EEG sample and return filtered decision.
        
        Args:
            sample: BrainLinkSample with attention/meditation
            timestamp: Current time
            
        Returns:
            (signal, metadata) tuple
        """
        # Add to window
        self.decision_window.append((timestamp, sample))
        
        # Remove old samples
        cutoff = timestamp - self.window_seconds
        while self.decision_window and self.decision_window[0][0] < cutoff:
            self.decision_window.popleft()
        
        # Check cooldown
        if self.last_output_time and (timestamp - self.last_output_time) < self.cooldown_seconds:
            # In cooldown - return IDLE
            return DecisionSignal.IDLE, {'confidence': 0.0, 'blocked': True, 'reason': 'cooldown'}
        
        # Majority vote from window
        if len(self.decision_window) >= 5:  # Minimum samples
            high_attention = sum(1 for _, s in self.decision_window if s.attention > self.confirm_threshold)
            ratio = high_attention / len(self.decision_window)
            
            if ratio > 0.6:  # 60% majority
                # Trigger CONFIRM
                self.last_output_time = timestamp
                self.current_signal = DecisionSignal.CONFIRM
                return DecisionSignal.CONFIRM, {'confidence': ratio, 'blocked': False, 'reason': 'confirm'}
        
        # Default IDLE
        return DecisionSignal.IDLE, {'confidence': 0.0, 'blocked': False, 'reason': 'idle'}
    
    def reset(self):
        """Reset filter state."""
        self.decision_window.clear()
        self.last_output_time = None
        self.current_signal = DecisionSignal.IDLE

