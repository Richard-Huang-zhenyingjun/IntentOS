"""
Week 8 Tests: Fault Injection Determinism

Tests:
- Same seed produces same fault sequence
- Fault schedules work correctly
- Fault activation timing is deterministic
"""

import pytest
import sys
import time

sys.path.insert(0, 'src')

from sim import FaultInjector, FaultType, ScheduledFault


def test_fault_injector_initialization():
    """Test fault injector initializes correctly."""
    schedule = [
        ScheduledFault(time_s=1.0, fault_type=FaultType.EEG_DROPOUT, duration_s=2.0),
        ScheduledFault(time_s=5.0, fault_type=FaultType.TARGET_LOSS, duration_s=1.0),
    ]
    
    injector = FaultInjector(seed=42, schedule=schedule)
    
    assert injector.seed == 42
    assert len(injector.schedule) == 2
    assert not injector.enabled


def test_fault_activation_timing():
    """Test faults activate at correct times."""
    fault = ScheduledFault(
        time_s=2.0,
        fault_type=FaultType.EEG_DROPOUT,
        duration_s=1.5
    )
    
    # Before activation
    assert not fault.is_active(1.0)
    assert not fault.is_active(1.9)
    
    # During activation
    assert fault.is_active(2.0)
    assert fault.is_active(2.5)
    assert fault.is_active(3.4)
    
    # After deactivation
    assert not fault.is_active(3.5)
    assert not fault.is_active(4.0)


def test_fault_injector_updates():
    """Test fault injector updates correctly."""
    schedule = [
        ScheduledFault(time_s=1.0, fault_type=FaultType.EEG_DROPOUT, duration_s=0.5),
        ScheduledFault(time_s=2.0, fault_type=FaultType.TARGET_LOSS, duration_s=0.5),
    ]
    
    injector = FaultInjector(seed=42, schedule=schedule)
    injector.start(0.0)
    
    # Time 0.5 - no faults
    faults = injector.update(0.5)
    assert len(faults) == 0
    
    # Time 1.2 - EEG dropout active
    faults = injector.update(1.2)
    assert FaultType.EEG_DROPOUT in faults
    assert len(faults) == 1
    
    # Time 1.6 - no faults (EEG dropout ended)
    faults = injector.update(1.6)
    assert len(faults) == 0
    
    # Time 2.3 - target loss active
    faults = injector.update(2.3)
    assert FaultType.TARGET_LOSS in faults
    assert len(faults) == 1


def test_same_seed_same_sequence():
    """Test same seed produces same fault sequence."""
    schedule = [
        ScheduledFault(time_s=1.0, fault_type=FaultType.EEG_DROPOUT, duration_s=1.0),
        ScheduledFault(time_s=3.0, fault_type=FaultType.TARGET_LOSS, duration_s=1.0),
    ]
    
    # Run 1
    injector1 = FaultInjector(seed=42, schedule=schedule)
    injector1.start(0.0)
    
    sequence1 = []
    for t in [0.5, 1.5, 2.5, 3.5]:
        faults = injector1.update(t)
        sequence1.append(sorted([str(f) for f in faults]))
    
    # Run 2 - same seed
    injector2 = FaultInjector(seed=42, schedule=schedule)
    injector2.start(0.0)
    
    sequence2 = []
    for t in [0.5, 1.5, 2.5, 3.5]:
        faults = injector2.update(t)
        sequence2.append(sorted([str(f) for f in faults]))
    
    # Should be identical
    assert sequence1 == sequence2


def test_different_seed_may_differ():
    """Test different seeds can produce different behavior."""
    # Note: With deterministic scheduling, seeds don't affect schedule
    # But they could affect randomized fault parameters in future
    
    injector1 = FaultInjector(seed=42, schedule=[])
    injector2 = FaultInjector(seed=99, schedule=[])
    
    # Seeds are different
    assert injector1.seed != injector2.seed


def test_fault_status_reporting():
    """Test fault injector status reporting."""
    schedule = [
        ScheduledFault(time_s=1.0, fault_type=FaultType.EEG_DROPOUT, duration_s=1.0),
        ScheduledFault(time_s=3.0, fault_type=FaultType.TARGET_LOSS, duration_s=1.0),
    ]
    
    injector = FaultInjector(seed=42, schedule=schedule)
    
    # Not enabled
    status = injector.get_status(0.0)
    assert status["enabled"] == False
    
    # Enable
    injector.start(0.0)
    
    # Check status at t=1.5 (EEG dropout active)
    status = injector.get_status(1.5)
    assert status["enabled"] == True
    assert status["seed"] == 42
    # active_faults contains string representations like "FaultType.EEG_DROPOUT"
    assert any("EEG_DROPOUT" in f for f in status["active_faults"])


def test_overlapping_faults():
    """Test multiple overlapping faults."""
    schedule = [
        ScheduledFault(time_s=1.0, fault_type=FaultType.EEG_DROPOUT, duration_s=2.0),
        ScheduledFault(time_s=1.5, fault_type=FaultType.TARGET_LOSS, duration_s=1.0),
    ]
    
    injector = FaultInjector(seed=42, schedule=schedule)
    injector.start(0.0)
    
    # Time 2.0 - both active
    faults = injector.update(2.0)
    assert FaultType.EEG_DROPOUT in faults
    assert FaultType.TARGET_LOSS in faults
    assert len(faults) == 2


def test_empty_schedule():
    """Test fault injector with empty schedule."""
    injector = FaultInjector(seed=42, schedule=[])
    injector.start(0.0)
    
    # Should have no faults at any time
    for t in range(10):
        faults = injector.update(float(t))
        assert len(faults) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

