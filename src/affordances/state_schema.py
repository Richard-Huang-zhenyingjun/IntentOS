"""State Schema - State estimation data structures for Week 6."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional


# === PER-CATEGORY STATE ENUMS ===

class LampState(str, Enum):
    """Lamp power states"""
    ON = "on"
    OFF = "off"
    UNKNOWN = "unknown"
    
    @classmethod
    def from_world_state(cls, world_state: dict) -> 'LampState':
        """Convert world state to enum"""
        power = world_state.get('power', 'unknown')
        if power == 'on':
            return cls.ON
        elif power == 'off':
            return cls.OFF
        else:
            return cls.UNKNOWN


class DoorState(str, Enum):
    """Door position states"""
    OPEN = "open"
    CLOSED = "closed"
    UNKNOWN = "unknown"
    
    @classmethod
    def from_world_state(cls, world_state: dict) -> 'DoorState':
        position = world_state.get('position', 'unknown')
        if position == 'open':
            return cls.OPEN
        elif position == 'closed':
            return cls.CLOSED
        else:
            return cls.UNKNOWN


class PhoneState(str, Enum):
    """Phone screen states"""
    SCREEN_ON = "screen_on"
    SCREEN_OFF = "screen_off"
    UNKNOWN = "unknown"
    
    @classmethod
    def from_world_state(cls, world_state: dict) -> 'PhoneState':
        screen = world_state.get('screen', 'unknown')
        if screen == 'screen_on':
            return cls.SCREEN_ON
        elif screen == 'screen_off':
            return cls.SCREEN_OFF
        else:
            return cls.UNKNOWN


# === STATE ESTIMATE ===

@dataclass(frozen=True)
class ObjectStateEstimate:
    """
    Estimated state of an object
    
    Created by StateEstimator
    Used by AffordanceEngine to generate context-aware affordances
    """
    # Object context
    object_id: str
    category: str  # lamp, door, phone
    
    # State estimate
    state: str  # Value from corresponding enum (e.g., "on", "off", "unknown")
    confidence: float  # 0.0-1.0
    
    # Reasoning
    method: str  # "world_state_hint", "visual_heuristic", "default"
    reason: str  # Human-readable explanation
    evidence: Dict[str, Any]  # Supporting data
    
    # Metadata
    timestamp: float
    frame_id: int
    
    # Uncertainty flags
    uncertain: bool = False  # confidence in fallback range
    too_uncertain: bool = False  # confidence below block threshold
    
    def __post_init__(self):
        """Validate estimate"""
        assert 0.0 <= self.confidence <= 1.0, f"Invalid confidence: {self.confidence}"
        assert self.category in ['lamp', 'door', 'phone', 'unknown'], \
            f"Invalid category: {self.category}"
    
    @classmethod
    def create_unknown(cls,
                      object_id: str,
                      category: str,
                      reason: str,
                      timestamp: float,
                      frame_id: int) -> 'ObjectStateEstimate':
        """Factory for unknown state"""
        return cls(
            object_id=object_id,
            category=category,
            state='unknown',
            confidence=0.0,
            method='default',
            reason=reason,
            evidence={},
            timestamp=timestamp,
            frame_id=frame_id,
            uncertain=False,
            too_uncertain=True
        )


# === SAFETY CONSTRAINTS ===

@dataclass
class SafetyConstraints:
    """
    Constraints on what actions are safe given current state
    
    Used by AffordanceEngine to filter options
    """
    # Allowed actions
    allowed_actions: set  # Set of AffordanceType values
    
    # Restrictions
    block_all: bool  # Block all actions due to uncertainty
    require_toggle: bool  # Must use toggle (state uncertain)
    allow_specific: bool  # Can use specific actions (state confident)
    
    # Reasoning
    reason: str
    confidence: float
    
    @classmethod
    def create_blocked(cls, reason: str) -> 'SafetyConstraints':
        """Factory for blocked constraints"""
        return cls(
            allowed_actions=set(),
            block_all=True,
            require_toggle=False,
            allow_specific=False,
            reason=reason,
            confidence=0.0
        )
    
    @classmethod
    def create_toggle_only(cls, toggle_action: str, reason: str, confidence: float) -> 'SafetyConstraints':
        """Factory for toggle-only constraints"""
        return cls(
            allowed_actions={toggle_action},
            block_all=False,
            require_toggle=True,
            allow_specific=False,
            reason=reason,
            confidence=confidence
        )
    
    @classmethod
    def create_specific(cls, specific_actions: set, reason: str, confidence: float) -> 'SafetyConstraints':
        """Factory for specific action constraints"""
        return cls(
            allowed_actions=specific_actions,
            block_all=False,
            require_toggle=False,
            allow_specific=True,
            reason=reason,
            confidence=confidence
        )




