"""
Week 4 Tests: State Machine Workflow

Tests:
- State transitions
- Proposal generation
- Confirm/Cancel handling
- Never execute without CONFIRM
- CANCEL clears proposal
"""

import pytest
import sys
from unittest.mock import Mock

sys.path.insert(0, 'src')

from intent_core import ArmStateMachine, ArmUIState, DecisionSignal, ArmDecision
from robotics.action_types import ArmActionType


@pytest.fixture
def state_machine():
    """Create state machine."""
    return ArmStateMachine()


@pytest.fixture
def mock_world():
    """Create mock world model."""
    world = Mock()
    world.get_available_actions.return_value = [
        ArmActionType.MOVE_ARM_UP,
        ArmActionType.REACH_FORWARD
    ]
    world.propose_next_action.return_value = ArmActionType.MOVE_ARM_UP
    world.get_action_reason.return_value = "Test reason"
    return world


def test_initial_state_is_idle(state_machine):
    """Test state machine starts in IDLE."""
    assert state_machine.state == ArmUIState.IDLE


def test_no_target_stays_idle(state_machine, mock_world):
    """Test no target → stays IDLE."""
    state_machine.set_target(None, False)
    state_machine.tick(mock_world, ArmDecision.idle())
    assert state_machine.state == ArmUIState.IDLE


def test_unlocked_target_goes_to_targeting(state_machine, mock_world):
    """Test unlocked target → TARGETING."""
    state_machine.set_target(123, locked=False)
    state_machine.tick(mock_world, ArmDecision.idle())
    assert state_machine.state == ArmUIState.TARGETING


def test_locked_target_goes_to_selecting(state_machine, mock_world):
    """Test locked target → SELECTING_ACTION."""
    state_machine.set_target(123, locked=True)
    state_machine.tick(mock_world, ArmDecision.idle())
    assert state_machine.state == ArmUIState.SELECTING_ACTION


def test_selecting_creates_proposal(state_machine, mock_world):
    """Test SELECTING_ACTION → creates proposal → AWAITING_CONFIRM."""
    state_machine.set_target(123, locked=True)
    state_machine.tick(mock_world, ArmDecision.idle())  # → SELECTING
    state_machine.tick(mock_world, ArmDecision.idle())  # → AWAITING_CONFIRM
    
    assert state_machine.state == ArmUIState.AWAITING_CONFIRM
    assert state_machine.active_proposal is not None
    assert state_machine.active_proposal.action_type == ArmActionType.MOVE_ARM_UP


def test_confirm_transitions_to_executing(state_machine, mock_world):
    """Test CONFIRM → EXECUTING."""
    # Setup: reach AWAITING_CONFIRM
    state_machine.set_target(123, locked=True)
    state_machine.tick(mock_world, ArmDecision.idle())  # → SELECTING
    state_machine.tick(mock_world, ArmDecision.idle())  # → AWAITING_CONFIRM
    
    # Confirm
    confirm = ArmDecision.from_keyboard(DecisionSignal.CONFIRM)
    state_machine.tick(mock_world, confirm)
    
    assert state_machine.state == ArmUIState.EXECUTING


def test_cancel_clears_proposal_and_returns_to_selecting(state_machine, mock_world):
    """Test CANCEL → clears proposal → SELECTING_ACTION."""
    # Setup: reach AWAITING_CONFIRM
    state_machine.set_target(123, locked=True)
    state_machine.tick(mock_world, ArmDecision.idle())  # → SELECTING
    state_machine.tick(mock_world, ArmDecision.idle())  # → AWAITING_CONFIRM
    
    proposal_before = state_machine.active_proposal
    assert proposal_before is not None
    
    # Cancel
    cancel = ArmDecision.from_keyboard(DecisionSignal.CANCEL)
    state_machine.tick(mock_world, cancel)
    
    assert state_machine.state == ArmUIState.SELECTING_ACTION
    assert state_machine.active_proposal is None  # Cleared


def test_executing_completes_to_done(state_machine, mock_world):
    """Test EXECUTING → DONE (Week 4: immediate completion)."""
    # Setup: reach EXECUTING
    state_machine.set_target(123, locked=True)
    state_machine.tick(mock_world, ArmDecision.idle())  # → SELECTING
    state_machine.tick(mock_world, ArmDecision.idle())  # → AWAITING_CONFIRM
    confirm = ArmDecision.from_keyboard(DecisionSignal.CONFIRM)
    state_machine.tick(mock_world, confirm)  # → EXECUTING
    
    # Execute
    state_machine.tick(mock_world, ArmDecision.idle())
    
    assert state_machine.state == ArmUIState.DONE


def test_never_execute_without_confirm(state_machine, mock_world):
    """Test CRITICAL: cannot reach EXECUTING without CONFIRM."""
    # Setup: reach AWAITING_CONFIRM
    state_machine.set_target(123, locked=True)
    state_machine.tick(mock_world, ArmDecision.idle())  # → SELECTING
    state_machine.tick(mock_world, ArmDecision.idle())  # → AWAITING_CONFIRM
    
    # Try to proceed with IDLE (no decision)
    for _ in range(100):
        state_machine.tick(mock_world, ArmDecision.idle())
        assert state_machine.state != ArmUIState.EXECUTING, "Must not execute without CONFIRM"


def test_reset_clears_state(state_machine, mock_world):
    """Test reset() clears all state."""
    # Setup: reach AWAITING_CONFIRM
    state_machine.set_target(123, locked=True)
    state_machine.tick(mock_world, ArmDecision.idle())
    state_machine.tick(mock_world, ArmDecision.idle())
    
    # Reset
    state_machine.reset()
    
    assert state_machine.state == ArmUIState.IDLE
    assert state_machine.active_target_id is None
    assert state_machine.active_proposal is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])




