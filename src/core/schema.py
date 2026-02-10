"""Core data types for Intent Interface."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, TYPE_CHECKING
import time

# Forward references for Week 1 types
if TYPE_CHECKING:
    from src.intelligence.scene_summary import SceneSummary
    from src.execution.primitive_executor import ExecutorStatus
    from src.robot.simulator import ArmState, ObjectState

# Week 1 imports
from src.intelligence.scene_summary import SceneSummary
from src.execution.primitive_executor import ExecutorStatus


class ArmUIState(str, Enum):
    """State machine states."""
    IDLE = "idle"                    # No activity
    SELECTING = "selecting"          # Target locked, computing proposal
    CONFIRMING = "confirming"        # Awaiting confirmation
    EXECUTING = "executing"          # Action in progress
    DONE = "done"                    # Action complete
    PAUSED = "paused"                # Recovery needed


class DecisionSignal(str, Enum):
    """Input decision signals."""
    IDLE = "idle"
    CONFIRM = "confirm"
    CANCEL = "cancel"


class ArmActionType(str, Enum):
    """Available arm actions."""
    MOVE_UP = "move_up"
    REACH = "reach"
    GRASP = "grasp"
    PLACE = "place"
    CLEAN_TABLE = "clean_table"  # Week 1: Clean messy table
    IDLE = "idle"                # Week 1: No action needed
    
    def __str__(self) -> str:
        """String representation (just the value)."""
        return self.value


@dataclass(frozen=True)
class ArmProposal:
    """Proposed action awaiting confirmation."""
    target_id: int
    action: ArmActionType
    reason: str
    timestamp: float
    
    def __repr__(self) -> str:
        """Human-readable summary."""
        return (
            f"ArmProposal(\n"
            f"  action: {self.action}\n"
            f"  reason: {self.reason}\n"
            f"  target: object {self.target_id}\n"
            f")"
        )


@dataclass(frozen=True)
class ArmDecision:
    """User decision (keyboard or EEG)."""
    signal: DecisionSignal
    confidence: float
    source: str  # "keyboard" or "eeg"
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


@dataclass
class UISnapshot:
    """Complete UI state (read-only) - Enhanced for Week 1 with scene understanding."""
    # State
    state: ArmUIState
    frame_count: int
    timestamp: float
    
    # Target
    target_id: Optional[int]
    target_locked: bool
    
    # Proposal
    proposal: Optional[ArmProposal]
    
    # Grasp
    holding_object: bool
    attached_id: Optional[int]
    
    # Safety
    false_executions: int  # MUST BE 0
    paused: bool
    pause_reason: str
    
    # Metadata
    what_happened: str  # Human-readable event
    
    # NEW Week 1 fields
    scene_summary: Optional['SceneSummary'] = None
    executor_status: Optional['ExecutorStatus'] = None
    primitive_index: int = 0
    
    # Week 1: Arm and object states (for scene understanding)
    arm_state: Optional['ArmState'] = None
    objects: Optional[List['ObjectState']] = None
    current_proposal: Optional[ArmProposal] = None  # Alias for proposal, Week 1 naming
    
    # Week 4: Proposer statistics
    proposer_stats: Optional[dict] = None
    
    # Week 7: Authorization, Trust, Autonomy
    autonomy_level: Optional[str] = None
    task_trust: Optional[float] = None
    auth_token_id: Optional[str] = None
    awaiting_reauth: bool = False
    awaiting_object_confirm: bool = False

