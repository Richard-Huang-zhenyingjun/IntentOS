"""
Decision strategy - robust EEG decision filtering.
Week 7: Windowing, majority vote, two-hit confirm, cooldown.
Paper-aligned: "Noisy BCI requires decision strategy".
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
import time
from intent_core.arm_intent_schema import DecisionSignal
from .brainlink.brainlink_decoder import BrainLinkFeatures
from .signal_quality import SignalWindow, compute_stability


@dataclass
class DecisionFrame:
    """
    Single decision frame in rolling window.
    
    Attributes:
        timestamp: Frame timestamp
        raw_signal: Raw decision (before smoothing)
        stable: Whether signal was stable
    """
    timestamp: float
    raw_signal: DecisionSignal
    stable: bool


@dataclass
class DecisionMeta:
    """
    Decision metadata for transparency.
    
    Attributes:
        stable: Signal stability
        blocked: Whether decision was blocked
        reason: Block reason if applicable
        confidence: Decision confidence [0, 1]
        counts: Vote counts {CONFIRM: N, CANCEL: M, IDLE: K}
        variance: Metric variance
        samples: Sample count
        cooldown_remaining: Cooldown time remaining
    """
    stable: bool
    blocked: bool
    reason: str
    confidence: float
    counts: dict
    variance: float
    samples: int
    cooldown_remaining: float


class DecisionStrategy:
    """
    Robust decision strategy for noisy EEG signals.
    
    Pipeline:
    1. Convert features → raw signal (threshold + hysteresis)
    2. Check stability
    3. Apply rolling window majority vote
    4. Optional: Two-hit confirm
    5. Apply cooldown
    
    Week 7: Prevents false triggers from noisy BCI.
    """
    
    def __init__(self, cfg: dict):
        """
        Initialize decision strategy.
        
        Args:
            cfg: Configuration dict
        """
        self.cfg = cfg
        
        # Config shortcuts
        self.confirm_high = cfg['eeg']['thresholds']['confirm_high']
        self.confirm_low = cfg['eeg']['thresholds']['confirm_low']
        self.cancel_high = cfg['eeg']['thresholds']['cancel_high']
        self.cancel_low = cfg['eeg']['thresholds']['cancel_low']
        self.use_meditation_cancel = cfg['eeg']['mapping']['use_meditation_for_cancel']
        
        strategy_cfg = cfg['eeg']['strategy']
        self.window_seconds = strategy_cfg['window_seconds']
        self.min_samples = strategy_cfg['min_samples']
        self.majority_ratio = strategy_cfg['majority_ratio']
        self.two_hit_confirm = strategy_cfg['two_hit_confirm']
        self.two_hit_window = strategy_cfg['two_hit_window_seconds']
        self.cooldown_seconds = strategy_cfg['cooldown_seconds']
        
        # State
        self.decision_window: List[DecisionFrame] = []
        self.signal_window = SignalWindow(self.window_seconds)
        self.last_output_time: Optional[float] = None
        self.last_output_signal: Optional[DecisionSignal] = None
        self.current_raw_signal = DecisionSignal.IDLE
        
        # Two-hit tracking
        self.confirm_timestamps: List[float] = []
        self.cancel_timestamps: List[float] = []
    
    def update(self, features: BrainLinkFeatures, now: float) -> Tuple[DecisionSignal, DecisionMeta]:
        """
        Update strategy with new features and produce decision.
        
        Args:
            features: Decoded BrainLink features
            now: Current timestamp
            
        Returns:
            (DecisionSignal, DecisionMeta)
        """
        # Add to signal window
        self.signal_window.add_sample(now, features.attention)
        
        # Check stability
        quality_report = compute_stability(self.signal_window, self.cfg, now)
        
        # If unstable, block all decisions
        if not quality_report.stable:
            return DecisionSignal.IDLE, DecisionMeta(
                stable=False,
                blocked=True,
                reason=quality_report.reason,
                confidence=quality_report.confidence,
                counts={},
                variance=quality_report.metric_variance,
                samples=quality_report.sample_count,
                cooldown_remaining=0.0
            )
        
        # Compute raw signal (with hysteresis)
        raw_signal = self._compute_raw_signal(features)
        
        # Add to decision window
        frame = DecisionFrame(
            timestamp=now,
            raw_signal=raw_signal,
            stable=True
        )
        self.decision_window.append(frame)
        
        # Remove old frames
        cutoff = now - self.window_seconds
        self.decision_window = [f for f in self.decision_window if f.timestamp > cutoff]
        
        # Check cooldown
        cooldown_remaining = 0.0
        if self.last_output_time is not None:
            elapsed = now - self.last_output_time
            cooldown_remaining = max(0.0, self.cooldown_seconds - elapsed)
            
            if cooldown_remaining > 0:
                return DecisionSignal.IDLE, DecisionMeta(
                    stable=True,
                    blocked=True,
                    reason=f"Cooldown ({cooldown_remaining:.1f}s)",
                    confidence=quality_report.confidence,
                    counts=self._count_votes(),
                    variance=quality_report.metric_variance,
                    samples=quality_report.sample_count,
                    cooldown_remaining=cooldown_remaining
                )
        
        # Apply majority vote
        final_signal, counts = self._majority_vote()
        
        # Apply two-hit filter if needed
        if self.two_hit_confirm:
            final_signal = self._apply_two_hit(final_signal, now)
        
        # Output decision
        if final_signal != DecisionSignal.IDLE:
            self.last_output_time = now
            self.last_output_signal = final_signal
        
        return final_signal, DecisionMeta(
            stable=True,
            blocked=False,
            reason="",
            confidence=quality_report.confidence,
            counts=counts,
            variance=quality_report.metric_variance,
            samples=quality_report.sample_count,
            cooldown_remaining=0.0
        )
    
    def _compute_raw_signal(self, features: BrainLinkFeatures) -> DecisionSignal:
        """
        Compute raw signal from features with hysteresis.
        
        Args:
            features: BrainLink features
            
        Returns:
            DecisionSignal
        """
        if not features.is_valid or features.attention is None:
            return DecisionSignal.IDLE
        
        attention = features.attention
        meditation = features.meditation if features.meditation is not None else 0.0
        
        # State machine with hysteresis
        if self.current_raw_signal == DecisionSignal.CONFIRM:
            # Already confirming - need to drop below low threshold to reset
            if attention < self.confirm_low:
                self.current_raw_signal = DecisionSignal.IDLE
        elif self.current_raw_signal == DecisionSignal.CANCEL:
            # Already cancelling - need to drop below low threshold
            if self.use_meditation_cancel and meditation < self.cancel_low:
                self.current_raw_signal = DecisionSignal.IDLE
            elif not self.use_meditation_cancel and attention >= self.confirm_low:
                self.current_raw_signal = DecisionSignal.IDLE
        else:
            # Idle - check for trigger
            if attention >= self.confirm_high:
                self.current_raw_signal = DecisionSignal.CONFIRM
            elif self.use_meditation_cancel and meditation >= self.cancel_high:
                self.current_raw_signal = DecisionSignal.CANCEL
            elif not self.use_meditation_cancel and attention < self.cancel_low:
                # Low attention = cancel
                self.current_raw_signal = DecisionSignal.CANCEL
        
        return self.current_raw_signal
    
    def _count_votes(self) -> dict:
        """Count votes in decision window."""
        counts = {
            DecisionSignal.CONFIRM: 0,
            DecisionSignal.CANCEL: 0,
            DecisionSignal.IDLE: 0
        }
        
        for frame in self.decision_window:
            counts[frame.raw_signal] += 1
        
        return counts
    
    def _majority_vote(self) -> Tuple[DecisionSignal, dict]:
        """
        Apply majority vote to decision window.
        
        Returns:
            (winning_signal, vote_counts)
        """
        counts = self._count_votes()
        total = len(self.decision_window)
        
        if total == 0:
            return DecisionSignal.IDLE, counts
        
        # Check if any signal has majority
        for signal in [DecisionSignal.CONFIRM, DecisionSignal.CANCEL]:
            ratio = counts[signal] / total
            if ratio >= self.majority_ratio:
                return signal, counts
        
        return DecisionSignal.IDLE, counts
    
    def _apply_two_hit(self, signal: DecisionSignal, now: float) -> DecisionSignal:
        """
        Apply two-hit filter: require 2 distinct votes within time window.
        
        Args:
            signal: Current signal from majority vote
            now: Current timestamp
            
        Returns:
            Filtered signal
        """
        if signal == DecisionSignal.CONFIRM:
            # Add timestamp
            self.confirm_timestamps.append(now)
            
            # Remove old timestamps
            cutoff = now - self.two_hit_window
            self.confirm_timestamps = [t for t in self.confirm_timestamps if t > cutoff]
            
            # Check for two hits
            if len(self.confirm_timestamps) >= 2:
                # Clear after successful two-hit
                self.confirm_timestamps.clear()
                return DecisionSignal.CONFIRM
            else:
                # Need another hit
                return DecisionSignal.IDLE
        
        elif signal == DecisionSignal.CANCEL:
            # Same logic for cancel
            self.cancel_timestamps.append(now)
            cutoff = now - self.two_hit_window
            self.cancel_timestamps = [t for t in self.cancel_timestamps if t > cutoff]
            
            if len(self.cancel_timestamps) >= 2:
                self.cancel_timestamps.clear()
                return DecisionSignal.CANCEL
            else:
                return DecisionSignal.IDLE
        
        return signal
    
    def reset(self) -> None:
        """Reset strategy state."""
        self.decision_window.clear()
        self.signal_window = SignalWindow(self.window_seconds)
        self.confirm_timestamps.clear()
        self.cancel_timestamps.clear()
        self.last_output_time = None
        self.last_output_signal = None
        self.current_raw_signal = DecisionSignal.IDLE

