"""EEG input source - BrainLink integration (preserved for future use)."""

import time
from typing import Optional
from src.core.schema import ArmDecision, DecisionSignal
from src.input.decision_source import DecisionSource
from src.input.decision_filter import DecisionFilter


class EEGSource(DecisionSource):
    """BrainLink EEG → ArmDecision (with quality filtering)."""
    
    def __init__(self, config: dict, mock_mode: bool = True):
        self.config = config
        self.mock_mode = mock_mode
        self.filter = DecisionFilter(config)
        
        # BrainLink client (real or mock)
        if not mock_mode:
            try:
                from src.input.brainlink_client import BrainLinkClient
                self.client = BrainLinkClient(config)
                self.client.start()
                print("[EEG] ✓ BrainLink hardware connected")
            except Exception as e:
                print(f"[EEG] ⚠️ Hardware unavailable, using mock: {e}")
                self.mock_mode = True
                self.client = None
        else:
            self.client = None
            print("[EEG] Mock mode enabled")
    
    def read_decision(self) -> ArmDecision:
        """Read EEG signal and produce filtered decision."""
        now = time.time()
        
        if self.mock_mode:
            # Mock: always return IDLE (keyboard is active controller)
            return ArmDecision(
                signal=DecisionSignal.IDLE,
                confidence=0.0,
                source="eeg_mock",
                timestamp=now
            )
        
        # Real EEG path (preserved for future)
        try:
            # Read BrainLink sample
            sample = self.client.read_sample()
            if sample is None:
                return ArmDecision(
                    signal=DecisionSignal.IDLE,
                    confidence=0.0,
                    source="eeg",
                    timestamp=now
                )
            
            # Apply decision filter (hysteresis, windowing, etc.)
            signal, meta = self.filter.process(sample, now)
            
            return ArmDecision(
                signal=signal,
                confidence=meta.confidence,
                source="eeg",
                timestamp=now
            )
        except Exception as e:
            print(f"[EEG] Error reading signal: {e}")
            return ArmDecision(
                signal=DecisionSignal.IDLE,
                confidence=0.0,
                source="eeg",
                timestamp=now
            )
    
    def get_source_name(self) -> str:
        if self.mock_mode:
            return "EEG (Mock - keyboard active)"
        return "EEG (BrainLink)"
    
    def reset(self):
        """Reset filter state."""
        self.filter.reset()
    
    def close(self):
        """Close BrainLink connection."""
        if self.client:
            self.client.close()

