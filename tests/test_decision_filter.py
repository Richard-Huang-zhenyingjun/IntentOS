"""
Tests for decision filter — debounce, quality gate, hold-to-confirm.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.input.filter import DecisionFilter
from src.input.types import DecisionIntent, SourceType, FilterAction


@pytest.fixture
def config():
    return {
        'input': {
            'debounce_frames': 6,
            'confirm_hold_frames': 1,
            'min_quality': 0.65,
        }
    }


class TestQualityGate:
    
    def test_high_quality_confirm_passes(self, config):
        f = DecisionFilter(config)
        result = f.filter(DecisionIntent.CONFIRM, SourceType.KEYBOARD, 1.0, frame_number=1)
        assert result.is_confirm
        assert result.filter_action == FilterAction.PASSED
    
    def test_low_quality_confirm_blocked(self, config):
        f = DecisionFilter(config)
        result = f.filter(DecisionIntent.CONFIRM, SourceType.MOCK_EEG, 0.3, frame_number=1)
        assert not result.is_confirm
        assert result.filter_action == FilterAction.BLOCKED_QUALITY
    
    def test_borderline_quality_blocked(self, config):
        f = DecisionFilter(config)
        result = f.filter(DecisionIntent.CONFIRM, SourceType.EEG, 0.64, frame_number=1)
        assert not result.is_confirm
    
    def test_exact_threshold_passes(self, config):
        f = DecisionFilter(config)
        result = f.filter(DecisionIntent.CONFIRM, SourceType.EEG, 0.65, frame_number=1)
        assert result.is_confirm
    
    def test_cancel_bypasses_quality_gate(self, config):
        f = DecisionFilter(config)
        result = f.filter(DecisionIntent.CANCEL, SourceType.EEG, 0.1, frame_number=1)
        assert result.is_cancel  # CANCEL always passes regardless of quality


class TestDebounce:
    
    def test_second_confirm_blocked_within_debounce(self, config):
        f = DecisionFilter(config)
        
        # First confirm passes
        r1 = f.filter(DecisionIntent.CONFIRM, SourceType.KEYBOARD, 1.0, frame_number=1)
        assert r1.is_confirm
        
        # Second confirm within debounce window (6 frames) blocked
        r2 = f.filter(DecisionIntent.CONFIRM, SourceType.KEYBOARD, 1.0, frame_number=3)
        assert not r2.is_confirm
        assert r2.filter_action == FilterAction.BLOCKED_DEBOUNCE
    
    def test_confirm_after_debounce_passes(self, config):
        f = DecisionFilter(config)
        
        r1 = f.filter(DecisionIntent.CONFIRM, SourceType.KEYBOARD, 1.0, frame_number=1)
        assert r1.is_confirm
        
        # Advance past debounce window
        for i in range(2, 8):
            f.filter(DecisionIntent.NONE, SourceType.KEYBOARD, 1.0, frame_number=i)
        
        r2 = f.filter(DecisionIntent.CONFIRM, SourceType.KEYBOARD, 1.0, frame_number=8)
        assert r2.is_confirm


class TestHoldToConfirm:
    
    def test_hold_required(self):
        config = {'input': {'debounce_frames': 0, 'confirm_hold_frames': 3, 'min_quality': 0.0}}
        f = DecisionFilter(config)
        
        # Frame 1: first confirm frame (1/3)
        r1 = f.filter(DecisionIntent.CONFIRM, SourceType.KEYBOARD, 1.0, frame_number=1)
        assert not r1.is_confirm  # Need 3 consecutive
        
        # Frame 2: second (2/3)
        r2 = f.filter(DecisionIntent.CONFIRM, SourceType.KEYBOARD, 1.0, frame_number=2)
        assert not r2.is_confirm
        
        # Frame 3: third (3/3) — passes
        r3 = f.filter(DecisionIntent.CONFIRM, SourceType.KEYBOARD, 1.0, frame_number=3)
        assert r3.is_confirm
    
    def test_hold_resets_on_interruption(self):
        config = {'input': {'debounce_frames': 0, 'confirm_hold_frames': 3, 'min_quality': 0.0}}
        f = DecisionFilter(config)
        
        f.filter(DecisionIntent.CONFIRM, SourceType.KEYBOARD, 1.0, frame_number=1)
        f.filter(DecisionIntent.CONFIRM, SourceType.KEYBOARD, 1.0, frame_number=2)
        
        # Interruption
        f.filter(DecisionIntent.NONE, SourceType.KEYBOARD, 1.0, frame_number=3)
        
        # Restart hold
        r = f.filter(DecisionIntent.CONFIRM, SourceType.KEYBOARD, 1.0, frame_number=4)
        assert not r.is_confirm  # Reset to 1/3


class TestNonePassthrough:
    
    def test_none_always_passes_as_none(self, config):
        f = DecisionFilter(config)
        for i in range(100):
            result = f.filter(DecisionIntent.NONE, SourceType.KEYBOARD, 1.0, frame_number=i)
            assert result.intent == DecisionIntent.NONE


if __name__ == '__main__':
    pytest.main([__file__, '-v'])



