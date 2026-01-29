"""
Week 8: Recovery integration tests.
Test recovery controller integration with orchestrator.
"""

import pytest
import yaml
from robotics.recovery import (
    RecoveryController, PauseTrigger, RecoveryState
)


@pytest.fixture
def recovery_config():
    """Load recovery configuration."""
    cfg = yaml.safe_load(open('configs/robotics.yaml'))
    return cfg['recovery']


def test_recovery_controller_initialization(recovery_config):
    """Test recovery controller initializes with config."""
    rc = RecoveryController(recovery_config)
    
    assert rc.enabled is True
    assert rc.target_loss_grace == 10
    assert rc.eeg_unstable_grace == 30
    assert rc.require_rescope is True
    assert rc.clear_confirmation is True
    assert rc.freeze_on_pause is True


def test_eeg_stability_grace_period(recovery_config):
    """Test EEG unstable uses grace period before pause."""
    rc = RecoveryController(recovery_config)
    
    # First few unstable frames should not pause
    for i in range(29):
        result = rc.check_eeg_stable(False)
        assert result is True, f"Should not pause at frame {i}"
        assert rc.get_status().state in (RecoveryState.NORMAL, RecoveryState.GRACE)
    
    # 30th frame should trigger pause
    result = rc.check_eeg_stable(False)
    assert result is False
    assert rc.is_paused
    assert rc.get_status().state == RecoveryState.PAUSED
    assert rc.get_status().trigger == PauseTrigger.EEG_UNSTABLE


def test_target_loss_grace_period(recovery_config):
    """Test target loss uses grace period before pause."""
    rc = RecoveryController(recovery_config)
    
    # First few invisible frames should not pause
    for i in range(9):
        result = rc.check_target_visible(False)
        assert result is True, f"Should not pause at frame {i}"
    
    # 10th frame should trigger pause
    result = rc.check_target_visible(False)
    assert result is False
    assert rc.is_paused
    assert rc.get_status().trigger == PauseTrigger.TARGET_LOST


def test_eeg_dropout_immediate_pause(recovery_config):
    """Test EEG dropout pauses immediately (no grace)."""
    rc = RecoveryController(recovery_config)
    
    # First dropout should pause immediately
    result = rc.check_eeg_connected(False)
    assert result is False
    assert rc.is_paused
    assert rc.get_status().trigger == PauseTrigger.EEG_DROPOUT


def test_recovery_clears_grace_counters(recovery_config):
    """Test that recovery clears grace counters."""
    rc = RecoveryController(recovery_config)
    
    # Build up grace counter
    for i in range(5):
        rc.check_eeg_stable(False)
    
    # Recover
    rc.check_eeg_stable(True)
    
    # Should reset grace counter
    for i in range(29):
        result = rc.check_eeg_stable(False)
        assert result is True


def test_pause_freezes_motion(recovery_config):
    """Test that pause triggers motion freeze."""
    rc = RecoveryController(recovery_config)
    
    assert rc.should_freeze_motion is False
    
    # Trigger pause
    rc.check_eeg_connected(False)
    
    assert rc.should_freeze_motion is True


def test_reset_clears_pause_state(recovery_config):
    """Test that reset clears pause state."""
    rc = RecoveryController(recovery_config)
    
    # Trigger pause
    rc.check_eeg_connected(False)
    assert rc.is_paused
    
    # Reset
    rc.reset()
    
    assert not rc.is_paused
    assert rc.get_status().state == RecoveryState.NORMAL


def test_action_timeout_detection(recovery_config):
    """Test action timeout detection."""
    rc = RecoveryController(recovery_config)
    
    import time
    start_time = time.time() - 11.0  # 11 seconds ago
    
    result = rc.check_action_timeout(start_time, max_duration=10.0)
    assert result is False
    assert rc.is_paused
    assert rc.get_status().trigger == PauseTrigger.ACTION_TIMEOUT


def test_cancel_trigger(recovery_config):
    """Test user cancellation trigger."""
    rc = RecoveryController(recovery_config)
    
    rc.trigger_cancel()
    
    assert rc.is_paused
    assert rc.get_status().trigger == PauseTrigger.CANCEL_REQUESTED


def test_status_explanation(recovery_config):
    """Test that status includes explanation."""
    rc = RecoveryController(recovery_config)
    
    # Normal state
    status = rc.get_status()
    assert "operational" in status.explanation.lower()
    
    # Paused state
    rc.check_eeg_connected(False)
    status = rc.get_status()
    assert "paused" in status.explanation.lower()
    assert "eeg" in status.explanation.lower()


def test_grace_frames_remaining(recovery_config):
    """Test grace frames remaining calculation."""
    rc = RecoveryController(recovery_config)
    
    # Build up grace
    for i in range(5):
        rc.check_eeg_stable(False)
        status = rc.get_status()
        if status.state == RecoveryState.GRACE:
            assert status.grace_frames_remaining > 0
            assert status.grace_frames_remaining <= 30


def test_multiple_pause_triggers(recovery_config):
    """Test that first pause trigger wins."""
    rc = RecoveryController(recovery_config)
    
    # Trigger EEG dropout first
    rc.check_eeg_connected(False)
    first_trigger = rc.get_status().trigger
    
    # Try to trigger target loss (should be ignored)
    rc.check_target_visible(False)
    
    # Should still be EEG dropout
    assert rc.get_status().trigger == first_trigger


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

