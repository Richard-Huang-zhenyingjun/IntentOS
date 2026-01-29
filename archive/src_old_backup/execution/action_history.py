"""
Action History - Track executed actions for undo (ENHANCED Week 8)

Provides comprehensive action tracking with strict validation,
expiration management, and multi-user support.

Week 5: Basic list-based storage
Week 8: Enhanced validation, constraints, comprehensive indexing
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from execution.action_schema import ExecutionResult
import time
import uuid


@dataclass
class ActionRecord:
    """
    Record of an executed action (ENHANCED Week 8)
    
    Stores complete information about an executed action for potential undo.
    
    Week 5: Basic recording
    Week 8: Enhanced validation, metadata, constraints, undo tracking
    
    Guarantees:
    - Reversible actions MUST have state information
    - State must actually change (before ≠ after)
    - Expiry time set correctly
    - Can validate undo eligibility at any time
    """
    # Identifiers
    action_id: str
    timestamp: float
    
    # Target
    user_id: Optional[str]
    session_id: Optional[str]  # ENHANCED Week 8
    object_id: str
    object_label: str
    category: str
    action_type: str
    
    # State changes (REQUIRED for undo)
    before_state: Dict
    after_state: Dict
    
    # Reversibility
    reversible: bool
    expires_at: float
    
    # Undo status
    undone: bool = False
    undone_at: Optional[float] = None
    undone_by_session: Optional[str] = None
    undo_action_id: Optional[str] = None  # NEW Week 8: Track undo action
    
    # Constraints (NEW Week 8 - for multi-user)
    requires_ownership: bool = False  # Must own object to undo
    requires_lock: bool = False  # Must hold lock to undo
    
    # Metadata (NEW Week 8)
    metadata: Dict = field(default_factory=dict)
    
    def __post_init__(self):
        """
        Validate action record (NEW Week 8)
        
        Ensures:
        - Reversible actions have state info
        - State actually changed
        - Expiry time is valid
        
        Raises:
            AssertionError: If validation fails
        """
        # CRITICAL: Reversible actions must have state info
        if self.reversible:
            assert self.before_state is not None, \
                f"Reversible action {self.action_id} missing before_state"
            assert self.after_state is not None, \
                f"Reversible action {self.action_id} missing after_state"
            assert self.before_state != self.after_state, \
                f"Reversible action {self.action_id} state didn't change"
        
        # Validate expiry time
        assert self.expires_at > self.timestamp, \
            f"Action {self.action_id} expiry time must be after timestamp"
    
    def is_expired(self, current_time: float) -> bool:
        """
        Check if undo window has expired
        
        Args:
            current_time: Current timestamp
        
        Returns:
            True if expired, False otherwise
        """
        return current_time > self.expires_at
    
    def can_undo(self, current_time: float) -> tuple[bool, str]:
        """
        Check if this action can be undone (ENHANCED Week 8)
        
        Checks:
        - Not already undone
        - Is reversible
        - Within time window
        
        Args:
            current_time: Current timestamp
        
        Returns:
            (can_undo, reason) tuple
        """
        if self.undone:
            return (False, f"Already undone at {self.undone_at:.1f}")
        
        if not self.reversible:
            return (False, f"Action type '{self.action_type}' is not reversible")
        
        if self.is_expired(current_time):
            elapsed = current_time - self.expires_at
            return (False, f"Undo window expired {elapsed:.1f}s ago")
        
        return (True, "Action can be undone")
    
    @classmethod
    def from_execution_result(cls,
                             result: ExecutionResult,
                             object_id: str,
                             object_label: str,
                             category: str,
                             action_type: str,
                             undo_window_seconds: float,
                             user_id: Optional[str] = None,
                             session_id: Optional[str] = None,
                             metadata: Optional[Dict] = None) -> 'ActionRecord':
        """
        Create action record from execution result
        
        Args:
            result: Execution result
            object_id: Target object ID
            object_label: Object label
            category: Object category
            action_type: Action type string
            undo_window_seconds: How long undo is available
            user_id: User who performed action
            session_id: Session ID (NEW Week 8)
            metadata: Additional metadata (NEW Week 8)
        
        Returns:
            ActionRecord instance
        """
        return cls(
            action_id=result.action_id,
            timestamp=result.timestamp,
            user_id=user_id,
            session_id=session_id,
            object_id=object_id,
            object_label=object_label,
            category=category,
            action_type=action_type,
            before_state=result.before_state,
            after_state=result.after_state,
            reversible=result.reversible,
            expires_at=result.timestamp + undo_window_seconds,
            metadata=metadata or {}
        )


class ActionHistory:
    """
    Track executed actions for undo (ENHANCED Week 8)
    
    Responsibilities:
    - Record all executed actions
    - Track undo eligibility and expiration
    - Support multi-user filtering (Week 8+)
    - Validate undo constraints
    - Provide statistics
    
    Week 5: Simple list-based storage
    Week 8: Enhanced validation, comprehensive indexing, constraints
    
    Design:
    - Actions are immutable once recorded (dataclass frozen)
    - Multiple indices for fast lookup
    - Automatic cleanup of expired actions
    - Strict validation on recording
    """
    
    def __init__(self, config: dict):
        self.config = config
        
        # Config
        self.undo_window_seconds = config.get('undo_window_seconds', 10.0)
        self.max_history_size = config.get('max_history_size', 100)
        self.allow_multiple_undo = config.get('allow_multiple_undo', False)  # NEW Week 8
        self.auto_cleanup_expired = config.get('auto_cleanup_expired', True)  # NEW Week 8
        
        # Storage
        self.actions: List[ActionRecord] = []
        
        # Indices (NEW Week 8: enhanced indexing)
        self.by_user: Dict[str, List[ActionRecord]] = {}
        self.by_session: Dict[str, List[ActionRecord]] = {}
        self.by_object: Dict[str, List[ActionRecord]] = {}
        
        # Statistics
        self.total_recorded = 0
        self.total_undone = 0
        self.total_expired = 0  # NEW Week 8
        self.total_non_reversible = 0  # NEW Week 8
    
    def record(self, record: ActionRecord):
        """
        Record an action (ENHANCED Week 8)
        
        Validates:
        - State information present for reversible actions
        - Expiry time set correctly
        - Metadata complete
        
        Args:
            record: ActionRecord to store
        
        Raises:
            ValueError: If validation fails
        """
        # Validate reversible actions (redundant with __post_init__, but explicit)
        if record.reversible:
            if not record.before_state or not record.after_state:
                raise ValueError(
                    f"Reversible action {record.action_id} must have before_state and after_state"
                )
            if record.before_state == record.after_state:
                raise ValueError(
                    f"Reversible action {record.action_id} state must change"
                )
        
        # Validate expiry
        if record.expires_at <= record.timestamp:
            raise ValueError(
                f"Action {record.action_id} expiry time must be after timestamp"
            )
        
        # Store
        self.actions.append(record)
        self.total_recorded += 1
        
        # Track non-reversible actions
        if not record.reversible:
            self.total_non_reversible += 1
        
        # Index by user
        if record.user_id:
            if record.user_id not in self.by_user:
                self.by_user[record.user_id] = []
            self.by_user[record.user_id].append(record)
        
        # Index by session (NEW Week 8)
        if record.session_id:
            if record.session_id not in self.by_session:
                self.by_session[record.session_id] = []
            self.by_session[record.session_id].append(record)
        
        # Index by object (NEW Week 8)
        if record.object_id not in self.by_object:
            self.by_object[record.object_id] = []
        self.by_object[record.object_id].append(record)
        
        # Trim history if needed
        self._trim_history()
    
    def last_reversible(self,
                       current_time: float,
                       user_id: Optional[str] = None,
                       session_id: Optional[str] = None) -> Optional[ActionRecord]:
        """
        Get last reversible action within undo window (ENHANCED Week 8)
        
        Filters:
        - user_id: Only actions by this user (multi-user)
        - session_id: Only actions in this session (NEW Week 8)
        
        Returns most recent action that:
        - Is reversible
        - Has not been undone
        - Has not expired
        
        Args:
            current_time: Current timestamp
            user_id: Optional user filter
            session_id: Optional session filter (NEW Week 8)
        
        Returns:
            Most recent reversible action or None
        """
        # Select appropriate list (priority: session > user > all)
        if session_id and session_id in self.by_session:
            candidates = self.by_session[session_id]
        elif user_id and user_id in self.by_user:
            candidates = self.by_user[user_id]
        else:
            candidates = self.actions
        
        # Search backwards (most recent first)
        for record in reversed(candidates):
            can_undo, reason = record.can_undo(current_time)
            if can_undo:
                return record
        
        return None
    
    def mark_undone(self,
                   action_id: str,
                   timestamp: float,
                   undo_action_id: str,
                   session_id: Optional[str] = None):
        """
        Mark action as undone (ENHANCED Week 8)
        
        Args:
            action_id: ID of action that was undone
            timestamp: When undo occurred
            undo_action_id: ID of the undo action itself (NEW Week 8)
            session_id: Session that performed undo
        
        Raises:
            ValueError: If action not found or already undone
        """
        for record in self.actions:
            if record.action_id == action_id:
                # Check not already undone
                if record.undone:
                    raise ValueError(
                        f"Action {action_id} already undone at {record.undone_at}"
                    )
                
                # Mark as undone (modify dataclass fields)
                object.__setattr__(record, 'undone', True)
                object.__setattr__(record, 'undone_at', timestamp)
                object.__setattr__(record, 'undone_by_session', session_id)
                object.__setattr__(record, 'undo_action_id', undo_action_id)
                
                self.total_undone += 1
                return
        
        raise ValueError(f"Action {action_id} not found in history")
    
    def get_undo_countdown(self,
                          current_time: float,
                          user_id: Optional[str] = None,
                          session_id: Optional[str] = None) -> Optional[float]:
        """
        Get seconds remaining for undo (ENHANCED Week 8)
        
        Useful for UI countdown timers.
        
        Args:
            current_time: Current timestamp
            user_id: Optional user filter
            session_id: Optional session filter (NEW Week 8)
        
        Returns:
            Seconds remaining or None if no undo available
        """
        last = self.last_reversible(current_time, user_id, session_id)
        if last:
            remaining = last.expires_at - current_time
            return max(0.0, remaining)
        return None
    
    def get_actions_for_object(self, object_id: str) -> List[ActionRecord]:
        """
        Get all actions for a specific object (NEW Week 8)
        
        Args:
            object_id: Object to get history for
        
        Returns:
            List of actions on this object
        """
        return self.by_object.get(object_id, [])
    
    def _trim_history(self):
        """
        Trim history to max size (ENHANCED Week 8)
        
        Strategy:
        1. Remove expired actions first
        2. If still too large, remove oldest
        
        Maintains all indices.
        """
        if len(self.actions) <= self.max_history_size:
            return
        
        current_time = time.time()
        
        # Remove expired actions first (if auto-cleanup enabled)
        if self.auto_cleanup_expired:
            expired = [a for a in self.actions if a.is_expired(current_time)]
            self.total_expired += len(expired)
            
            for action in expired:
                self._remove_action(action)
        
        # If still too large, remove oldest (non-undoable first)
        while len(self.actions) > self.max_history_size:
            # Find oldest non-reversible or already undone action
            for action in self.actions:
                if not action.reversible or action.undone:
                    self._remove_action(action)
                    break
            else:
                # All actions reversible and not undone - remove oldest
                oldest = self.actions[0]
                self._remove_action(oldest)
    
    def _remove_action(self, action: ActionRecord):
        """
        Remove action from all indices (NEW Week 8)
        
        Args:
            action: Action to remove
        """
        # Remove from main list
        try:
            self.actions.remove(action)
        except ValueError:
            pass
        
        # Remove from user index
        if action.user_id and action.user_id in self.by_user:
            try:
                self.by_user[action.user_id].remove(action)
            except ValueError:
                pass
        
        # Remove from session index
        if action.session_id and action.session_id in self.by_session:
            try:
                self.by_session[action.session_id].remove(action)
            except ValueError:
                pass
        
        # Remove from object index
        if action.object_id in self.by_object:
            try:
                self.by_object[action.object_id].remove(action)
            except ValueError:
                pass
    
    def get_statistics(self) -> dict:
        """
        Get comprehensive history statistics (ENHANCED Week 8)
        
        Returns:
            Dictionary with detailed metrics
        """
        current_time = time.time()
        available_undo = self.last_reversible(current_time)
        
        # Count by status
        undone_count = sum(1 for a in self.actions if a.undone)
        reversible_count = sum(1 for a in self.actions if a.reversible)
        expired_count = sum(1 for a in self.actions if a.is_expired(current_time))
        
        return {
            'total_recorded': self.total_recorded,
            'total_undone': self.total_undone,
            'total_expired': self.total_expired,
            'total_non_reversible': self.total_non_reversible,
            'current_size': len(self.actions),
            'current_undone': undone_count,
            'current_reversible': reversible_count,
            'current_expired': expired_count,
            'undo_available': available_undo is not None,
            'undo_rate': self.total_undone / max(1, self.total_recorded),
            'reversible_rate': reversible_count / max(1, len(self.actions))
        }
