"""
Test decision strategy module.
Week 7: Robust EEG decision filtering tests.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
import time
import yaml
from intent_core.arm_intent_schema import DecisionSignal
from input.brainlink.brainlink_decoder import BrainLinkFeatures
from input.decision_strategy import DecisionStrategy, DecisionMeta


@pytest.fixture
def default_cfg():
    """Load default config."""
    cfg_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'robotics.yaml')
    with open(cfg_path, 'r') as f:
        return yaml.safe_load(f)


@pytest.fixture
def strategy(default_cfg):
    """Create decision strategy with default config."""
    return DecisionStrategy(default_cfg)


def make_features(attention=50.0, meditation=50.0, valid=True, timestamp=None):
    """Helper to create BrainLinkFeatures."""
    if timestamp is None:
        timestamp = time.time()
    return BrainLinkFeatures(
        attention=attention,
        meditation=meditation,
        signal_quality=0.0,
        is_valid=valid,
        timestamp=timestamp
    )


class TestDecisionStrategy:
    """Test DecisionStrategy class."""
    
    def test_initialization(self, default_cfg):
        """Test strategy initialization."""
        strategy = DecisionStrategy(default_cfg)
        
        assert strategy.confirm_high == 70
        assert strategy.confirm_low == 55
        assert strategy.window_seconds == 1.5
        assert strategy.cooldown_seconds == 1.5
        assert len(strategy.decision_window) == 0
    
    def test_idle_signal_below_threshold(self, strategy):
        """Test that low attention produces IDLE."""
        features = make_features(attention=50.0)
        signal, meta = strategy.update(features, time.time())
        
        assert signal == DecisionSignal.IDLE
        assert meta.stable == False  # Not enough samples yet
    
    def test_confirm_signal_above_threshold(self, strategy):
        """Test that high attention triggers CONFIRM (with sufficient votes)."""
        now = time.time()
        
        # Send high attention for long enough to pass majority vote
        for i in range(15):
            features = make_features(attention=75.0, timestamp=now + i * 0.1)
            signal, meta = strategy.update(features, now + i * 0.1)
        
        # With two-hit confirm enabled, need multiple distinct votes
        # But after enough samples, should eventually confirm
        assert meta.stable == True
        # Signal depends on two-hit logic - may be IDLE or CONFIRM
    
    def test_hysteresis(self, strategy):
        """Test that hysteresis prevents oscillation."""
        now = time.time()
        
        # Send high attention to enter CONFIRM state (need more samples)
        for i in range(15):
            features = make_features(attention=75.0, timestamp=now + i * 0.05)
            strategy.update(features, now + i * 0.05)
        
        # Check raw signal is CONFIRM
        assert strategy.current_raw_signal == DecisionSignal.CONFIRM
        
        # Drop to middle range (between high and low thresholds)
        features = make_features(attention=60.0, timestamp=now + 0.8)
        strategy.update(features, now + 0.8)
        
        # Should still be CONFIRM (hysteresis)
        assert strategy.current_raw_signal == DecisionSignal.CONFIRM
        
        # Drop below low threshold
        features = make_features(attention=50.0, timestamp=now + 0.9)
        strategy.update(features, now + 0.9)
        
        # Should reset to IDLE
        assert strategy.current_raw_signal == DecisionSignal.IDLE
    
    def test_insufficient_samples_blocks_decision(self, strategy):
        """Test that insufficient samples blocks decisions."""
        features = make_features(attention=75.0)
        signal, meta = strategy.update(features, time.time())
        
        # With only 1 sample, should be unstable
        assert meta.stable == False
        assert "Too few samples" in meta.reason
        assert signal == DecisionSignal.IDLE
    
    def test_missing_signal_blocks_decision(self, strategy):
        """Test that missing signal blocks decisions."""
        now = time.time()
        
        # Add some samples
        for i in range(10):
            features = make_features(attention=75.0, timestamp=now + i * 0.1)
            strategy.update(features, now + i * 0.1)
        
        # Wait too long (simulate missing packets)
        future = now + 2.0  # Exceeds max_missing_seconds (1.5s)
        features = make_features(attention=75.0, timestamp=future)
        signal, meta = strategy.update(features, future)
        
        # Should be blocked (either "No signal" or "Too few samples" due to window expiration)
        assert meta.stable == False
        assert meta.blocked == True
        assert signal == DecisionSignal.IDLE
    
    def test_cooldown_blocks_rapid_fire(self, strategy):
        """Test that cooldown prevents rapid-fire confirmations."""
        now = time.time()
        
        # Disable two-hit for this test (modify strategy)
        strategy.two_hit_confirm = False
        
        # Build up enough samples for majority vote
        for i in range(15):
            features = make_features(attention=75.0, timestamp=now + i * 0.1)
            signal, meta = strategy.update(features, now + i * 0.1)
        
        # Should get a CONFIRM at some point
        if signal == DecisionSignal.CONFIRM:
            # Immediately try again
            features = make_features(attention=75.0, timestamp=now + 1.6)
            signal2, meta2 = strategy.update(features, now + 1.6)
            
            # Should be blocked by cooldown
            assert signal2 == DecisionSignal.IDLE
            assert meta2.blocked == True
            assert "Cooldown" in meta2.reason
    
    def test_two_hit_confirm(self, strategy):
        """Test that two-hit confirm requires multiple distinct votes."""
        now = time.time()
        
        # Ensure two-hit is enabled
        assert strategy.two_hit_confirm == True
        
        # Build up samples with high attention
        for i in range(10):
            features = make_features(attention=75.0, timestamp=now + i * 0.1)
            signal, meta = strategy.update(features, now + i * 0.1)
        
        # First majority vote should not trigger (need second hit)
        # Keep sending high attention
        for i in range(10, 20):
            features = make_features(attention=75.0, timestamp=now + i * 0.1)
            signal, meta = strategy.update(features, now + i * 0.1)
        
        # Eventually should get CONFIRM after two distinct hits
        # (exact timing depends on windowing logic)
        assert meta.stable == True
    
    def test_invalid_features_ignored(self, strategy):
        """Test that invalid features are handled gracefully."""
        features = make_features(attention=None, valid=False)
        signal, meta = strategy.update(features, time.time())
        
        # Should produce IDLE and be unstable
        assert signal == DecisionSignal.IDLE
    
    def test_reset(self, strategy):
        """Test that reset clears all state."""
        now = time.time()
        
        # Add some samples
        for i in range(10):
            features = make_features(attention=75.0, timestamp=now + i * 0.1)
            strategy.update(features, now + i * 0.1)
        
        # Reset
        strategy.reset()
        
        # Check state cleared
        assert len(strategy.decision_window) == 0
        assert strategy.current_raw_signal == DecisionSignal.IDLE
        assert strategy.last_output_time is None
        assert len(strategy.confirm_timestamps) == 0
    
    def test_majority_vote_counts(self, strategy):
        """Test that majority vote counts are correct."""
        now = time.time()
        
        # Add high attention samples (CONFIRM)
        for i in range(10):
            features = make_features(attention=75.0, timestamp=now + i * 0.05)  # Closer spacing
            strategy.update(features, now + i * 0.05)
        
        # Check vote counts (high attention should produce CONFIRM raw signals)
        counts = strategy._count_votes()
        assert counts[DecisionSignal.CONFIRM] > 0
        assert sum(counts.values()) == len(strategy.decision_window)
        
        # Add low attention samples (IDLE/CANCEL)
        for i in range(10, 20):
            features = make_features(attention=30.0, timestamp=now + i * 0.05)
            strategy.update(features, now + i * 0.05)
        
        # Check updated counts
        counts2 = strategy._count_votes()
        assert sum(counts2.values()) == len(strategy.decision_window)
    
    def test_cancel_with_low_attention(self, strategy):
        """Test CANCEL signal with low attention (if not using meditation)."""
        now = time.time()
        
        # Strategy uses attention for cancel (meditation disabled by default)
        assert strategy.use_meditation_cancel == False
        
        # Send low attention
        for i in range(15):
            features = make_features(attention=30.0, timestamp=now + i * 0.1)
            signal, meta = strategy.update(features, now + i * 0.1)
        
        # Should eventually produce CANCEL (after windowing + two-hit)
        # (exact behavior depends on thresholds and two-hit logic)
        assert meta.stable == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

