"""
BrainLink decision source - complete EEG pipeline.
Week 7: Client → Decoder → Strategy → DecisionSignal.
"""

import time
from typing import Optional, TYPE_CHECKING
from input.eeg_interface import EEGDecisionSource
from intent_core.arm_intent_schema import DecisionSignal
from .brainlink_client import BrainLinkClient
from .brainlink_decoder import decode_sample, BrainLinkFeatures

if TYPE_CHECKING:
    from src.input.decision_strategy import DecisionStrategy, DecisionMeta


class BrainLinkDecisionSource(EEGDecisionSource):
    """
    BrainLink Lite decision source.
    
    Complete pipeline:
    1. BrainLinkClient → raw samples
    2. Decoder → validated features
    3. DecisionStrategy → robust decision signal
    
    Week 7: Implements paper's "noisy BCI + decision strategy" approach.
    """
    
    def __init__(self, cfg: dict):
        """
        Initialize BrainLink decision source.
        
        Args:
            cfg: Configuration dict
        """
        # Import here to avoid circular import
        from src.input.decision_strategy import DecisionStrategy, DecisionMeta
        
        self.cfg = cfg
        self.client = BrainLinkClient(cfg)
        self.strategy = DecisionStrategy(cfg)
        
        # State
        self.last_features: Optional[BrainLinkFeatures] = None
        self.last_meta: Optional[DecisionMeta] = None
        self.last_signal = DecisionSignal.IDLE
        
        self._started = False
    
    def start(self) -> bool:
        """
        Start BrainLink connection.
        
        Returns:
            True if started successfully
        """
        success = self.client.start()
        
        if success:
            self._started = True
            print("✓ BrainLink decision source started")
        else:
            print("⚠️  BrainLink decision source failed to start")
        
        return success
    
    def read_signal(self) -> DecisionSignal:
        """
        Read current decision signal.
        
        Returns:
            DecisionSignal (CONFIRM / CANCEL / IDLE)
        """
        if not self._started:
            return DecisionSignal.IDLE
        
        # Read sample
        sample = self.client.read_sample()
        
        if sample is None:
            # No new sample - use strategy with None features
            features = BrainLinkFeatures(
                timestamp=time.time(),
                is_valid=False
            )
        else:
            # Decode sample
            features = decode_sample(sample, self.cfg)
        
        self.last_features = features
        
        # Apply decision strategy
        signal, meta = self.strategy.update(features, time.time())
        
        self.last_meta = meta
        self.last_signal = signal
        
        return signal
    
    def close(self) -> None:
        """Close BrainLink connection."""
        if self._started:
            self.client.close()
            self._started = False
    
    def get_source_name(self) -> str:
        """Get source name."""
        port = self.client.port_name if self.client.port_name else "disconnected"
        return f"BrainLink ({port})"
    
    def get_confidence(self) -> float:
        """Get decision confidence."""
        if self.last_meta is None:
            return 0.0
        return self.last_meta.confidence
    
    def get_debug_status(self) -> dict:
        """
        Get detailed debug status.
        
        Returns:
            Dict with EEG metrics, stability, blocking status
        """
        if self.last_features is None or self.last_meta is None:
            return {
                "connected": self._started,
                "features": None,
                "stable": False,
                "blocked": True,
                "reason": "No data",
                "confidence": 0.0,
                "counts": {},
                "variance": 0.0,
                "samples": 0,
                "cooldown": 0.0,
                "last_signal": "IDLE",
            }
        
        return {
            "connected": self._started,
            "port": self.client.port_name,
            "features": {
                "attention": self.last_features.attention,
                "meditation": self.last_features.meditation,
                "signal_quality": self.last_features.signal_quality,
                "valid": self.last_features.is_valid,
            },
            "stable": self.last_meta.stable,
            "blocked": self.last_meta.blocked,
            "reason": self.last_meta.reason,
            "confidence": self.last_meta.confidence,
            "counts": self.last_meta.counts,
            "variance": self.last_meta.variance,
            "samples": self.last_meta.samples,
            "cooldown": self.last_meta.cooldown_remaining,
            "last_signal": str(self.last_signal),
        }

