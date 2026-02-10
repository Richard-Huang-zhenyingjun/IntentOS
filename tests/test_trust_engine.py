"""
Test trust engine — deterministic trust from execution outcomes.
"""
import pytest
from src.core.trust import TrustEngine, PENALTY_VALUES, PenaltySeverity


@pytest.fixture
def config():
    return {
        'trust': {
            'init_task_trust': 1.0,
            'recovery_per_success': 0.03,
            'max_recovery_trust': 0.90,
            'reauth': {
                'enable': True,
                'task_trust_below': 0.55,
                'consecutive_failures': 2,
            },
        },
    }


def test_trust_starts_at_one(config):
    engine = TrustEngine(config)
    engine.start_session()
    assert engine.task_trust == 1.0


def test_trust_decreases_on_grasp_fail(config):
    engine = TrustEngine(config)
    engine.start_session()
    
    engine.record_primitive_result("grasp_fail", object_index=0)
    
    expected = 1.0 - PENALTY_VALUES[PenaltySeverity.SEVERE]
    assert abs(engine.task_trust - expected) < 0.001


def test_trust_decreases_deterministically(config):
    """Same inputs → same trust"""
    results = []
    for _ in range(3):
        engine = TrustEngine(config)
        engine.start_session()
        engine.record_primitive_result("primitive_timeout", object_index=0)
        engine.record_primitive_result("grasp_retry", object_index=0)
        results.append(engine.task_trust)
    
    assert results[0] == results[1] == results[2]


def test_trust_recovery_on_success(config):
    engine = TrustEngine(config)
    engine.start_session()
    
    # Decrease trust
    engine.record_primitive_result("grasp_fail", object_index=0)
    trust_after_fail = engine.task_trust
    
    # Recover on success
    engine.record_object_complete(success=True, object_index=0)
    
    assert engine.task_trust > trust_after_fail
    assert engine.task_trust <= 0.90  # Bounded by max_recovery


def test_trust_recovery_bounded(config):
    """Trust cannot recover above max_recovery_trust"""
    engine = TrustEngine(config)
    engine.start_session()
    
    # Apply penalty to bring trust below max_recovery_trust
    engine.record_primitive_result("grasp_fail", object_index=0)  # SEVERE: -0.22
    trust_before_recovery = engine.task_trust
    assert trust_before_recovery < 0.90  # Should be 0.78
    
    # Many successes - should recover but be bounded
    for i in range(20):
        engine.record_object_complete(success=True, object_index=i)
    
    assert engine.task_trust <= 0.90
    assert engine.task_trust > trust_before_recovery  # Should have recovered some


def test_reauth_trigger_on_low_trust(config):
    engine = TrustEngine(config)
    engine.start_session()
    
    # Three severe failures → trust should drop below 0.55
    # Two severe: 1.0 - 0.22 - 0.22 = 0.56 (just above threshold)
    # Three severe: 1.0 - 0.22 - 0.22 - 0.22 = 0.34 (below threshold)
    engine.record_primitive_result("grasp_fail", object_index=0)
    engine.record_primitive_result("object_timeout", object_index=0)
    engine.record_primitive_result("grasp_fail", object_index=0)
    
    reason = engine.should_reauth()
    assert reason is not None
    assert "trust_below" in reason


def test_reauth_trigger_on_consecutive_failures(config):
    engine = TrustEngine(config)
    engine.start_session()
    
    # Two consecutive object failures
    engine.record_object_complete(success=False, object_index=0)
    engine.record_object_complete(success=False, object_index=1)
    
    reason = engine.should_reauth()
    assert reason is not None
    assert "consecutive_failures" in reason


def test_no_reauth_after_recovery(config):
    engine = TrustEngine(config)
    engine.start_session()
    
    # One failure, then success
    engine.record_object_complete(success=False, object_index=0)
    engine.record_object_complete(success=True, object_index=1)
    
    # Consecutive failures reset on success
    assert engine.consecutive_failures == 0
    reason = engine.should_reauth()
    # May or may not trigger based on trust level, but consecutive failures won't trigger
    if reason:
        assert "consecutive" not in reason


def test_low_quality_auth_starts_lower_trust(config):
    engine = TrustEngine(config)
    engine.start_session(auth_quality=0.5)
    
    # 0.6 + 0.4 * 0.5 = 0.8 modifier → trust starts at 0.8
    assert engine.task_trust < 1.0
    assert engine.task_trust == pytest.approx(0.8, abs=0.01)

