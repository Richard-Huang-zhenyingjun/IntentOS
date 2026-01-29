"""
BrainLink decoder - convert raw samples to validated features.
Week 7: Feature extraction and validation.
"""

from dataclasses import dataclass
from typing import Optional
from .brainlink_client import BrainLinkSample


@dataclass
class BrainLinkFeatures:
    """
    Decoded features from BrainLink sample.
    
    Attributes:
        attention: Attention metric (0-100), normalized
        meditation: Meditation metric (0-100), normalized
        signal_quality: Quality score (0=good, 200=bad)
        is_valid: Whether sample has required metrics
        timestamp: Sample timestamp
    """
    attention: Optional[float] = None
    meditation: Optional[float] = None
    signal_quality: Optional[float] = None
    is_valid: bool = False
    timestamp: float = 0.0
    
    def __repr__(self) -> str:
        """Human-readable summary."""
        if not self.is_valid:
            return "BrainLinkFeatures(INVALID)"
        return f"BrainLinkFeatures(att={self.attention:.0f}, med={self.meditation:.0f}, qual={self.signal_quality:.0f})"


def decode_sample(sample: BrainLinkSample, cfg: dict) -> BrainLinkFeatures:
    """
    Decode raw sample into validated features.
    
    Args:
        sample: Raw BrainLink sample
        cfg: Configuration dict
        
    Returns:
        BrainLinkFeatures with validation
    """
    features = BrainLinkFeatures(timestamp=sample.timestamp)
    
    # Extract attention
    if sample.attention is not None:
        # Validate range (0-100)
        if 0 <= sample.attention <= 100:
            features.attention = float(sample.attention)
        else:
            print(f"⚠️  Invalid attention value: {sample.attention}")
    
    # Extract meditation
    if sample.meditation is not None:
        if 0 <= sample.meditation <= 100:
            features.meditation = float(sample.meditation)
        else:
            print(f"⚠️  Invalid meditation value: {sample.meditation}")
    
    # Extract signal quality
    if sample.signal_quality is not None:
        features.signal_quality = float(sample.signal_quality)
    
    # Check validity
    min_quality = cfg['eeg']['quality'].get('min_signal_quality', 200)
    
    # Valid if:
    # 1. Has attention metric
    # 2. Signal quality acceptable (if available)
    if features.attention is not None:
        if features.signal_quality is None or features.signal_quality <= min_quality:
            features.is_valid = True
    
    return features




