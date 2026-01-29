"""Core schema for intent interface."""

from dataclasses import dataclass, field
from typing import Optional, Dict, List
from enum import Enum


class IntentType(Enum):
    """
    Types of user intents (ENHANCED Week 8).
    
    Categories:
    - Core: IDLE, SELECT, CONFIRM, CANCEL
    - Undo: UNDO_REQUEST, UNDO_CONFIRM, UNDO_CANCEL (Week 5)
    - Recovery: RECOVERY_START, RECOVERY_COMPLETE (NEW Week 8)
    """
    # Core intents
    IDLE = "idle"
    SELECT = "select"
    CONFIRM = "confirm"
    CANCEL = "cancel"
    
    # Undo intents (Week 5, enhanced Week 8)
    UNDO_REQUEST = "undo_request"
    UNDO_CONFIRM = "undo_confirm"
    UNDO_CANCEL = "undo_cancel"
    
    # Recovery intents (NEW Week 8)
    RECOVERY_START = "recovery_start"  # User initiates recovery
    RECOVERY_COMPLETE = "recovery_complete"  # Recovery validation passed


class CameraEventType(Enum):
    """Camera event types for logging."""
    FRAME_PROCESSED = "frame_processed"
    DETECTION_RUN = "detection_run"
    FOCUS_SELECTED = "focus_selected"
    SCOPE_SIGNAL_EMITTED = "scope_signal_emitted"
    AMBIGUITY_DETECTED = "ambiguity_detected"
    CAMERA_FAILURE = "camera_failure"


class SystemState(Enum):
    """
    System states (ENHANCED Week 8).
    
    State Flow:
    - Normal: IDLE → SCOPED → CONFIRMING → EXECUTING → SCOPED
    - Undo: SCOPED → UNDO_CONFIRMING → EXECUTING (undo) → SCOPED
    - Pause & Recovery: Any → PAUSED → RECOVERING → SCOPED (NEW Week 8)
    
    Critical:
    - PAUSED blocks ALL execution (safe stop)
    - RECOVERING requires fresh scope + confirmation
    - UNDO_CONFIRMING requires explicit confirmation
    """
    # Normal operation
    IDLE = "idle"
    SCOPED = "scoped"
    CONFIRMING = "confirming"
    EXECUTING = "executing"
    
    # Pause & Recovery (Week 7, enhanced Week 8)
    PAUSED = "paused"  # Safe stop, waiting for recovery
    RECOVERING = "recovering"  # User re-engaging after pause (NEW Week 8)
    
    # Undo (Week 5, enhanced Week 8)
    UNDO_CONFIRMING = "undo_confirming"  # Waiting for undo confirmation


@dataclass
class Intent:
    """User intent."""
    type: IntentType
    confidence: float
    timestamp: float
    source: str
    payload: Optional[Dict] = None


@dataclass
class SystemContext:
    """
    Extended context for state machine (NEW Week 8).
    
    Tracks additional context needed for recovery and undo.
    Enables transparent failure handling and safe recovery.
    """
    # Pause context
    pause_trigger: Optional[str] = None  # What caused the pause (e.g., "object_loss")
    pause_reason: Optional[str] = None  # Human-readable explanation
    pause_timestamp: Optional[float] = None  # When pause occurred
    
    # Recovery context
    recovery_required: bool = False  # Whether recovery is needed
    recovery_steps_completed: List[str] = field(default_factory=list)  # Steps user completed
    recovery_instructions: List[str] = field(default_factory=list)  # What user needs to do
    
    # Undo context
    undo_available: bool = False  # Whether undo is currently available
    undo_expires_at: Optional[float] = None  # When undo window closes
    undo_action_id: Optional[str] = None  # ID of action that can be undone

