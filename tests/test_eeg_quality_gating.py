"""
Test that low-quality EEG confirms are blocked by the decision filter.
"""
import pytest
from src.input.filter import DecisionFilter
from src.input.types import DecisionIntent, SourceType, FilterAction


def test_low_quality_eeg_blocked():
    """EEG confirm with low quality must be blocked"""
    config = {'input': {'debounce_frames': 0, 'confirm_hold_frames': 1, 'min_quality': 0.65}}
    f = DecisionFilter(config)
    
    result = f.filter(
        DecisionIntent.CONFIRM, SourceType.EEG, quality=0.3, frame_number=1
    )
    
    assert result.intent == DecisionIntent.NONE
    assert result.filter_action == FilterAction.BLOCKED_QUALITY


def test_high_quality_eeg_passes():
    """EEG confirm with high quality must pass"""
    config = {'input': {'debounce_frames': 0, 'confirm_hold_frames': 1, 'min_quality': 0.65}}
    f = DecisionFilter(config)
    
    result = f.filter(
        DecisionIntent.CONFIRM, SourceType.EEG, quality=0.85, frame_number=1
    )
    
    assert result.intent == DecisionIntent.CONFIRM
    assert result.filter_action == FilterAction.PASSED


def test_eeg_cancel_bypasses_quality():
    """EEG cancel must pass even with zero quality"""
    config = {'input': {'debounce_frames': 0, 'confirm_hold_frames': 1, 'min_quality': 0.99}}
    f = DecisionFilter(config)
    
    result = f.filter(
        DecisionIntent.CANCEL, SourceType.EEG, quality=0.0, frame_number=1
    )
    
    assert result.intent == DecisionIntent.CANCEL
    assert result.filter_action == FilterAction.PASSED



