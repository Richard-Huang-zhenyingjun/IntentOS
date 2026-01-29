"""
Week 8: Fault injection tests.
Test deterministic fault injection system.
"""

import pytest
import yaml
from src.robotics.recovery import FaultInjector, FaultType, ScheduledFault


@pytest.fixture
def fault_config():
    """Load fault configuration."""
    cfg = yaml.safe_load(open('configs/robotics.yaml'))
    return cfg['faults']


def test_fault_injector_initialization(fault_config):
    """Test fault injector initializes with config."""
    fi = FaultInjector(fault_config)
    
    assert fi.enabled is False  # Disabled by default
    assert fi.seed == 42
    assert len(fi.schedule) == 0


def test_schedule_fault(fault_config):
    """Test scheduling a fault."""
    fi = FaultInjector(fault_config)
    fi.enabled = True
    
    fi.schedule_fault(FaultType.EEG_DROPOUT, trigger_frame=10, duration_frames=5)
    
    assert len(fi.schedule) == 1
    assert fi.schedule[0].fault_type == FaultType.EEG_DROPOUT
    assert fi.schedule[0].trigger_frame == 10
    assert fi.schedule[0].duration_frames == 5


def test_fault_activation_at_trigger_frame(fault_config):
    """Test fault activates at trigger frame."""
    fi = FaultInjector(fault_config)
    fi.enabled = True
    
    fi.schedule_fault(FaultType.EEG_DROPOUT, trigger_frame=10, duration_frames=5)
    
    # Before trigger frame
    for frame in range(10):
        fi.tick(frame)
        assert not fi.should_inject_eeg_dropout()
    
    # At trigger frame
    fi.tick(10)
    assert fi.should_inject_eeg_dropout()


def test_fault_duration(fault_config):
    """Test fault lasts for specified duration."""
    fi = FaultInjector(fault_config)
    fi.enabled = True
    
    fi.schedule_fault(FaultType.TARGET_LOST, trigger_frame=10, duration_frames=5)
    
    # Activate fault
    fi.tick(10)
    assert fi.should_inject_target_lost()
    
    # Should remain active for duration
    for frame in range(11, 15):
        fi.tick(frame)
        assert fi.should_inject_target_lost(), f"Should be active at frame {frame}"
    
    # Should deactivate after duration
    fi.tick(15)
    assert not fi.should_inject_target_lost()


def test_multiple_faults(fault_config):
    """Test multiple faults can be scheduled."""
    fi = FaultInjector(fault_config)
    fi.enabled = True
    
    fi.schedule_fault(FaultType.EEG_DROPOUT, trigger_frame=10, duration_frames=5)
    fi.schedule_fault(FaultType.TARGET_LOST, trigger_frame=20, duration_frames=10)
    
    assert len(fi.schedule) == 2
    
    # First fault
    fi.tick(10)
    assert fi.should_inject_eeg_dropout()
    assert not fi.should_inject_target_lost()
    
    # Between faults
    fi.tick(16)
    assert not fi.should_inject_eeg_dropout()
    assert not fi.should_inject_target_lost()
    
    # Second fault
    fi.tick(20)
    assert not fi.should_inject_eeg_dropout()
    assert fi.should_inject_target_lost()


def test_overlapping_faults(fault_config):
    """Test overlapping faults can be active simultaneously."""
    fi = FaultInjector(fault_config)
    fi.enabled = True
    
    fi.schedule_fault(FaultType.EEG_UNSTABLE, trigger_frame=10, duration_frames=10)
    fi.schedule_fault(FaultType.TARGET_LOST, trigger_frame=15, duration_frames=10)
    
    # Tick through to overlap period
    for frame in range(16):
        fi.tick(frame)
    
    # Both active in overlap period (frame 15)
    assert fi.should_inject_eeg_unstable()
    assert fi.should_inject_target_lost()
    
    active = fi.get_active_faults()
    assert FaultType.EEG_UNSTABLE in active
    assert FaultType.TARGET_LOST in active


def test_injection_log(fault_config):
    """Test injection log records all events."""
    fi = FaultInjector(fault_config)
    fi.enabled = True
    
    fi.schedule_fault(FaultType.EEG_DROPOUT, trigger_frame=10, duration_frames=5)
    
    # Trigger and clear
    for frame in range(20):
        fi.tick(frame)
    
    log = fi.get_injection_log()
    assert len(log) >= 2  # At least activate and deactivate
    assert any("INJECT" in entry for entry in log)
    assert any("CLEAR" in entry for entry in log)


def test_instant_fault(fault_config):
    """Test instant fault (duration=0)."""
    fi = FaultInjector(fault_config)
    fi.enabled = True
    
    fi.schedule_fault(FaultType.EEG_DROPOUT, trigger_frame=10, duration_frames=0)
    
    # Activate at trigger frame
    fi.tick(10)
    assert fi.should_inject_eeg_dropout()
    
    # Should remain active (instant faults don't auto-clear)
    fi.tick(11)
    assert fi.should_inject_eeg_dropout()


def test_disabled_injector(fault_config):
    """Test disabled injector doesn't inject faults."""
    fi = FaultInjector(fault_config)
    assert fi.enabled is False
    
    fi.schedule_fault(FaultType.EEG_DROPOUT, trigger_frame=10, duration_frames=5)
    
    fi.tick(10)
    assert not fi.should_inject_eeg_dropout()


def test_reset_clears_state(fault_config):
    """Test reset clears active faults and frame counter."""
    fi = FaultInjector(fault_config)
    fi.enabled = True
    
    fi.schedule_fault(FaultType.EEG_DROPOUT, trigger_frame=10, duration_frames=5)
    fi.tick(10)
    assert fi.should_inject_eeg_dropout()
    
    fi.reset()
    
    assert fi.current_frame == 0
    assert len(fi.active_faults) == 0
    assert len(fi.get_injection_log()) == 0


def test_clear_schedule(fault_config):
    """Test clearing fault schedule."""
    fi = FaultInjector(fault_config)
    fi.enabled = True
    
    fi.schedule_fault(FaultType.EEG_DROPOUT, trigger_frame=10, duration_frames=5)
    fi.schedule_fault(FaultType.TARGET_LOST, trigger_frame=20, duration_frames=10)
    
    assert len(fi.schedule) == 2
    
    fi.clear_schedule()
    
    assert len(fi.schedule) == 0


def test_is_fault_active(fault_config):
    """Test checking if specific fault is active."""
    fi = FaultInjector(fault_config)
    fi.enabled = True
    
    fi.schedule_fault(FaultType.EEG_DROPOUT, trigger_frame=10, duration_frames=5)
    
    fi.tick(10)
    
    assert fi.is_fault_active(FaultType.EEG_DROPOUT)
    assert not fi.is_fault_active(FaultType.TARGET_LOST)


def test_deterministic_seed(fault_config):
    """Test deterministic behavior with seed."""
    fi1 = FaultInjector(fault_config)
    fi1.enabled = True
    
    fi2 = FaultInjector(fault_config)
    fi2.enabled = True
    
    # Both should have same seed
    assert fi1.seed == fi2.seed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

