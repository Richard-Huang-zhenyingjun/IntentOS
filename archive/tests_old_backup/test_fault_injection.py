"""
Tests for Fault Injection System (Week 8)

Validates deterministic fault injection for stress testing.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from sim.fault_injection import (
    FaultInjector,
    FaultType,
    InjectedFault,
    create_test_fault_schedule,
    create_stress_test_schedule,
    create_undo_stress_schedule
)


class TestFaultInjector:
    """Test fault injection mechanics"""
    
    def test_fault_injector_disabled_by_default(self):
        """Fault injector should be disabled by default"""
        config = {}
        injector = FaultInjector(config, seed=42)
        
        assert injector.enabled is False
        
        # No effects when disabled
        effects = injector.inject(1.0)
        assert effects == {}
    
    def test_fault_injector_enabled(self):
        """Fault injector should be enabled when configured"""
        config = {'enabled': True}
        injector = FaultInjector(config, seed=42)
        
        assert injector.enabled is True
    
    def test_schedule_fault_programmatically(self):
        """Should be able to schedule faults programmatically"""
        config = {'enabled': True}
        injector = FaultInjector(config, seed=42)
        
        # Schedule hand dropout
        injector.schedule_fault(
            fault_type=FaultType.HAND_DROPOUT,
            start_time=5.0,
            duration=2.0,
            parameters={}
        )
        
        assert len(injector.fault_schedule) == 1
        assert injector.fault_schedule[0]['type'] == FaultType.HAND_DROPOUT.value
        assert injector.fault_schedule[0]['start_time'] == 5.0
    
    def test_fault_activation_at_scheduled_time(self):
        """Fault should activate at scheduled time"""
        config = {'enabled': True}
        injector = FaultInjector(config, seed=42)
        
        injector.schedule_fault(
            fault_type=FaultType.HAND_DROPOUT,
            start_time=5.0,
            duration=2.0
        )
        
        # Before start time - no effect
        effects = injector.inject(4.9)
        assert 'hand_dropout' not in effects
        assert len(injector.active_faults) == 0
        
        # At start time - fault activates
        effects = injector.inject(5.0)
        assert effects.get('hand_dropout') is True
        assert len(injector.active_faults) == 1
        
        # During fault - still active
        effects = injector.inject(6.0)
        assert effects.get('hand_dropout') is True
        assert len(injector.active_faults) == 1
        
        # After end time - fault expires
        effects = injector.inject(7.5)
        assert 'hand_dropout' not in effects
        assert len(injector.active_faults) == 0
        assert len(injector.completed_faults) == 1
    
    def test_hand_dropout_effects(self):
        """Hand dropout should provide correct effects"""
        config = {'enabled': True}
        injector = FaultInjector(config, seed=42)
        
        injector.schedule_fault(
            fault_type=FaultType.HAND_DROPOUT,
            start_time=1.0,
            duration=1.0
        )
        
        effects = injector.inject(1.0)
        
        assert effects.get('hand_dropout') is True
        assert effects.get('hand_detection_override') is None
    
    def test_object_loss_effects(self):
        """Object loss should provide correct effects"""
        config = {'enabled': True}
        injector = FaultInjector(config, seed=42)
        
        injector.schedule_fault(
            fault_type=FaultType.OBJECT_LOSS,
            start_time=1.0,
            duration=1.0,
            parameters={'object_id': 'track_001'}
        )
        
        effects = injector.inject(1.0)
        
        assert effects.get('object_loss') is True
        assert effects.get('object_id_to_remove') == 'track_001'
    
    def test_confidence_collapse_effects(self):
        """Confidence collapse should provide correct effects"""
        config = {'enabled': True}
        injector = FaultInjector(config, seed=42)
        
        injector.schedule_fault(
            fault_type=FaultType.CONFIDENCE_COLLAPSE,
            start_time=1.0,
            duration=1.0,
            parameters={'multiplier': 0.3}
        )
        
        effects = injector.inject(1.0)
        
        assert effects.get('confidence_collapse') is True
        assert effects.get('confidence_multiplier') == 0.3
    
    def test_ambiguity_burst_effects(self):
        """Ambiguity burst should provide correct effects"""
        config = {'enabled': True}
        injector = FaultInjector(config, seed=42)
        
        injector.schedule_fault(
            fault_type=FaultType.AMBIGUITY_BURST,
            start_time=1.0,
            duration=1.0,
            parameters={'competitor': 'track_999'}
        )
        
        effects = injector.inject(1.0)
        
        assert effects.get('ambiguity_burst') is True
        assert effects.get('inject_competitor_object') == 'track_999'
    
    def test_oscillation_burst_effects(self):
        """Oscillation burst should provide correct effects"""
        config = {'enabled': True}
        injector = FaultInjector(config, seed=42)
        
        injector.schedule_fault(
            fault_type=FaultType.OSCILLATION_BURST,
            start_time=1.0,
            duration=1.0,
            parameters={'pattern': ['A', 'B', 'C']}
        )
        
        effects = injector.inject(1.0)
        
        assert effects.get('oscillation_burst') is True
        assert effects.get('oscillation_pattern') == ['A', 'B', 'C']
    
    def test_state_uncertainty_effects(self):
        """State uncertainty should provide correct effects"""
        config = {'enabled': True}
        injector = FaultInjector(config, seed=42)
        
        injector.schedule_fault(
            fault_type=FaultType.STATE_UNCERTAINTY,
            start_time=1.0,
            duration=1.0,
            parameters={'confidence': 0.2}
        )
        
        effects = injector.inject(1.0)
        
        assert effects.get('state_uncertainty') is True
        assert effects.get('state_confidence_override') == 0.2
    
    def test_multiple_overlapping_faults(self):
        """Multiple faults can be active simultaneously"""
        config = {'enabled': True}
        injector = FaultInjector(config, seed=42)
        
        # Schedule overlapping faults
        injector.schedule_fault(
            fault_type=FaultType.HAND_DROPOUT,
            start_time=1.0,
            duration=3.0
        )
        injector.schedule_fault(
            fault_type=FaultType.CONFIDENCE_COLLAPSE,
            start_time=2.0,
            duration=2.0,
            parameters={'multiplier': 0.3}
        )
        
        # At 2.5s - both should be active
        effects = injector.inject(2.5)
        
        assert effects.get('hand_dropout') is True
        assert effects.get('confidence_collapse') is True
        assert len(injector.active_faults) == 2
    
    def test_is_active_method(self):
        """is_active() should correctly report active fault types"""
        config = {'enabled': True}
        injector = FaultInjector(config, seed=42)
        
        injector.schedule_fault(
            fault_type=FaultType.HAND_DROPOUT,
            start_time=1.0,
            duration=1.0
        )
        
        # Before activation
        assert not injector.is_active(FaultType.HAND_DROPOUT)
        
        # During activation
        injector.inject(1.0)
        assert injector.is_active(FaultType.HAND_DROPOUT)
        assert not injector.is_active(FaultType.OBJECT_LOSS)
        
        # After expiration
        injector.inject(3.0)
        assert not injector.is_active(FaultType.HAND_DROPOUT)
    
    def test_clear_schedule(self):
        """clear_schedule() should reset all faults"""
        config = {'enabled': True}
        injector = FaultInjector(config, seed=42)
        
        injector.schedule_fault(
            fault_type=FaultType.HAND_DROPOUT,
            start_time=1.0,
            duration=1.0
        )
        
        injector.inject(1.0)  # Activate fault
        
        assert len(injector.fault_schedule) > 0
        assert len(injector.active_faults) > 0
        
        injector.clear_schedule()
        
        assert len(injector.fault_schedule) == 0
        assert len(injector.active_faults) == 0
        assert len(injector.completed_faults) == 0
    
    def test_statistics(self):
        """get_statistics() should provide accurate stats"""
        config = {'enabled': True}
        injector = FaultInjector(config, seed=42)
        
        # Schedule and execute faults
        injector.schedule_fault(FaultType.HAND_DROPOUT, 1.0, 1.0)
        injector.schedule_fault(FaultType.OBJECT_LOSS, 2.0, 1.0)
        injector.schedule_fault(FaultType.HAND_DROPOUT, 3.0, 1.0)
        
        injector.inject(1.0)  # Activate first
        injector.inject(2.0)  # Activate second, first expires
        injector.inject(3.0)  # Activate third, second expires
        injector.inject(5.0)  # All expire
        
        stats = injector.get_statistics()
        
        assert stats['total_faults_injected'] == 3
        assert stats['active_faults'] == 0
        assert stats['completed_faults'] == 3
        assert stats['fault_types_used']['hand_dropout'] == 2
        assert stats['fault_types_used']['object_loss'] == 1


class TestPredefinedSchedules:
    """Test predefined fault schedules"""
    
    def test_create_test_fault_schedule(self):
        """Test schedule should have expected faults"""
        schedule = create_test_fault_schedule()
        
        assert len(schedule) == 4
        
        # Verify structure
        for fault in schedule:
            assert 'type' in fault
            assert 'start_time' in fault
            assert 'duration' in fault
            assert 'parameters' in fault
        
        # Verify timing
        assert schedule[0]['start_time'] == 5.0  # Hand dropout
        assert schedule[1]['start_time'] == 10.0  # Object loss
        assert schedule[2]['start_time'] == 15.0  # Confidence collapse
        assert schedule[3]['start_time'] == 20.0  # Ambiguity burst
    
    def test_create_stress_test_schedule(self):
        """Stress test schedule should have many overlapping faults"""
        schedule = create_stress_test_schedule()
        
        assert len(schedule) >= 8  # Many faults
        
        # Verify overlapping faults exist
        times = [f['start_time'] for f in schedule]
        assert len(times) == len(schedule)
        
        # Should have tight timing (overlaps)
        min_gap = min(times[i+1] - times[i] for i in range(len(times) - 1))
        assert min_gap <= 2.0  # At least some faults are close together
    
    def test_create_undo_stress_schedule(self):
        """Undo stress schedule should target undo scenarios"""
        schedule = create_undo_stress_schedule()
        
        assert len(schedule) == 3
        
        # All should be timed around typical action/undo sequence
        assert all(f['start_time'] < 10.0 for f in schedule)


class TestFaultInjectionIntegration:
    """Test fault injection with system integration"""
    
    def test_fault_injection_deterministic(self):
        """Same seed should produce same fault sequence"""
        config = {
            'enabled': True,
            'fault_schedule': create_test_fault_schedule()
        }
        
        injector1 = FaultInjector(config, seed=42)
        injector2 = FaultInjector(config, seed=42)
        
        # Run through same timestamps
        for t in [5.0, 10.0, 15.0, 20.0]:
            effects1 = injector1.inject(t)
            effects2 = injector2.inject(t)
            
            assert effects1 == effects2
    
    def test_fault_injection_with_real_schedule(self):
        """Run through complete test schedule"""
        config = {
            'enabled': True,
            'fault_schedule': create_test_fault_schedule()
        }
        
        injector = FaultInjector(config, seed=42)
        
        timeline = []
        
        # Simulate 25 seconds at 10 Hz
        for i in range(250):
            t = i * 0.1
            effects = injector.inject(t)
            
            if effects:
                timeline.append((t, list(effects.keys())))
        
        # Should have multiple fault activations
        assert len(timeline) > 0
        
        # Verify expected faults activated
        all_effects = set()
        for _, effects in timeline:
            all_effects.update(effects)
        
        assert 'hand_dropout' in all_effects
        assert 'object_loss' in all_effects
        assert 'confidence_collapse' in all_effects
        assert 'ambiguity_burst' in all_effects


if __name__ == '__main__':
    pytest.main([__file__, '-v'])




