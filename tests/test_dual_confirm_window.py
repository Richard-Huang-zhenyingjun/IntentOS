"""
Tests for DUAL confirmation mode.
Both sources must confirm within time window.
"""
import pytest
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.input.router import DecisionRouter
from src.input.source_fake import FakeSource
from src.input.source_eeg_mock import MockEEGSource
from src.input.types import DecisionIntent
from src.input.policies import DecisionPolicy, RoutingMode


def _make_dual_policy(window_ms: float = 900) -> DecisionPolicy:
    return DecisionPolicy(
        mode=RoutingMode.DUAL,
        min_quality=0.0,
        debounce_frames=0,
        confirm_hold_frames=1,
        dual_window_ms=window_ms,
        dual_sources=['keyboard', 'eeg'],
        allowed_sources=['keyboard', 'eeg'],
    )


def test_dual_both_confirm_within_window():
    """Both sources confirming within window → CONFIRM"""
    router = DecisionRouter(_make_dual_policy(window_ms=2000))
    
    kb = FakeSource()
    kb.set_confirm_on_frame(1)
    router.register_source('keyboard', kb)
    
    mock_eeg = MockEEGSource({'eeg_mock': {'enabled': True, 'confirm_probability': 0.0, 'quality_mean': 0.9, 'quality_std': 0.0, 'artifact_probability': 0.0}})
    mock_eeg.inject_confirm(quality=0.9)
    router.register_source('eeg', mock_eeg)
    
    intent, _, _, _ = router.read_all()
    assert intent == DecisionIntent.CONFIRM


def test_dual_only_keyboard_no_confirm():
    """Only keyboard confirms → no CONFIRM in DUAL mode"""
    router = DecisionRouter(_make_dual_policy())
    
    kb = FakeSource()
    kb.set_confirm_on_frame(1)
    router.register_source('keyboard', kb)
    
    mock_eeg = MockEEGSource({'eeg_mock': {'enabled': True, 'confirm_probability': 0.0, 'quality_mean': 0.5, 'quality_std': 0.0, 'artifact_probability': 0.0}})
    router.register_source('eeg', mock_eeg)
    
    intent, _, _, _ = router.read_all()
    assert intent == DecisionIntent.NONE  # EEG didn't confirm


def test_dual_outside_window_no_confirm():
    """Both confirm but outside window → no CONFIRM"""
    router = DecisionRouter(_make_dual_policy(window_ms=100))  # 100ms window
    
    kb = FakeSource()
    kb.set_confirm_on_frame(1)
    router.register_source('keyboard', kb)
    
    mock_eeg = MockEEGSource({'eeg_mock': {'enabled': True, 'confirm_probability': 0.0, 'quality_mean': 0.9, 'quality_std': 0.0, 'artifact_probability': 0.0}})
    router.register_source('eeg', mock_eeg)
    
    # Keyboard confirms first
    router.read_all()
    
    # Wait past window
    time.sleep(0.2)
    
    # EEG confirms too late
    mock_eeg.inject_confirm(quality=0.9)
    intent, _, _, _ = router.read_all()
    assert intent == DecisionIntent.NONE


if __name__ == '__main__':
    pytest.main([__file__, '-v'])



