"""
Authorization token system.

Every motor command traces back to a valid authorization token.
This formalizes false_executions == 0 as an auditable property:
  "Show me every primitive with no valid token → always zero"

Tokens are:
- Issued on user confirm
- Scoped (TASK_SESSION or SINGLE_OBJECT)
- Invalidated on completion, cancellation, or re-auth trigger
- Referenced by ID in every execution event
"""
import time
import uuid
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class AuthScope(Enum):
    """What the token authorizes"""
    TASK_SESSION = "task_session"     # Authorizes full multi-object session (A2)
    SINGLE_OBJECT = "single_object"  # Authorizes one object only (A1)


class TokenState(Enum):
    """Token lifecycle state"""
    ACTIVE = "active"
    COMPLETED = "completed"       # Task/object finished normally
    INVALIDATED = "invalidated"   # Re-auth triggered or cancelled
    EXPIRED = "expired"           # Future: time-based expiry


@dataclass(frozen=True)
class AuthorizationToken:
    """
    Immutable authorization token.
    
    Every execution event references token_id.
    Post-hoc audit: grep events for primitives with no matching active token.
    """
    token_id: str
    issued_at_ms: float
    scope: AuthScope
    source: str              # "keyboard", "eeg", "dual", "test"
    quality: float           # Decision quality at confirmation time
    autonomy_level: str      # Which autonomy mode issued this
    max_objects: int = 0     # 0 = unlimited (TASK_SESSION), 1 = single (SINGLE_OBJECT)
    metadata: dict = field(default_factory=dict)


class AuthorizationManager:
    """
    Issues, tracks, and invalidates authorization tokens.
    
    Invariants:
    - At most ONE active token at any time
    - Executor MUST check is_authorized() before any primitive
    - Token ID appears in every execution event log
    """
    
    def __init__(self):
        self._active_token: Optional[AuthorizationToken] = None
        self._token_state: TokenState = TokenState.COMPLETED
        
        # History (for audit)
        self._token_history: list = []
        self._objects_executed_under_token: int = 0
        
        # Metrics
        self.tokens_issued: int = 0
        self.tokens_invalidated: int = 0
        self.reauth_count: int = 0
    
    def issue(
        self,
        source: str,
        quality: float,
        scope: AuthScope,
        autonomy_level: str,
        max_objects: int = 0,
    ) -> AuthorizationToken:
        """
        Issue a new authorization token.
        
        Invalidates any existing active token first.
        Called by orchestrator on user confirm.
        """
        # Invalidate any existing token
        if self._active_token and self._token_state == TokenState.ACTIVE:
            self._invalidate_internal("superseded_by_new_token")
        
        token = AuthorizationToken(
            token_id=f"auth_{uuid.uuid4().hex[:12]}",
            issued_at_ms=time.time() * 1000,
            scope=scope,
            source=source,
            quality=quality,
            autonomy_level=autonomy_level,
            max_objects=max_objects,
        )
        
        self._active_token = token
        self._token_state = TokenState.ACTIVE
        self._objects_executed_under_token = 0
        self.tokens_issued += 1
        
        self._token_history.append({
            'token_id': token.token_id,
            'action': 'issued',
            'time_ms': token.issued_at_ms,
            'scope': token.scope.value,
            'source': source,
            'quality': quality,
        })
        
        logger.info(
            f"[AUTH] Token issued: {token.token_id} "
            f"(scope={token.scope.value}, source={source}, quality={quality:.2f})"
        )
        
        return token
    
    def is_authorized(self) -> bool:
        """Check if there is a valid active token"""
        if self._active_token is None:
            return False
        if self._token_state != TokenState.ACTIVE:
            return False
        
        # Check object limit for SINGLE_OBJECT scope
        # Note: We allow execution to continue for objects already started
        # This check prevents starting NEW objects beyond the limit
        if (self._active_token.scope == AuthScope.SINGLE_OBJECT
                and self._active_token.max_objects > 0
                and self._objects_executed_under_token >= self._active_token.max_objects):
            self._invalidate_internal("object_limit_reached")
            return False
        
        return True
    
    def get_active_token_id(self) -> Optional[str]:
        """Get active token ID for event logging (None if no active token)"""
        if self._active_token and self._token_state == TokenState.ACTIVE:
            return self._active_token.token_id
        return None
    
    def get_active_token(self) -> Optional[AuthorizationToken]:
        """Get full active token (for inspection)"""
        if self._token_state == TokenState.ACTIVE:
            return self._active_token
        return None
    
    def record_object_started(self):
        """Called when an object execution begins under current token"""
        self._objects_executed_under_token += 1
    
    def complete(self):
        """Mark token as completed (task/object finished normally)"""
        if self._active_token:
            self._token_state = TokenState.COMPLETED
            self._token_history.append({
                'token_id': self._active_token.token_id,
                'action': 'completed',
                'time_ms': time.time() * 1000,
                'objects_executed': self._objects_executed_under_token,
            })
            logger.info(
                f"[AUTH] Token completed: {self._active_token.token_id} "
                f"({self._objects_executed_under_token} objects)"
            )
    
    def invalidate(self, reason: str):
        """
        Invalidate active token (re-auth trigger, cancel, error).
        
        After invalidation, executor cannot proceed until new token is issued.
        """
        self._invalidate_internal(reason)
        self.tokens_invalidated += 1
    
    def invalidate_for_reauth(self, reason: str):
        """Invalidate specifically for re-authorization (tracked separately)"""
        self._invalidate_internal(f"reauth: {reason}")
        self.tokens_invalidated += 1
        self.reauth_count += 1
    
    def _invalidate_internal(self, reason: str):
        """Internal invalidation logic"""
        if self._active_token:
            self._token_state = TokenState.INVALIDATED
            self._token_history.append({
                'token_id': self._active_token.token_id,
                'action': 'invalidated',
                'time_ms': time.time() * 1000,
                'reason': reason,
            })
            logger.info(f"[AUTH] Token invalidated: {self._active_token.token_id} ({reason})")
    
    def get_audit_trail(self) -> list:
        """Return complete token history for replay/audit"""
        return list(self._token_history)
    
    def get_stats(self) -> dict:
        return {
            'tokens_issued': self.tokens_issued,
            'tokens_invalidated': self.tokens_invalidated,
            'reauth_count': self.reauth_count,
            'active_token_id': self.get_active_token_id(),
            'objects_under_current': self._objects_executed_under_token,
        }

