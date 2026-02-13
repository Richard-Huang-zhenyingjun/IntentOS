"""
Test authorization token system.
CRITICAL: No primitive should ever execute without a valid token.
"""
import pytest
from src.core.authorization import AuthorizationManager, AuthScope, TokenState


def test_no_authorization_without_token():
    """Manager reports unauthorized before any token issued"""
    mgr = AuthorizationManager()
    assert not mgr.is_authorized()
    assert mgr.get_active_token_id() is None


def test_issue_token_authorizes():
    """Issuing a token enables authorization"""
    mgr = AuthorizationManager()
    token = mgr.issue(
        source="keyboard", quality=1.0,
        scope=AuthScope.TASK_SESSION, autonomy_level="A2",
    )
    
    assert mgr.is_authorized()
    assert mgr.get_active_token_id() == token.token_id
    assert token.scope == AuthScope.TASK_SESSION


def test_invalidation_removes_authorization():
    """Invalidating token prevents further execution"""
    mgr = AuthorizationManager()
    mgr.issue(source="keyboard", quality=1.0,
              scope=AuthScope.TASK_SESSION, autonomy_level="A2")
    
    assert mgr.is_authorized()
    mgr.invalidate("test_reason")
    assert not mgr.is_authorized()


def test_completion_removes_authorization():
    """Completing token prevents further execution"""
    mgr = AuthorizationManager()
    mgr.issue(source="keyboard", quality=1.0,
              scope=AuthScope.TASK_SESSION, autonomy_level="A2")
    
    mgr.complete()
    assert not mgr.is_authorized()


def test_single_object_token_exhausts_after_one():
    """SINGLE_OBJECT scope token invalidates after one object"""
    mgr = AuthorizationManager()
    mgr.issue(
        source="keyboard", quality=1.0,
        scope=AuthScope.SINGLE_OBJECT, autonomy_level="A1",
        max_objects=1,
    )
    
    assert mgr.is_authorized()
    mgr.record_object_started()
    assert not mgr.is_authorized()  # Exhausted


def test_new_token_supersedes_old():
    """Issuing a new token invalidates the previous one"""
    mgr = AuthorizationManager()
    token1 = mgr.issue(source="keyboard", quality=1.0,
                       scope=AuthScope.TASK_SESSION, autonomy_level="A2")
    token2 = mgr.issue(source="eeg", quality=0.8,
                       scope=AuthScope.TASK_SESSION, autonomy_level="A2")
    
    assert mgr.get_active_token_id() == token2.token_id
    assert token1.token_id != token2.token_id


def test_audit_trail_records_all_actions():
    """Audit trail captures issue, complete, invalidate"""
    mgr = AuthorizationManager()
    
    mgr.issue(source="keyboard", quality=1.0,
              scope=AuthScope.TASK_SESSION, autonomy_level="A2")
    mgr.complete()
    mgr.issue(source="eeg", quality=0.7,
              scope=AuthScope.SINGLE_OBJECT, autonomy_level="A1", max_objects=1)
    mgr.invalidate("trust_drop")
    
    trail = mgr.get_audit_trail()
    actions = [entry['action'] for entry in trail]
    
    assert actions == ['issued', 'completed', 'issued', 'invalidated']
    assert mgr.tokens_issued == 2
    assert mgr.tokens_invalidated == 1


def test_reauth_tracking():
    """Re-auth invalidation is tracked separately"""
    mgr = AuthorizationManager()
    mgr.issue(source="keyboard", quality=1.0,
              scope=AuthScope.TASK_SESSION, autonomy_level="A2")
    
    mgr.invalidate_for_reauth("trust_below_threshold")
    
    assert mgr.reauth_count == 1
    assert not mgr.is_authorized()



