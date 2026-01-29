"""
Week 8: Undo and cancel tests.
Test return-to-rest and safe retreat functionality.
"""

import pytest
import yaml
from src.robotics.recovery import UndoController, TrustMetricsTracker, PauseTrigger


@pytest.fixture
def recovery_config():
    """Load recovery configuration."""
    cfg = yaml.safe_load(open('configs/robotics.yaml'))
    return cfg['recovery']


def test_undo_controller_initialization(recovery_config):
    """Test undo controller initializes with config."""
    uc = UndoController(recovery_config)
    
    assert uc.enable_return_to_rest is True
    assert uc.detach_before_rest is True
    assert uc.rest_joint_positions == []
    assert uc.max_steps == 1200


def test_undo_controller_not_active_initially(recovery_config):
    """Test undo controller is not active initially."""
    uc = UndoController(recovery_config)
    
    assert not uc.is_active()


def test_undo_controller_reset(recovery_config):
    """Test undo controller reset."""
    uc = UndoController(recovery_config)
    
    uc.active = True
    uc.steps_used = 100
    
    uc.reset()
    
    assert not uc.is_active()
    assert uc.steps_used == 0


def test_trust_metrics_initialization():
    """Test trust metrics tracker initializes correctly."""
    tracker = TrustMetricsTracker()
    
    assert tracker.false_executions == 0
    assert tracker.confirmed_executions == 0
    assert len(tracker.pause_events) == 0
    assert len(tracker.execution_events) == 0


def test_trust_metrics_record_confirmed_execution():
    """Test recording confirmed execution."""
    tracker = TrustMetricsTracker()
    
    tracker.record_execution("MOVE_ARM_UP", confirmed=True, success=True)
    
    assert tracker.confirmed_executions == 1
    assert tracker.false_executions == 0
    assert len(tracker.execution_events) == 1


def test_trust_metrics_record_false_execution():
    """Test recording false execution (safety violation)."""
    tracker = TrustMetricsTracker()
    
    tracker.record_execution("MOVE_ARM_UP", confirmed=False, success=True)
    
    assert tracker.confirmed_executions == 0
    assert tracker.false_executions == 1
    assert len(tracker.execution_events) == 1


def test_trust_metrics_record_pause():
    """Test recording pause event."""
    tracker = TrustMetricsTracker()
    
    tracker.record_pause(PauseTrigger.EEG_UNSTABLE, "EEG signal unstable")
    
    assert len(tracker.pause_events) == 1
    assert tracker.is_paused
    assert tracker.pause_events[0].trigger == PauseTrigger.EEG_UNSTABLE


def test_trust_metrics_record_recovery():
    """Test recording recovery from pause."""
    tracker = TrustMetricsTracker()
    
    tracker.record_pause(PauseTrigger.TARGET_LOST, "Target lost")
    tracker.record_recovery()
    
    assert not tracker.is_paused
    assert tracker.pause_events[0].recovered is True
    assert tracker.pause_events[0].recovery_time is not None


def test_trust_metrics_generate_report():
    """Test generating trust metrics report."""
    tracker = TrustMetricsTracker()
    
    # Record some events
    tracker.record_execution("MOVE_ARM_UP", confirmed=True, success=True)
    tracker.record_execution("REACH_FORWARD", confirmed=True, success=True)
    tracker.record_pause(PauseTrigger.EEG_UNSTABLE, "EEG unstable")
    tracker.record_recovery()
    
    report = tracker.generate_report()
    
    assert report.false_executions == 0
    assert report.confirmed_executions == 2
    assert report.pauses_triggered == 1
    assert report.pauses_recovered == 1
    assert report.all_refusals_explained is True


def test_trust_metrics_safety_guarantee_pass():
    """Test safety guarantee passes with no false executions."""
    tracker = TrustMetricsTracker()
    
    tracker.record_execution("MOVE_ARM_UP", confirmed=True, success=True)
    tracker.record_execution("REACH_FORWARD", confirmed=True, success=True)
    
    report = tracker.generate_report()
    report_dict = report.to_dict()
    
    assert report_dict["safety_metrics"]["safety_guarantee"] == "PASS"


def test_trust_metrics_safety_guarantee_fail():
    """Test safety guarantee fails with false executions."""
    tracker = TrustMetricsTracker()
    
    tracker.record_execution("MOVE_ARM_UP", confirmed=False, success=True)
    
    report = tracker.generate_report()
    report_dict = report.to_dict()
    
    assert report_dict["safety_metrics"]["safety_guarantee"] == "FAIL"


def test_trust_metrics_pause_breakdown():
    """Test pause breakdown by trigger type."""
    tracker = TrustMetricsTracker()
    
    tracker.record_pause(PauseTrigger.EEG_UNSTABLE, "EEG unstable")
    tracker.record_recovery()
    tracker.record_pause(PauseTrigger.TARGET_LOST, "Target lost")
    tracker.record_recovery()
    tracker.record_pause(PauseTrigger.EEG_UNSTABLE, "EEG unstable again")
    tracker.record_recovery()
    
    report = tracker.generate_report()
    
    assert report.pause_by_trigger["eeg_unstable"] == 2
    assert report.pause_by_trigger["target_lost"] == 1


def test_trust_metrics_recovery_rate():
    """Test recovery rate calculation."""
    tracker = TrustMetricsTracker()
    
    # 3 pauses, 2 recovered
    tracker.record_pause(PauseTrigger.EEG_UNSTABLE, "EEG unstable")
    tracker.record_recovery()
    tracker.record_pause(PauseTrigger.TARGET_LOST, "Target lost")
    tracker.record_recovery()
    tracker.record_pause(PauseTrigger.EEG_DROPOUT, "EEG dropout")
    # Don't recover from last one
    
    report = tracker.generate_report()
    report_dict = report.to_dict()
    
    recovery_rate = report_dict["pause_metrics"]["recovery_rate"]
    assert recovery_rate == pytest.approx(2.0 / 3.0)


def test_trust_metrics_tick():
    """Test frame counter advancement."""
    tracker = TrustMetricsTracker()
    
    assert tracker.current_frame == 0
    
    tracker.tick()
    assert tracker.current_frame == 1
    
    tracker.tick(10)
    assert tracker.current_frame == 10


def test_trust_metrics_reset():
    """Test metrics reset."""
    tracker = TrustMetricsTracker()
    
    tracker.record_execution("MOVE_ARM_UP", confirmed=True, success=True)
    tracker.record_pause(PauseTrigger.EEG_UNSTABLE, "EEG unstable")
    tracker.tick(100)
    
    tracker.reset()
    
    assert tracker.current_frame == 0
    assert tracker.false_executions == 0
    assert tracker.confirmed_executions == 0
    assert len(tracker.pause_events) == 0
    assert len(tracker.execution_events) == 0


def test_trust_metrics_to_dict():
    """Test report serialization to dict."""
    tracker = TrustMetricsTracker()
    
    tracker.record_execution("MOVE_ARM_UP", confirmed=True, success=True)
    tracker.record_pause(PauseTrigger.TARGET_LOST, "Target lost")
    tracker.record_recovery()
    
    report = tracker.generate_report()
    report_dict = report.to_dict()
    
    assert "safety_metrics" in report_dict
    assert "pause_metrics" in report_dict
    assert "timing" in report_dict
    assert "transparency" in report_dict


if __name__ == "__main__":
    pytest.main([__file__, "-v"])




