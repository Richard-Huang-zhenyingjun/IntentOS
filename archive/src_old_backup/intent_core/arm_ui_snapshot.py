"""
Arm UI snapshot - single source of truth for visualization.
Week 9: Complete transparency, all state visible to user.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import time


@dataclass
class ArmUISnapshot:
    """
    Complete UI state snapshot.
    
    Single source of truth for visualization - no hidden state.
    Week 9: All system state visible to user for trust and transparency.
    """
    
    # Timestamp
    timestamp: float = field(default_factory=time.time)
    
    # === Core State ===
    state: str = "idle"                      # State machine state
    last_event: str = ""                     # Last state transition
    cooldown_frames: int = 0
    
    # === Target Selection ===
    cursor_source: str = "mouse"             # "gaze" or "mouse"
    hover_object_id: Optional[int] = None    # Currently hovered object
    locked_object_id: Optional[int] = None   # Locked target
    selection_locked: bool = False
    hover_progress: float = 0.0              # Dwell progress (0-1)
    
    # === Proposal ===
    available_actions: List[str] = field(default_factory=list)
    proposed_action: Optional[str] = None
    proposal_reason: Optional[str] = None
    proposal_object_id: Optional[int] = None
    
    # === Decision Input (EEG) ===
    decision_source: str = "keyboard"        # "keyboard", "MockEEG", "BrainLink"
    eeg_signal: str = "IDLE"                 # Current signal
    eeg_attention: Optional[float] = None
    eeg_meditation: Optional[float] = None
    eeg_signal_quality: Optional[float] = None
    eeg_stable: bool = True
    eeg_blocked: bool = False
    eeg_blocked_reason: Optional[str] = None
    eeg_confidence: Optional[float] = None
    cooldown_remaining_s: float = 0.0
    
    # === Execution ===
    executing_action: Optional[str] = None
    execution_progress: float = 0.0
    execution_steps: int = 0
    execution_phase: Optional[str] = None    # e.g., "approaching", "lifting"
    
    # === Grasp State ===
    holding_object_id: Optional[int] = None
    gripper_state: str = "open"              # "open" or "closed"
    
    # === World State ===
    ee_pos: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    obj_pos: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    joint_angles: List[float] = field(default_factory=list)  # PATCH 4: Joint angles (radians)
    
    # === Execution Result ===
    last_execution_result: Optional[Dict[str, Any]] = None
    
    # === Recovery / Safety ===
    paused: bool = False
    pause_trigger: Optional[str] = None
    pause_explanation: Optional[str] = None
    pause_duration: float = 0.0
    recovery_steps: List[str] = field(default_factory=list)
    
    # === Fault Injection ===
    active_faults: List[str] = field(default_factory=list)
    fault_injector_enabled: bool = False
    
    # === Trust Metrics (Headline) ===
    false_executions: int = 0                # MUST BE 0
    executions_started: int = 0
    executions_completed: int = 0
    pauses_triggered: int = 0
    executions_blocked_unstable: int = 0
    
    # === Performance ===
    fps: float = 0.0
    frame_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp,
            "state": self.state,
            "last_event": self.last_event,
            "selection": {
                "cursor_source": self.cursor_source,
                "hover_object_id": self.hover_object_id,
                "locked_object_id": self.locked_object_id,
                "selection_locked": self.selection_locked,
                "hover_progress": self.hover_progress,
            },
            "proposal": {
                "available_actions": self.available_actions,
                "proposed_action": self.proposed_action,
                "proposal_reason": self.proposal_reason,
            },
            "eeg": {
                "source": self.decision_source,
                "signal": self.eeg_signal,
                "attention": self.eeg_attention,
                "stable": self.eeg_stable,
                "blocked": self.eeg_blocked,
                "blocked_reason": self.eeg_blocked_reason,
            },
            "execution": {
                "action": self.executing_action,
                "progress": self.execution_progress,
                "steps": self.execution_steps,
                "phase": self.execution_phase,
            },
            "grasp": {
                "holding_object_id": self.holding_object_id,
                "gripper_state": self.gripper_state,
            },
            "recovery": {
                "paused": self.paused,
                "trigger": self.pause_trigger,
                "explanation": self.pause_explanation,
                "steps": self.recovery_steps,
            },
            "trust": {
                "false_executions": self.false_executions,
                "executions_started": self.executions_started,
                "executions_completed": self.executions_completed,
                "pauses_triggered": self.pauses_triggered,
                "blocked_unstable": self.executions_blocked_unstable,
            },
            "performance": {
                "fps": self.fps,
                "frame_count": self.frame_count,
            }
        }

