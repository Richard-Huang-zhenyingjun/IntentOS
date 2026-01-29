"""State machine - manages SELECT→PROPOSE→CONFIRM→EXECUTE lifecycle."""

from typing import Optional
import time
from src.core.schema import ArmUIState, ArmProposal, ArmDecision, DecisionSignal, ArmActionType


class StateMachine:
    """Finite state machine for intent authorization."""
    
    def __init__(self):
        # State
        self.state = ArmUIState.IDLE
        
        # Target
        self.target_id: Optional[int] = None
        self.target_locked = False
        
        # Proposal
        self.proposal: Optional[ArmProposal] = None
        
        # Pause
        self.paused = False
        self.pause_reason = ""
        
        # Frame tracking
        self.state_entry_frame = 0
        self.current_frame = 0
    
    def set_target(self, target_id: Optional[int], locked: bool = False):
        """Set current target object."""
        self.target_id = target_id
        self.target_locked = locked
        
        if target_id is not None and locked:
            print(f"[FSM] Target locked: {target_id}")
            if self.state == ArmUIState.IDLE:
                self._transition_to(ArmUIState.SELECTING)
    
    def propose_action(self, action: ArmActionType, reason: str):
        """Propose an action (enters CONFIRMING state)."""
        if self.paused:
            print("[FSM] Cannot propose while paused")
            return
        
        if self.target_id is None:
            print("[FSM] Cannot propose without target")
            return
        
        self.proposal = ArmProposal(
            target_id=self.target_id,
            action=action,
            reason=reason,
            timestamp=time.time()
        )
        
        self._transition_to(ArmUIState.CONFIRMING)
        print(f"[FSM] Proposed: {action.value} - {reason}")
    
    def process_decision(self, decision: ArmDecision) -> bool:
        """Process user decision.
        
        Returns:
            True if execution should proceed, False otherwise
        """
        if self.state != ArmUIState.CONFIRMING:
            return False
        
        if decision.signal == DecisionSignal.CONFIRM:
            print(f"[FSM] ✓ Confirmed via {decision.source}")
            self._transition_to(ArmUIState.EXECUTING)
            return True
        
        elif decision.signal == DecisionSignal.CANCEL:
            print(f"[FSM] ✗ Cancelled via {decision.source}")
            self.clear_proposal()
            self._transition_to(ArmUIState.SELECTING)
            return False
        
        return False
    
    def start_execution(self):
        """Mark execution started."""
        if self.state != ArmUIState.CONFIRMING:
            print(f"[FSM] Warning: start_execution called in state {self.state}")
        self._transition_to(ArmUIState.EXECUTING)
    
    def complete_execution(self):
        """Mark execution complete."""
        if self.state == ArmUIState.EXECUTING:
            self._transition_to(ArmUIState.DONE)
            print(f"[FSM] ✓ Execution complete")
            # Clear proposal after completion
            self.clear_proposal()
    
    def trigger_pause(self, reason: str):
        """Trigger pause state."""
        self.paused = True
        self.pause_reason = reason
        self._transition_to(ArmUIState.PAUSED)
        print(f"[FSM] ⏸ PAUSED: {reason}")
    
    def resume_from_pause(self):
        """Resume from pause."""
        if not self.paused:
            return
        
        self.paused = False
        self.pause_reason = ""
        self.clear_proposal()
        self._transition_to(ArmUIState.IDLE)
        print("[FSM] ▶ Resumed from pause")
    
    def clear_proposal(self):
        """Clear current proposal."""
        self.proposal = None
    
    def reset(self):
        """Reset to IDLE."""
        self.state = ArmUIState.IDLE
        self.target_id = None
        self.target_locked = False
        self.proposal = None
        self.paused = False
        self.pause_reason = ""
    
    def _transition_to(self, new_state: ArmUIState):
        """Internal state transition."""
        if new_state != self.state:
            print(f"[FSM] {self.state.value} → {new_state.value}")
            self.state = new_state
            self.state_entry_frame = self.current_frame
    
    def tick(self):
        """Tick frame counter."""
        self.current_frame += 1

