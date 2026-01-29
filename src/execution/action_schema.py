"""Action Schema - Data structures for action execution."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional
import uuid


class ActionType(str, Enum):
    """
    Executable action types (ENHANCED Week 6)
    
    Week 5: Generic toggles
    Week 6: Add specific state-setting actions
    
    These map 1:1 from AffordanceType for executable actions
    """
    # Power control (ENHANCED Week 6)
    TOGGLE_POWER = "toggle_power"
    TURN_ON = "turn_on"      # NEW
    TURN_OFF = "turn_off"    # NEW
    
    # Physical state (ENHANCED Week 6)
    TOGGLE_OPEN = "toggle_open"
    OPEN = "open"            # NEW
    CLOSE = "close"          # NEW
    
    # Screens (ENHANCED Week 6)
    TOGGLE_SCREEN = "toggle_screen"
    WAKE = "wake"            # NEW
    SLEEP = "sleep"          # NEW
    
    # Placeholders (Week 5)
    PICK_UP = "pick_up"
    PUT_DOWN = "put_down"
    MOVE = "move"


@dataclass(frozen=True)
class ActionRequest:
    """
    Request to execute an action on an object
    
    Created by Router after confirmation + authorization
    Consumed by ActionExecutor
    """
    # Identifiers
    action_id: str  # Unique ID for this action
    user_id: Optional[str]  # User requesting action (Week 7+)
    session_id: Optional[str]  # Session ID (Week 7+)
    
    # Target
    object_id: str  # Track ID from Week 2
    object_label: str  # Human-readable label
    category: str  # Object category (lamp/door/phone)
    
    # Action
    action_type: ActionType
    
    # Context
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0
    
    # Authority trail (for logging/debugging)
    authority_chain: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def create(cls, 
               object_id: str,
               object_label: str,
               category: str,
               action_type: ActionType,
               timestamp: float,
               user_id: Optional[str] = None,
               session_id: Optional[str] = None,
               metadata: Optional[Dict[str, Any]] = None) -> 'ActionRequest':
        """Factory method for creating action requests"""
        return cls(
            action_id=f"action_{uuid.uuid4().hex[:8]}",
            user_id=user_id,
            session_id=session_id,
            object_id=object_id,
            object_label=object_label,
            category=category,
            action_type=action_type,
            metadata=metadata or {},
            timestamp=timestamp,
            authority_chain={
                'created_at': timestamp,
                'created_by': 'router'
            }
        )


@dataclass
class ExecutionResult:
    """
    Result of action execution
    
    Returned by ActionExecutor
    Used by Router for logging and state updates
    """
    # Success
    ok: bool
    
    # State changes
    before_state: Optional[Dict[str, Any]]
    after_state: Optional[Dict[str, Any]]
    
    # Metadata
    reason: str  # Success message or failure reason
    reversible: bool  # Can this action be undone?
    action_id: str  # ID of executed action
    
    # Timing
    timestamp: float
    execution_time_ms: float = 0.0
    
    # Error details (if ok=False)
    error_code: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None

