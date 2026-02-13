"""
Test autonomy modes — A1 micro-confirm vs A2 task-confirm.
"""
import pytest
from src.core.authorization import AuthorizationManager, AuthScope
from src.core.autonomy import AutonomyLevel, AutonomyPolicy


def test_a2_authorizes_multiple_objects():
    """A2 task-confirm: one token covers entire session"""
    mgr = AuthorizationManager()
    mgr.issue(
        source="keyboard", quality=1.0,
        scope=AuthScope.TASK_SESSION, autonomy_level="A2",
        max_objects=0,
    )
    
    # Execute 5 objects under same token
    for _ in range(5):
        assert mgr.is_authorized()
        mgr.record_object_started()
    
    assert mgr.is_authorized()  # Still valid


def test_a1_requires_confirm_per_object():
    """A1 micro-confirm: token exhausts after one object"""
    mgr = AuthorizationManager()
    mgr.issue(
        source="keyboard", quality=1.0,
        scope=AuthScope.SINGLE_OBJECT, autonomy_level="A1",
        max_objects=1,
    )
    
    assert mgr.is_authorized()
    mgr.record_object_started()  # First object
    assert not mgr.is_authorized()  # Exhausted — need new confirm


def test_a1_needs_reissue_for_next_object():
    """A1: new token needed for each object"""
    mgr = AuthorizationManager()
    
    # Object 1
    t1 = mgr.issue(source="keyboard", quality=1.0,
                   scope=AuthScope.SINGLE_OBJECT, autonomy_level="A1", max_objects=1)
    mgr.record_object_started()
    assert not mgr.is_authorized()
    
    # Object 2 — new token
    t2 = mgr.issue(source="keyboard", quality=1.0,
                   scope=AuthScope.SINGLE_OBJECT, autonomy_level="A1", max_objects=1)
    assert mgr.is_authorized()
    assert t1.token_id != t2.token_id


def test_autonomy_policy_from_config():
    config = {
        'autonomy': {
            'level': 'A1_MICRO_CONFIRM',
            'allow_auto_decrease': True,
            'decrease_on': {'trust_below': 0.55, 'consecutive_failures': 2},
        },
    }
    
    policy = AutonomyPolicy.from_config(config)
    assert policy.level == AutonomyLevel.A1_MICRO_CONFIRM
    assert policy.get_token_scope() == AuthScope.SINGLE_OBJECT
    assert policy.get_max_objects() == 1



