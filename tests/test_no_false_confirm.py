"""
CRITICAL INVARIANT: The decision pipeline can never CREATE a confirm.
If no source signals CONFIRM, the output must be NONE or CANCEL.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.input.pipeline import DecisionPipeline
from src.input.router import DecisionRouter
from src.input.filter import DecisionFilter
from src.input.source_fake import FakeSource
from src.input.source_eeg_mock import MockEEGSource
from src.input.types import DecisionIntent
from src.input.policies import DecisionPolicy, RoutingMode


def _build_pipeline(mode: str = "ANY") -> tuple:
    """Build pipeline with no confirms scheduled"""
    config = {
        'input': {
            'mode': mode,
            'sources_enabled': ['keyboard', 'eeg'],
            'debounce_frames': 0,
            'confirm_hold_frames': 1,
            'min_quality': 0.0,
            'dual': {'sources': ['keyboard', 'eeg'], 'window_ms': 900},
        },
        'eeg_mock': {
            'enabled': True,
            'confirm_probability': 0.0,  # Never confirms
            'quality_mean': 0.5,
            'quality_std': 0.1,
            'artifact_probability': 0.0,
            'seed': 42,
        },
    }
    
    policy = DecisionPolicy.from_config(config)
    router = DecisionRouter(policy)
    
    kb = FakeSource()  # No confirms scheduled
    router.register_source('keyboard', kb)
    
    mock_eeg = MockEEGSource(config)
    router.register_source('eeg', mock_eeg)
    
    decision_filter = DecisionFilter(config)
    pipeline = DecisionPipeline(router, decision_filter)
    
    return pipeline


def test_no_false_confirm_any_mode():
    """ANY mode: no source confirms → pipeline never outputs CONFIRM"""
    pipeline = _build_pipeline("ANY")
    
    for frame in range(1000):
        decision = pipeline.tick(frame)
        assert decision.intent != DecisionIntent.CONFIRM, (
            f"False confirm at frame {frame}! "
            f"source={decision.source_type}, quality={decision.quality}"
        )


def test_no_false_confirm_keyboard_only():
    """KEYBOARD_ONLY: no keyboard confirm → never outputs CONFIRM"""
    pipeline = _build_pipeline("KEYBOARD_ONLY")
    
    for frame in range(1000):
        decision = pipeline.tick(frame)
        assert decision.intent != DecisionIntent.CONFIRM


def test_no_false_confirm_dual():
    """DUAL mode: no dual confirm → never outputs CONFIRM"""
    pipeline = _build_pipeline("DUAL")
    
    for frame in range(1000):
        decision = pipeline.tick(frame)
        assert decision.intent != DecisionIntent.CONFIRM


if __name__ == '__main__':
    pytest.main([__file__, '-v'])



