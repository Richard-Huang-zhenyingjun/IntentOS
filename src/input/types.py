"""
Decision pipeline types.

Replaces Week 3's Decision dataclass with richer DecisionFrame.
All pipeline stages operate on DecisionFrame.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List


class DecisionIntent(Enum):
    """What the user (or EEG) is signaling"""
    NONE = "none"          # No decision
    CONFIRM = "confirm"    # Approve proposed action
    CANCEL = "cancel"      # Reject / abort


class SourceType(Enum):
    """Where the decision came from"""
    KEYBOARD = "keyboard"
    EEG = "eeg"
    MOCK_EEG = "mock_eeg"
    TEST = "test"
    COMBINED = "combined"  # Router merged multiple sources
    UNKNOWN = "unknown"


class FilterAction(Enum):
    """What the filter did to a decision"""
    PASSED = "passed"
    BLOCKED_QUALITY = "blocked_quality"
    BLOCKED_DEBOUNCE = "blocked_debounce"
    BLOCKED_HOLD = "blocked_hold"
    BLOCKED_POLICY = "blocked_policy"
    DOWNGRADED = "downgraded"  # CONFIRM → NONE


@dataclass(frozen=True)
class DecisionFrame:
    """
    Immutable decision snapshot from the pipeline.
    
    This is what the orchestrator sees — a single, filtered decision.
    The orchestrator never knows how many sources contributed
    or what the filter blocked.
    """
    intent: DecisionIntent = DecisionIntent.NONE
    source_type: SourceType = SourceType.UNKNOWN
    quality: float = 1.0    # 0.0-1.0, keyboard always 1.0
    frame_number: int = 0
    
    # Debug / observability (orchestrator can ignore these)
    raw_intents: Dict[str, str] = field(default_factory=dict)
    filter_action: FilterAction = FilterAction.PASSED
    filter_reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_confirm(self) -> bool:
        return self.intent == DecisionIntent.CONFIRM
    
    @property
    def is_cancel(self) -> bool:
        return self.intent == DecisionIntent.CANCEL


@dataclass
class RawSourceReading:
    """
    Raw reading from a single decision source (before routing/filtering).
    Mutable — only used internally in the pipeline.
    """
    intent: DecisionIntent = DecisionIntent.NONE
    source_type: SourceType = SourceType.UNKNOWN
    quality: float = 1.0
    raw_pressed: bool = False  # Whether physical button/signal is active THIS frame
    metadata: Dict[str, Any] = field(default_factory=dict)


