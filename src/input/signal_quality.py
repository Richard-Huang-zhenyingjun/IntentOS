"""
Signal quality monitor - detect unstable/dropped EEG signals.
Week 7: Paper-aligned "noisy BCI" handling.
"""

from dataclasses import dataclass
from typing import List, Optional
import time
import numpy as np


@dataclass
class SignalQualityReport:
    """
    Signal quality assessment.
    
    Attributes:
        stable: Whether signal is stable enough to trust
        reason: Explanation if unstable
        missing_seconds: Time since last valid sample
        metric_variance: Variance of primary metric in window
        sample_count: Number of samples in window
        confidence: Quality confidence [0, 1]
    """
    stable: bool
    reason: str
    missing_seconds: float
    metric_variance: float
    sample_count: int
    confidence: float
    
    def __repr__(self) -> str:
        """Human-readable summary."""
        status = "STABLE" if self.stable else f"UNSTABLE ({self.reason})"
        return f"SignalQuality({status}, conf={self.confidence:.2f}, samples={self.sample_count})"


class SignalWindow:
    """
    Rolling window of signal samples.
    
    Maintains time-windowed history for stability analysis.
    """
    
    def __init__(self, window_seconds: float):
        """
        Initialize signal window.
        
        Args:
            window_seconds: Window duration
        """
        self.window_seconds = window_seconds
        self.samples: List[tuple[float, Optional[float]]] = []  # (timestamp, value)
        self.last_valid_time: Optional[float] = None
    
    def add_sample(self, timestamp: float, value: Optional[float]) -> None:
        """Add sample to window."""
        self.samples.append((timestamp, value))
        
        if value is not None:
            self.last_valid_time = timestamp
        
        # Remove old samples
        cutoff = timestamp - self.window_seconds
        self.samples = [(t, v) for t, v in self.samples if t > cutoff]
    
    def get_valid_values(self) -> List[float]:
        """Get all valid (non-None) values in window."""
        return [v for _, v in self.samples if v is not None]
    
    def get_sample_count(self) -> int:
        """Get number of samples in window."""
        return len(self.samples)
    
    def get_missing_seconds(self, now: float) -> float:
        """Get time since last valid sample."""
        if self.last_valid_time is None:
            return float('inf')
        return now - self.last_valid_time


def compute_stability(window: SignalWindow, cfg: dict, now: float) -> SignalQualityReport:
    """
    Assess signal stability.
    
    Args:
        window: Signal window
        cfg: Configuration dict
        now: Current timestamp
        
    Returns:
        SignalQualityReport with assessment
    """
    quality_cfg = cfg['eeg']['quality']
    strategy_cfg = cfg['eeg']['strategy']
    
    # Get valid samples
    valid_values = window.get_valid_values()
    sample_count = len(valid_values)
    missing_seconds = window.get_missing_seconds(now)
    
    # Check 1: Missing samples
    max_missing = quality_cfg['max_missing_seconds']
    if missing_seconds > max_missing:
        return SignalQualityReport(
            stable=False,
            reason=f"No signal for {missing_seconds:.1f}s (max {max_missing:.1f}s)",
            missing_seconds=missing_seconds,
            metric_variance=0.0,
            sample_count=sample_count,
            confidence=0.0
        )
    
    # Check 2: Insufficient samples
    min_samples = strategy_cfg['min_samples']
    if sample_count < min_samples:
        return SignalQualityReport(
            stable=False,
            reason=f"Too few samples ({sample_count}/{min_samples})",
            missing_seconds=missing_seconds,
            metric_variance=0.0,
            sample_count=sample_count,
            confidence=0.3
        )
    
    # Check 3: High variance (erratic signal)
    metric_variance = np.var(valid_values) if len(valid_values) > 1 else 0.0
    
    if quality_cfg['enable_variance_check']:
        max_variance = quality_cfg['max_variance']
        if metric_variance > max_variance:
            return SignalQualityReport(
                stable=False,
                reason=f"High variance ({metric_variance:.0f} > {max_variance:.0f})",
                missing_seconds=missing_seconds,
                metric_variance=metric_variance,
                sample_count=sample_count,
                confidence=0.5
            )
    
    # Stable
    # Confidence based on sample count and freshness
    conf_samples = min(1.0, sample_count / (min_samples * 2))
    conf_freshness = 1.0 - min(1.0, missing_seconds / max_missing)
    confidence = (conf_samples + conf_freshness) / 2
    
    return SignalQualityReport(
        stable=True,
        reason="Signal stable",
        missing_seconds=missing_seconds,
        metric_variance=metric_variance,
        sample_count=sample_count,
        confidence=confidence
    )




