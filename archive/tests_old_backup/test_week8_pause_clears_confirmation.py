"""
Week 8 Tests: Pause Clears Confirmation

Tests:
- Pause clears active proposal
- Pause clears confirmation state
- Recovery requires re-scoping (unlock + re-lock)
- No auto-resume
"""

import pytest
import yaml
import sys
from unittest.mock import Mock

sys.path.insert(0, 'src')

from intent_core import ArmStateMachine, ArmUIState
from intent_core.arm_intent_schema import ArmProposal, DecisionSignal, ArmDecision
from robotics.action_types import ArmActionType
from robotics.recovery import PauseTrigger, RecoveryPlan


@pytest.fixture
def state_machine():
    """Create state machine."""
    return ArmStateMachine()


@pytest.fixture
def mock_world():
    """Create mock world model."""
    world = Mock()
    world.get_available_actions.return_value = [ArmActionType.MOVE_ARM_UP]
    
    proposal = Mock(spec=ArmProposal)
    proposal.target_object_id = 1
    proposal.action_type = ArmActionType.MOVE_ARM_UP
    proposal.reason = "Test action"
    proposal.available_actions = [ArmActionType.MOVE_ARM_UP]
    proposal.timestamp = 0.0
    
    world.propose_next_action.return_value = proposal
    
    return world


def test_pause_clears_proposal(state_machine, mock_world):
    """Test that pause clears active proposal."""
    # Set up state with proposal
    state_machine.state = ArmUIState.AWAITING_CONFIRM
    
    proposal = Mock(spec=ArmProposal)
    proposal.target_object_id = 1
    proposal.action_type = ArmActionType.REACH_FORWARD
    proposal.reason = "Test"
    proposal.available_actions = [ArmActionType.REACH_FORWARD]
    proposal.timestamp = 0.0
    
    state_machine.active_proposal = proposal
    
    # Trigger pause
    state_machine.trigger_pause("eeg_unstable")
    
    # Verify state and proposal cleared
    assert state_machine.state == ArmUIState.PAUSED
    assert state_machine.active_proposal is None


def test_pause_from_awaiting_confirm(state_machine, mock_world):
    """Test pause transition from AWAITING_CONFIRM state."""
    # Enter AWAITING_CONFIRM
    state_machine.state = ArmUIState.SELECTING_ACTION
    state_machine.set_target(1, True)
    
    decision = ArmDecision.idle()
    state_machine.tick(mock_world, decision, None)
    
    # Should now be in AWAITING_CONFIRM with proposal
    assert state_machine.state == ArmUIState.AWAITING_CONFIRM
    assert state_machine.active_proposal is not None
    
    # Trigger pause
    state_machine.trigger_pause("target_lost")
    
    # Verify pause
    assert state_machine.state == ArmUIState.PAUSED
    assert state_machine.active_proposal is None


def test_recovery_requires_target_unlock(state_machine):
    """Test recovery requires target unlock (re-scoping)."""
    # Enter PAUSED state
    state_machine.state = ArmUIState.PAUSED
    state_machine.in_recovery = False
    state_machine.active_target_id = 1
    state_machine.target_locked = True
    
    # Mark recovery conditions met
    state_machine.check_recovery_ready(True)
    
    # Tick PAUSED state
    state_machine._tick_paused()
    
    # Should enter recovery mode but stay in PAUSED
    assert state_machine.state == ArmUIState.PAUSED
    assert state_machine.in_recovery == True
    
    # Still locked, should remain in PAUSED
    state_machine._tick_paused()
    assert state_machine.state == ArmUIState.PAUSED
    
    # Now unlock target
    state_machine.set_target(None, False)
    state_machine._tick_paused()
    
    # Should transition to IDLE
    assert state_machine.state == ArmUIState.IDLE
    assert state_machine.in_recovery == False


def test_no_auto_resume_from_pause(state_machine, mock_world):
    """Test that system never auto-resumes from PAUSED."""
    # Enter PAUSED
    state_machine.state = ArmUIState.PAUSED
    state_machine.active_target_id = 1
    state_machine.target_locked = True
    
    # Tick multiple times with recovery conditions met
    state_machine.check_recovery_ready(True)
    
    for _ in range(20):
        state_machine._tick_paused()
        # Should stay in PAUSED until target unlocked
        if state_machine.target_locked:
            assert state_machine.state == ArmUIState.PAUSED


def test_recovery_plan_creation():
    """Test recovery plan generation."""
    plan = RecoveryPlan.create(PauseTrigger.EEG_UNSTABLE)
    
    assert plan.should_pause == True
    assert plan.trigger == PauseTrigger.EEG_UNSTABLE
    assert len(plan.required_steps) > 0
    assert "EEG" in plan.explanation


def test_recovery_plan_eeg_requirements():
    """Test EEG recovery requirements."""
    plan = RecoveryPlan.create(PauseTrigger.EEG_DROPOUT)
    
    # Mock EEG status - unstable
    eeg_status = {"stable": False, "blocked": True}
    
    # Mock world and selector
    world = Mock()
    selector = Mock()
    selector.is_locked.return_value = True
    
    # Should not be complete (EEG unstable)
    assert plan.is_recovery_complete(world, eeg_status, selector) == False
    
    # Now stable
    eeg_status = {"stable": True, "blocked": False}
    
    # Should be complete
    assert plan.is_recovery_complete(world, eeg_status, selector) == True


def test_recovery_plan_target_requirements():
    """Test target loss recovery requirements."""
    plan = RecoveryPlan.create(PauseTrigger.TARGET_LOST)
    
    # Mock selector - not locked
    selector = Mock()
    selector.is_locked.return_value = False
    
    # Mock world and EEG
    world = Mock()
    eeg_status = {"stable": True, "blocked": False}
    
    # Should not be complete (target not locked)
    assert plan.is_recovery_complete(world, eeg_status, selector) == False
    
    # Now locked
    selector.is_locked.return_value = True
    
    # Should be complete
    assert plan.is_recovery_complete(world, eeg_status, selector) == True


def test_pause_resets_recovery_state(state_machine):
    """Test that exiting PAUSED resets recovery state."""
    # Enter PAUSED with recovery in progress
    state_machine.state = ArmUIState.PAUSED
    state_machine.in_recovery = True
    state_machine.recovery_conditions_met = True
    
    # Exit to IDLE
    state_machine.set_target(None, False)
    state_machine.check_recovery_ready(True)
    state_machine._tick_paused()
    
    # Recovery state should be reset
    assert state_machine.state == ArmUIState.IDLE
    assert state_machine.in_recovery == False
    assert state_machine.recovery_conditions_met == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

