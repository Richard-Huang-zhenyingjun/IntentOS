"""Affordance Schema - Data structures for object affordances."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List


class ObjectCategory(str, Enum):
    """
    Object categories recognized by the system
    
    Week 3: Basic categories only
    Week 6+: Add state-aware subcategories (LAMP_ON, LAMP_OFF)
    """
    LAMP = "lamp"
    DOOR = "door"
    CUP = "cup"
    PHONE = "phone"
    BOOK = "book"
    BOTTLE = "bottle"
    UNKNOWN = "unknown"
    
    @classmethod
    def from_string(cls, s: str) -> 'ObjectCategory':
        """Safe conversion from string"""
        s_lower = s.lower().strip()
        for category in cls:
            if category.value == s_lower:
                return category
        return cls.UNKNOWN


class AffordanceType(str, Enum):
    """
    Primitive actions the system can suggest
    
    Week 5: Generic toggles only
    Week 6: Add specific state-aware actions
    """
    # Power control (ENHANCED Week 6)
    TOGGLE_POWER = "toggle_power"  # State-agnostic fallback
    TURN_ON = "turn_on"            # NEW: State-aware (lamp OFF → ON)
    TURN_OFF = "turn_off"          # NEW: State-aware (lamp ON → OFF)
    
    # Physical state (ENHANCED Week 6)
    TOGGLE_OPEN = "toggle_open"    # State-agnostic fallback
    OPEN = "open"                  # NEW: State-aware (door CLOSED → OPEN)
    CLOSE = "close"                # NEW: State-aware (door OPEN → CLOSED)
    
    # Screens (ENHANCED Week 6)
    TOGGLE_SCREEN = "toggle_screen"  # State-agnostic fallback
    WAKE = "wake"                    # NEW: State-aware (screen OFF → ON)
    SLEEP = "sleep"                  # NEW: State-aware (screen ON → OFF)
    
    # Manipulation (placeholders, Week 5)
    PICK_UP = "pick_up"
    PUT_DOWN = "put_down"
    MOVE = "move"
    
    # Meta
    NONE = "none"
    WAIT = "wait"


class AffordanceRisk(str, Enum):
    """Risk level for affordance execution"""
    LOW = "low"  # Reversible, safe (toggle light)
    MEDIUM = "medium"  # Reversible but notable (open door)
    HIGH = "high"  # Irreversible or requires care (pick up fragile object)
    UNKNOWN = "unknown"  # Cannot assess risk


@dataclass(frozen=True)
class AffordanceOption:
    """
    A single suggested action for an object
    
    CRITICAL: This is a SUGGESTION, not a command
    Having an AffordanceOption does NOT grant permission to execute
    """
    affordance_type: AffordanceType
    
    # UI Display
    title: str  # Short label: "Turn On", "Open Door"
    description: str  # Longer explanation: "Turn on the lamp"
    
    # Safety metadata
    risk: AffordanceRisk
    requires_confirmation: bool  # ALWAYS True in this project
    
    # Reasoning (for transparency)
    reason: str  # Why this affordance was suggested
    confidence: float  # 0.0-1.0 (how sure we are this makes sense)
    
    # Additional context
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Enforce invariants"""
        assert self.requires_confirmation == True, \
            "All affordances MUST require confirmation (authority boundary)"
        assert 0.0 <= self.confidence <= 1.0, \
            f"Confidence must be [0,1], got {self.confidence}"
        assert len(self.title) > 0, "Title cannot be empty"
    
    @classmethod
    def create_placeholder(cls, affordance_type: AffordanceType, reason: str):
        """Create a placeholder affordance (for unimplemented actions)"""
        return cls(
            affordance_type=affordance_type,
            title=f"{affordance_type.value.replace('_', ' ').title()} (Not Available)",
            description=f"This action is not yet implemented",
            risk=AffordanceRisk.UNKNOWN,
            requires_confirmation=True,
            reason=reason,
            confidence=0.0,
            metadata={'placeholder': True}
        )


@dataclass(frozen=True)
class AffordanceSet:
    """
    Complete affordance output for a scoped object
    
    Either:
    - options is populated (1-3 affordances)
    - OR blocked=True with reason
    
    Never both
    """
    # Object context
    object_id: str  # Track ID from Week 2
    object_label: str  # Raw detector label
    category: ObjectCategory
    category_confidence: float
    
    # Affordances (empty if blocked)
    options: List[AffordanceOption]  # Length <= max_options
    
    # Blocking status
    blocked: bool
    block_reason: str  # Human-readable explanation if blocked
    
    # Metadata
    timestamp: float
    frame_id: int
    
    # Reasoning trail (for logging/debugging)
    reasoning: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Enforce invariants"""
        max_opts = 3  # Could be configurable
        assert len(self.options) <= max_opts, \
            f"Too many options: {len(self.options)} > {max_opts}"
        
        # If blocked, options should be empty
        if self.blocked:
            assert len(self.options) == 0, \
                "Blocked affordance sets should have no options"
            assert len(self.block_reason) > 0, \
                "Blocked sets must have a reason"
        else:
            # Not blocked, should have at least 1 option (or be NONE)
            if self.category != ObjectCategory.UNKNOWN:
                assert len(self.options) >= 0, \
                    "Non-blocked sets should have options or be UNKNOWN"
    
    @classmethod
    def create_blocked(cls, object_id: str, object_label: str, 
                      reason: str, timestamp: float, frame_id: int):
        """Factory for blocked affordance set"""
        return cls(
            object_id=object_id,
            object_label=object_label,
            category=ObjectCategory.UNKNOWN,
            category_confidence=0.0,
            options=[],
            blocked=True,
            block_reason=reason,
            timestamp=timestamp,
            frame_id=frame_id,
            reasoning={'blocked_at': 'creation', 'reason': reason}
        )
    
    @classmethod
    def create_empty(cls, object_id: str, object_label: str,
                    category: ObjectCategory, reason: str, 
                    timestamp: float, frame_id: int):
        """Factory for non-blocked but empty affordance set"""
        return cls(
            object_id=object_id,
            object_label=object_label,
            category=category,
            category_confidence=0.0,
            options=[],
            blocked=False,
            block_reason="",
            timestamp=timestamp,
            frame_id=frame_id,
            reasoning={'empty_reason': reason}
        )

