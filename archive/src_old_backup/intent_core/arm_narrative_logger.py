"""
Arm narrative logger - human-readable event stream.
Week 9: Natural language narration for transparency and trust.
Inspired by original Intent Interface project.
"""

from typing import List, Optional
from .arm_ui_snapshot import ArmUISnapshot


class ArmNarrativeLogger:
    """
    Generates human-readable narration from UI snapshots.
    
    Tracks state changes and produces natural language descriptions
    of system behavior. Avoids spam by only reporting changes.
    
    Week 9: "Show, don't just tell" - explain every decision.
    """
    
    def __init__(self, verbose: bool = True):
        """
        Initialize narrative logger.
        
        Args:
            verbose: If True, narrate all events; if False, only critical events
        """
        self.verbose = verbose
        
        # FIX 5: Throttle logging I/O
        self._log_counter = 0
        self._log_frequency = 15  # Log every 15 frames (~0.5s at 30fps)
        
        # Track previous state to detect changes
        self.last_state = None
        self.last_locked_id = None
        self.last_proposal = None
        self.last_executing = None
        self.last_paused = False
        self.last_signal = None
        self.last_result = None
    
    def describe(self, snapshot: ArmUISnapshot) -> List[str]:
        """
        Generate narrative lines for snapshot.
        
        FIX 5: Throttled for performance - only checks every N frames.
        
        Args:
            snapshot: Current UI snapshot
            
        Returns:
            List of narrative lines (only new events)
        """
        # FIX 5: Throttle logging I/O - only check every N frames
        self._log_counter += 1
        if self._log_counter % self._log_frequency != 0:
            return []  # Skip this frame
        
        lines = []
        
        # State changes
        if snapshot.state != self.last_state:
            lines.append(self._describe_state_change(snapshot))
            self.last_state = snapshot.state
        
        # Target selection
        if snapshot.locked_object_id != self.last_locked_id:
            if snapshot.locked_object_id is not None:
                lines.append(f"✓ Locked onto object {snapshot.locked_object_id}")
            elif self.last_locked_id is not None:
                lines.append(f"  Unlocked target (was object {self.last_locked_id})")
            self.last_locked_id = snapshot.locked_object_id
        
        # Proposal
        if snapshot.proposed_action != self.last_proposal:
            if snapshot.proposed_action:
                lines.append(self._describe_proposal(snapshot))
            self.last_proposal = snapshot.proposed_action
        
        # Decision signal
        if self.verbose and snapshot.eeg_signal != self.last_signal:
            if snapshot.eeg_signal != "IDLE":
                lines.append(f"  Decision: {snapshot.eeg_signal}")
            self.last_signal = snapshot.eeg_signal
        
        # Execution start
        if snapshot.executing_action != self.last_executing:
            if snapshot.executing_action:
                lines.append(f"▶ Executing: {snapshot.executing_action}")
            self.last_executing = snapshot.executing_action
        
        # Execution result
        if snapshot.last_execution_result != self.last_result:
            if snapshot.last_execution_result:
                lines.append(self._describe_result(snapshot.last_execution_result))
            self.last_result = snapshot.last_execution_result
        
        # Pause
        if snapshot.paused != self.last_paused:
            if snapshot.paused:
                lines.append(self._describe_pause(snapshot))
            else:
                lines.append("✓ Recovery complete, system resumed")
            self.last_paused = snapshot.paused
        
        # EEG blocking
        if snapshot.eeg_blocked and snapshot.state == "awaiting_confirm":
            if snapshot.eeg_blocked_reason:
                lines.append(f"⚠️  Confirmation blocked: {snapshot.eeg_blocked_reason}")
        
        return lines
    
    def _describe_state_change(self, snapshot: ArmUISnapshot) -> str:
        """Describe state machine transition."""
        state_names = {
            "idle": "System idle",
            "targeting": "Waiting for target selection",
            "selecting_action": "Computing available actions",
            "awaiting_confirm": "Awaiting confirmation",
            "executing": "Executing action",
            "done": "Action complete",
            "paused": "System paused",
        }
        
        return f"→ {state_names.get(snapshot.state, snapshot.state)}"
    
    def _describe_proposal(self, snapshot: ArmUISnapshot) -> str:
        """Describe action proposal."""
        action = snapshot.proposed_action or "unknown"
        reason = snapshot.proposal_reason or "no reason given"
        
        # Clean up action name
        action_display = action.replace('_', ' ').title()
        
        return f"💡 Proposed: {action_display} — {reason}"
    
    def _describe_result(self, result: dict) -> str:
        """Describe execution result."""
        success = result.get("success", False)
        reason = result.get("reason", "")
        action = result.get("action_type", "action")
        
        if success:
            return f"✓ {action.replace('_', ' ').title()} succeeded: {reason}"
        else:
            return f"✗ {action.replace('_', ' ').title()} failed: {reason}"
    
    def _describe_pause(self, snapshot: ArmUISnapshot) -> str:
        """Describe pause event."""
        trigger = snapshot.pause_trigger or "unknown"
        explanation = snapshot.pause_explanation or ""
        
        line = f"⏸  PAUSED: {trigger}"
        if explanation:
            line += f" — {explanation}"
        
        return line
    
    def reset(self) -> None:
        """Reset tracking state."""
        self.last_state = None
        self.last_locked_id = None
        self.last_proposal = None
        self.last_executing = None
        self.last_paused = False
        self.last_signal = None
        self.last_result = None

