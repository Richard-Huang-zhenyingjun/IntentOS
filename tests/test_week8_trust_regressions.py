"""
Week 8: Trust Regressions - Critical Safety Invariants.

Tests the paper's "shared control requires trust" principle:
- False executions MUST always be 0
- Every pause has an explanation
- No auto-resume (explicit user re-engagement required)
- Trust metrics accurately track safety guarantees
"""

import pytest
import yaml
import time

from intent_core import ArmOrchestrator, ArmTrustMetrics
from robotics import ArmSimulator
from robotics.recovery import PauseTrigger, RecoveryPlan, ArmRecoveryController
from world import WorldModel
from perception import TargetSelector
from sim import FaultInjector, FaultType, ScheduledFault


@pytest.fixture
def config():
    """Load robotics configuration."""
    with open('configs/robotics.yaml', 'r') as f:
        return yaml.safe_load(f)


@pytest.fixture
def sim(config):
    """Create simulator instance."""
    simulator = ArmSimulator(cfg_path='configs/robotics.yaml')
    simulator.connect()
    simulator.reset_world()
    yield simulator
    simulator.close()


@pytest.fixture
def orchestrator_env(config, sim):
    """Create orchestrator with all dependencies."""
    world = WorldModel(config)
    selector = TargetSelector(sim, config)
    orchestrator = ArmOrchestrator(config, use_eeg=False)
    
    yield orchestrator, world, selector, sim
    
    orchestrator.close()


def test_false_executions_always_zero(orchestrator_env):
    """
    CRITICAL SAFETY TEST
    
    Trust metrics must never record false executions.
    Every execution must be confirmed by user.
    """
    orch, world, selector, sim = orchestrator_env
    
    # Run multiple steps without any confirmations
    for _ in range(50):
        snapshot = orch.step(sim, world, selector)
        sim.step(n=1)
    
    # Check trust metrics
    metrics = orch.trust_metrics.get_summary()
    
    # CRITICAL: false_executions MUST be 0
    assert metrics['false_executions'] == 0, \
        "🚨 CRITICAL VIOLATION: False executions detected!"
    
    print("✓ False executions = 0 (safety guarantee maintained)")


def test_pause_always_has_explanation(config):
    """
    CRITICAL: Every pause must have human-readable explanation.
    
    Paper requirement: "every refusal explained"
    """
    # Test all pause triggers have explanations
    triggers = [
        PauseTrigger.EEG_UNSTABLE,
        PauseTrigger.TARGET_LOST,
        PauseTrigger.ACTION_TIMEOUT,
        PauseTrigger.CANCEL_REQUESTED,
    ]
    
    for trigger in triggers:
        plan = RecoveryPlan.create(trigger)
        
        assert plan.should_pause is True
        assert plan.explanation is not None
        assert len(plan.explanation) > 0
        assert plan.required_steps is not None
        assert len(plan.required_steps) > 0
        
        print(f"✓ {trigger.value}: '{plan.explanation}'")


def test_no_auto_resume_from_pause(config, sim):
    """
    CRITICAL: System must never auto-resume from PAUSED state.
    
    Requires explicit user re-engagement (target re-selection).
    """
    world = WorldModel(config)
    selector = TargetSelector(sim, config)
    
    # Create orchestrator with fault injector that triggers immediate pause
    fault_injector = FaultInjector(seed=42, schedule=[
        ScheduledFault(time_s=0.0, fault_type=FaultType.EEG_DROPOUT, duration_s=2.0)
    ])
    fault_injector.start(time.time())
    
    orch = ArmOrchestrator(config, use_eeg=False, fault_injector=fault_injector)
    
    # Run initial step to trigger pause
    for _ in range(5):
        snapshot = orch.step(sim, world, selector)
        sim.step(n=1)
    
    # Count paused states
    paused_count = 0
    for _ in range(50):
        snapshot = orch.step(sim, world, selector)
        if snapshot['state'] == 'paused' or snapshot.get('recovery', {}).get('paused', False):
            paused_count += 1
        sim.step(n=1)
    
    # Should remain paused for significant duration (no auto-resume)
    assert paused_count > 20, \
        f"System may have auto-resumed (only paused {paused_count}/50 steps)"
    
    print(f"✓ Remained paused for {paused_count}/50 steps (no auto-resume)")
    
    orch.close()


def test_trust_metrics_accurate_tracking(orchestrator_env):
    """
    Test that trust metrics accurately track all safety events.
    """
    orch, world, selector, sim = orchestrator_env
    
    initial_metrics = orch.trust_metrics.get_summary()
    
    # Simulate some blocked confirmations
    orch.trust_metrics.record_blocked_unstable()
    orch.trust_metrics.record_blocked_unstable()
    
    # Simulate a pause
    orch.trust_metrics.record_pause("target_lost")
    
    # Simulate an undo
    orch.trust_metrics.record_undo()
    
    final_metrics = orch.trust_metrics.get_summary()
    
    assert final_metrics['blocked_unstable'] == initial_metrics['blocked_unstable'] + 2
    assert final_metrics['pauses_triggered'] == initial_metrics['pauses_triggered'] + 1
    assert final_metrics['undos_performed'] == initial_metrics['undos_performed'] + 1
    assert 'target_lost' in final_metrics['pauses_by_trigger']
    
    print("✓ Trust metrics accurately track all events")


def test_recovery_plan_completeness(config):
    """
    Test that recovery plans provide complete information.
    """
    recovery_controller = ArmRecoveryController(config)
    
    # Create recovery plans for different triggers
    triggers = [PauseTrigger.EEG_UNSTABLE, PauseTrigger.TARGET_LOST]
    
    for trigger in triggers:
        plan = RecoveryPlan.create(trigger)
        
        # Check completeness
        assert plan.trigger is not None
        assert plan.explanation is not None and len(plan.explanation) > 0
        assert plan.required_steps is not None and len(plan.required_steps) > 0
        
        print(f"✓ {trigger.value} recovery plan is complete")


def test_fault_injection_respects_safety(config, sim):
    """
    Fault injection must not violate safety guarantees.
    
    Even with injected faults, false_executions must remain 0.
    """
    world = WorldModel(config)
    selector = TargetSelector(sim, config)
    
    # Create fault injector with multiple faults
    fault_injector = FaultInjector(seed=42, schedule=[
        ScheduledFault(time_s=0.1, fault_type=FaultType.EEG_DROPOUT, duration_s=0.5),
        ScheduledFault(time_s=0.5, fault_type=FaultType.TARGET_LOSS, duration_s=0.3),
    ])
    start_time = time.time()
    fault_injector.start(start_time)
    
    orch = ArmOrchestrator(config, use_eeg=False, fault_injector=fault_injector)
    
    # Run with fault injection
    for i in range(50):
        snapshot = orch.step(sim, world, selector)
        sim.step(n=1)
        
        # Check active faults
        active_faults = snapshot.get('active_faults', [])
        if active_faults:
            print(f"  Frame {i}: Active faults: {active_faults}")
    
    # Verify safety guarantee maintained
    metrics = orch.trust_metrics.get_summary()
    assert metrics['false_executions'] == 0, \
        "Fault injection caused false executions!"
    
    print("✓ Safety maintained despite fault injection")
    
    orch.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
