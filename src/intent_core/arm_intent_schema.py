"""
Arm intent schema - states and decisions for robotics control.
Week 4: State machine + confirm/cancel workflow (paper-aligned).
Separate from existing Intent Interface to avoid conflicts.
"""

from dataclasses import dataclass
from enum import Enum
import time
from typing import Optional, List
from robotics.action_types import ArmActionType


class ArmUIState(str, Enum):
    """
    UI states for arm control workflow.
    
    Paper-aligned flow:
    IDLE → TARGETING → SELECTING_ACTION → AWAITING_CONFIRM → EXECUTING → DONE
    
    Week 8 Recovery flow:
    Any state → PAUSED → RECOVERING → TARGETING (requires fresh scope)
    """
    IDLE = "idle"                           # No activity
    TARGETING = "targeting"                 # User selecting target (not locked)
    SELECTING_ACTION = "selecting_action"   # Computing available actions
    AWAITING_CONFIRM = "awaiting_confirm"   # Proposal shown, waiting for C/X
    EXECUTING = "executing"                 # Action approved (Week 4: stub)
    DONE = "done"                          # Action complete, waiting for next
    PAUSED = "paused"                      # System paused due to failure (Week 8)
    RECOVERING = "recovering"              # User re-engaging after pause (Week 8)


class DecisionSignal(str, Enum):
    """
    User decision signals.
    
    Week 4: Keyboard input (C/X keys).
    Week 6: EEG input.
    """
    CONFIRM = "confirm"  # Approve proposed action
    CANCEL = "cancel"    # Reject proposed action
    IDLE = "idle"        # No decision


@dataclass
class ArmProposal:
    """
    Single action proposal shown to user.
    
    Paper concept: "action selection stage" shows one option at a time.
    """
    target_object_id: int
    action_type: ArmActionType
    reason: str                          # Why this action was proposed
    available_actions: List[ArmActionType]  # All available (for transparency)
    timestamp: float
    
    def __repr__(self) -> str:
        """Human-readable summary."""
        return (
            f"ArmProposal(\n"
            f"  action: {self.action_type}\n"
            f"  reason: {self.reason}\n"
            f"  target: object {self.target_object_id}\n"
            f"  available: {[str(a) for a in self.available_actions]}\n"
            f")"
        )


@dataclass
class ArmDecision:
    """
    User decision (confirm/cancel).
    
    Week 4: From keyboard.
    Week 6: From EEG (with confidence).
    """
    signal: DecisionSignal
    confidence: float      # 1.0 for keyboard, variable for EEG
    source: str            # "keyboard" or "eeg"
    timestamp: float
    
    @staticmethod
    def from_keyboard(signal: DecisionSignal) -> 'ArmDecision':
        """Create decision from keyboard input."""
        return ArmDecision(
            signal=signal,
            confidence=1.0,  # Keyboard is always certain
            source="keyboard",
            timestamp=time.time()
        )
    
    @staticmethod
    def idle() -> 'ArmDecision':
        """Create idle decision (no input)."""
        return ArmDecision(
            signal=DecisionSignal.IDLE,
            confidence=0.0,
            source="none",
            timestamp=time.time()
        )

