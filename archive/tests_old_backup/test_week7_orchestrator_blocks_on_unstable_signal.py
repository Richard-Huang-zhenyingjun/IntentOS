"""
Week 7 Tests: EEG Stability Blocking

Tests:
- Unstable signal blocks confirmation
- PAUSED state triggered on prolonged instability
- State machine never executes with unstable signal
"""

import pytest
import yaml
import sys
from unittest.mock import Mock

sys.path.insert(0, 'src')

from intent_core import ArmStateMachine, ArmUIState
from intent_core.arm_intent_schema import DecisionSignal, ArmDecision


@pytest.fixture
def state_machine():
    """Create state machine."""
    return ArmStateMachine()


@pytest.fixture
def mock_world():
    """Create mock world model."""
    world = Mock()
    world.get_available_actions.return_value = []
    world.propose_next_action.return_value = None
    return world


def test_eeg_stability_check_accepts_stable_signal(state_machine):
    """Test stable EEG signal is accepted."""
    eeg_meta = {
        "stable": True,
        "blocked": False,
        "reason": "",
    }
    
    result = state_machine.check_eeg_stability(eeg_meta)
    
    assert result == True
    assert state_machine.eeg_unstable_frames == 0


def test_eeg_stability_check_detects_unstable(state_machine):
    """Test unstable EEG signal is detected."""
    eeg_meta = {
        "stable": False,
        "blocked": True,
        "reason": "High variance",
    }
    
    result = state_machine.check_eeg_stability(eeg_meta)
    
    assert result == False
    assert state_machine.eeg_unstable_frames > 0


def test_prolonged_instability_triggers_pause(state_machine, mock_world):
    """Test prolonged instability → PAUSED state."""
    # Set state to AWAITING_CONFIRM
    state_machine.state = ArmUIState.AWAITING_CONFIRM
    state_machine.active_proposal = Mock()
    
    # Feed unstable signal repeatedly
    eeg_meta = {
        "stable": False,
        "blocked": True,
        "reason": "No signal",
    }
    
    for _ in range(35):  # More than max_unstable_frames (30)
        state_machine.check_eeg_stability(eeg_meta)
    
    # Should transition to PAUSED
    assert state_machine.state == ArmUIState.PAUSED
    assert state_machine.active_proposal is None


def test_stable_signal_resets_unstable_counter(state_machine):
    """Test stable signal resets unstable counter."""
    # Build up unstable frames
    eeg_meta_unstable = {
        "stable": False,
        "blocked": True,
        "reason": "Missing data",
    }
    
    for _ in range(10):
        state_machine.check_eeg_stability(eeg_meta_unstable)
    
    assert state_machine.eeg_unstable_frames == 10
    
    # Now stable signal
    eeg_meta_stable = {
        "stable": True,
        "blocked": False,
        "reason": "",
    }
    
    state_machine.check_eeg_stability(eeg_meta_stable)
    
    # Should reset counter
    assert state_machine.eeg_unstable_frames == 0


def test_paused_state_requires_unlock_to_recover(state_machine):
    """Test PAUSED state requires target unlock to recover."""
    # Enter PAUSED state
    state_machine.state = ArmUIState.PAUSED
    state_machine.active_target_id = 123
    state_machine.target_locked = True
    
    # Tick while target still locked
    state_machine._tick_paused()
    
    # Should remain PAUSED
    assert state_machine.state == ArmUIState.PAUSED
    
    # Unlock target
    state_machine.set_target(None, False)
    state_machine._tick_paused()
    
    # Should recover to IDLE
    assert state_machine.state == ArmUIState.IDLE


def test_no_eeg_meta_is_treated_as_stable(state_machine):
    """Test None eeg_meta (keyboard mode) is always stable."""
    result = state_machine.check_eeg_stability(None)
    
    assert result == True
    assert state_machine.eeg_unstable_frames == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])




