"""
Tests for decision router — mode selection and source routing.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.input.router import DecisionRouter
from src.input.source_fake import FakeSource
from src.input.source_eeg_mock import MockEEGSource
from src.input.types import DecisionIntent, SourceType
from src.input.policies import DecisionPolicy, RoutingMode


def _make_policy(mode: str, **overrides) -> DecisionPolicy:
    base = {
        'mode': RoutingMode(mode),
        'min_quality': 0.65,
        'debounce_frames': 6,
        'confirm_hold_frames': 1,
        'dual_window_ms': 900,
        'dual_sources': ['keyboard', 'eeg'],
        'allowed_sources': ['keyboard', 'eeg'],
    }
    base.update(overrides)
    return DecisionPolicy(**base)


class TestKeyboardOnly:
    
    def test_keyboard_confirm_routed(self):
        router = DecisionRouter(_make_policy("KEYBOARD_ONLY"))
        kb = FakeSource()
        kb.set_confirm_on_frame(1)
        router.register_source('keyboard', kb)
        
        intent, src, quality, _ = router.read_all()
        assert intent == DecisionIntent.CONFIRM
        assert src == SourceType.TEST
    
    def test_eeg_ignored_in_keyboard_only(self):
        policy = _make_policy("KEYBOARD_ONLY", allowed_sources=['keyboard'])
        router = DecisionRouter(policy)
        
        kb = FakeSource()
        router.register_source('keyboard', kb)
        
        mock_eeg = MockEEGSource({'eeg_mock': {'enabled': True, 'confirm_probability': 1.0, 'quality_mean': 0.9, 'quality_std': 0.0, 'artifact_probability': 0.0}})
        router.register_source('eeg', mock_eeg)
        
        intent, _, _, _ = router.read_all()
        assert intent == DecisionIntent.NONE  # EEG not in allowed_sources


class TestAnyMode:
    
    def test_keyboard_confirm_in_any_mode(self):
        router = DecisionRouter(_make_policy("ANY"))
        kb = FakeSource()
        kb.set_confirm_on_frame(1)
        router.register_source('keyboard', kb)
        
        intent, _, _, _ = router.read_all()
        assert intent == DecisionIntent.CONFIRM
    
    def test_eeg_confirm_in_any_mode(self):
        router = DecisionRouter(_make_policy("ANY"))
        
        kb = FakeSource()
        router.register_source('keyboard', kb)
        
        mock_eeg = MockEEGSource({'eeg_mock': {'enabled': True, 'confirm_probability': 0.0, 'quality_mean': 0.9, 'quality_std': 0.0, 'artifact_probability': 0.0}})
        mock_eeg.inject_confirm(quality=0.85)
        router.register_source('eeg', mock_eeg)
        
        intent, src, quality, _ = router.read_all()
        assert intent == DecisionIntent.CONFIRM
        assert quality == 0.85


class TestCancelPriority:
    
    def test_cancel_overrides_confirm(self):
        router = DecisionRouter(_make_policy("ANY"))
        
        # Keyboard confirms
        kb = FakeSource()
        kb.set_confirm_on_frame(1)
        router.register_source('keyboard', kb)
        
        # EEG cancels
        mock_eeg = MockEEGSource({'eeg_mock': {'enabled': True, 'confirm_probability': 0.0, 'quality_mean': 0.9, 'quality_std': 0.0, 'artifact_probability': 0.0}})
        mock_eeg.inject_cancel(quality=0.8)
        router.register_source('eeg', mock_eeg)
        
        intent, _, _, _ = router.read_all()
        assert intent == DecisionIntent.CANCEL  # Cancel wins


class TestNoFalseConfirm:
    
    def test_no_sources_no_confirm(self):
        router = DecisionRouter(_make_policy("ANY"))
        intent, _, _, _ = router.read_all()
        assert intent == DecisionIntent.NONE
    
    def test_all_none_no_confirm(self):
        router = DecisionRouter(_make_policy("ANY"))
        
        kb = FakeSource()  # Will return NONE (no confirms scheduled)
        router.register_source('keyboard', kb)
        
        mock_eeg = MockEEGSource({'eeg_mock': {'enabled': True, 'confirm_probability': 0.0, 'quality_mean': 0.5, 'quality_std': 0.0, 'artifact_probability': 0.0}})
        router.register_source('eeg', mock_eeg)
        
        for _ in range(100):
            intent, _, _, _ = router.read_all()
            assert intent == DecisionIntent.NONE


if __name__ == '__main__':
    pytest.main([__file__, '-v'])


