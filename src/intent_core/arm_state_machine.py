"""
Arm state machine - enforces proposal → confirm → execute workflow.
Week 4: Paper-aligned control loop with explicit confirmation.
"""

from typing import Optional, List
import time
from .arm_intent_schema import (
    ArmUIState, DecisionSignal, ArmProposal, ArmDecision
)
from robotics.action_types import ArmActionType


class ArmStateMachine:
    """
    Finite state machine for arm control workflow.
    
    Paper-aligned flow:
    1. User selects target (gaze)
    2. System proposes action
    3. User confirms/cancels
    4. System executes (Week 4: stub) or returns to step 2
    
    Safety invariants:
    - Never execute without CONFIRM
    - One proposal at a time
    - CANCEL clears proposal
    - All transitions logged
    """
    
    def __init__(self):
        """Initialize state machine."""
        self.state = ArmUIState.IDLE
        self.active_target_id: Optional[int] = None
        self.target_locked: bool = False
        self.active_proposal: Optional[ArmProposal] = None
        self.last_event: str = "initialized"
        self.cooldown_frames: int = 0
        self.history: List[str] = []
        
        # Week 5: Multi-frame execution tracking
        self.executing_action: Optional[ArmActionType] = None
        self.execution_started_at: float = 0.0
        self.execution_last_progress: float = 0.0
        
        # Week 7: EEG stability tracking
        self.eeg_unstable_frames: int = 0
        self.max_unstable_frames: int = 30  # ~1s at 30fps
        
        # Week 8: Recovery state
        self.in_recovery = False
        self.recovery_conditions_met = False
        
        self._log_event("State machine initialized")
    
    def _log_event(self, event: str) -> None:
        """Log state machine event."""
        self.last_event = event
        self.history.append(f"{time.time():.3f}: {event}")
        if len(self.history) > 100:  # Keep last 100 events
            self.history.pop(0)
    
    def set_target(self, target_id: Optional[int], locked: bool) -> None:
        """
        Update target selection state.
        
        Args:
            target_id: Selected object ID, or None
            locked: Whether target is locked (stable)
        """
        # Detect target change
        if target_id != self.active_target_id:
            if target_id is not None:
                self._log_event(f"Target changed: {self.active_target_id} → {target_id}")
            else:
                self._log_event("Target cleared")
            
            # Clear proposal if target changes
            if self.active_proposal is not None:
                self._log_event("Proposal cleared (target changed)")
                self.active_proposal = None
        
        self.active_target_id = target_id
        self.target_locked = locked
    
    def tick(self, world, decision: ArmDecision, controller=None) -> None:
        """
        Advance state machine one frame.
        
        Args:
            world: WorldModel instance (for action availability)
            decision: User decision (CONFIRM/CANCEL/IDLE)
            controller: ArmController instance (Week 5+, for cancellation)
        """
        print(f"\n[STATE_MACHINE] tick() Entry:")
        print(f"  Current state: {self.state}")
        print(f"  Decision: {decision}")
        print(f"  Active proposal: {self.active_proposal}")
        print(f"  Target locked: {self.target_locked}")
        print(f"  Target ID: {self.active_target_id}")
        
        # PATCH 7: Log ignored decisions
        if decision.signal == DecisionSignal.CONFIRM and self.state != ArmUIState.AWAITING_CONFIRM:
            print(f"[IGNORED] CONFIRM in {self.state.value} (need AWAITING_CONFIRM)")
        elif decision.signal == DecisionSignal.CANCEL:
            # CANCEL is only processed in AWAITING_CONFIRM or EXECUTING
            if self.state not in [ArmUIState.AWAITING_CONFIRM, ArmUIState.EXECUTING]:
                print(f"[IGNORED] CANCEL in {self.state.value} (need AWAITING_CONFIRM or EXECUTING)")
        
        # Decrement cooldown
        if self.cooldown_frames > 0:
            self.cooldown_frames -= 1
        
        # State-specific logic
        if self.state == ArmUIState.IDLE:
            self._tick_idle()
        
        elif self.state == ArmUIState.TARGETING:
            self._tick_targeting()
        
        elif self.state == ArmUIState.SELECTING_ACTION:
            self._tick_selecting_action(world)
        
        elif self.state == ArmUIState.AWAITING_CONFIRM:
            print(f"[DBG STATE_MACHINE] Entering _tick_awaiting_confirm with decision: {decision}")
            self._tick_awaiting_confirm(decision, controller)
            print(f"[DBG STATE_MACHINE] After _tick_awaiting_confirm, state: {self.state}")
        
        elif self.state == ArmUIState.EXECUTING:
            self._tick_executing(controller)
        
        elif self.state == ArmUIState.DONE:
            self._tick_done()
        
        elif self.state == ArmUIState.PAUSED:
            self._tick_paused()
        
        print(f"[STATE_MACHINE] tick() Exit:")
        print(f"  New state: {self.state}")
        print(f"  New proposal: {self.active_proposal}")
    
    def _tick_idle(self) -> None:
        """Tick IDLE state: wait for target."""
        if self.active_target_id is not None:
            if self.target_locked:
                self._transition_to(ArmUIState.SELECTING_ACTION)
            else:
                self._transition_to(ArmUIState.TARGETING)
    
    def _tick_targeting(self) -> None:
        """Tick TARGETING state: wait for target lock."""
        if self.active_target_id is None:
            self._transition_to(ArmUIState.IDLE)
        elif self.target_locked:
            self._transition_to(ArmUIState.SELECTING_ACTION)
    
    def _tick_selecting_action(self, world) -> None:
        """Tick SELECTING_ACTION state: compute proposal."""
        if self.active_target_id is None:
            self._transition_to(ArmUIState.IDLE)
            return
        
        # Compute available actions
        available = world.get_available_actions()
        
        if not available:
            self._log_event("No actions available for target")
            self.active_proposal = None
            return
        
        # Propose next action
        proposed_action = world.propose_next_action()
        
        if proposed_action is None:
            self._log_event("No proposal generated")
            self.active_proposal = None
            return
        
        # Create proposal
        self.active_proposal = ArmProposal(
            target_object_id=self.active_target_id,
            action_type=proposed_action,
            reason=world.get_action_reason(proposed_action),
            available_actions=available,
            timestamp=time.time()
        )
        
        self._log_event(f"Proposed: {proposed_action}")
        
        # AUTO-CONFIRM GRASP: If proposal is GRASP_OBJECT, execute immediately
        if proposed_action == ArmActionType.GRASP_OBJECT:
            self._log_event(f"Auto-confirming GRASP action (no user confirmation needed)")
            self.executing_action = proposed_action
            self.execution_started_at = time.time()
            self.execution_last_progress = 0.0
            self._transition_to(ArmUIState.EXECUTING)
            self.cooldown_frames = 5  # Debounce
        else:
            # Normal behavior: wait for user confirmation
            self._transition_to(ArmUIState.AWAITING_CONFIRM)
    
    def _tick_awaiting_confirm(self, decision: ArmDecision, controller=None) -> None:
        """Tick AWAITING_CONFIRM state: wait for user decision."""
        print(f"\n[DBG _tick_awaiting_confirm] Entry:")
        print(f"  Decision: {decision}")
        print(f"  Decision.signal: {decision.signal if hasattr(decision, 'signal') else 'NO SIGNAL'}")
        print(f"  Checking if decision.signal == DecisionSignal.CONFIRM...")
        print(f"  DecisionSignal.CONFIRM value: {DecisionSignal.CONFIRM}")
        print(f"  Comparison result: {decision.signal == DecisionSignal.CONFIRM if hasattr(decision, 'signal') else 'NO SIGNAL ATTR'}")
        print(f"  Cooldown frames: {self.cooldown_frames}")
        
        if self.cooldown_frames > 0:
            print(f"[DBG _tick_awaiting_confirm] Cooldown active, returning")
            return  # Prevent double-trigger
        
        # DEFENSIVE: Check if proposal exists
        if self.active_proposal is None:
            print("[DBG _tick_awaiting_confirm] ⚠️ No proposal, returning to SELECTING")
            self._transition_to(ArmUIState.SELECTING_ACTION)
            return
        
        # Week 7: Only process decisions if signal is stable
        # (stability check happens in tick(), not here)
        
        if decision.signal == DecisionSignal.CONFIRM:
            print(f"[DBG _tick_awaiting_confirm] ★★★ CONFIRM MATCHED ★★★")
            self._log_event(f"CONFIRMED: {self.active_proposal.action_type}")
            self.executing_action = self.active_proposal.action_type
            self.execution_started_at = time.time()
            self.execution_last_progress = 0.0
            self._transition_to(ArmUIState.EXECUTING)
            self.cooldown_frames = 5  # Debounce
        
        elif decision.signal == DecisionSignal.CANCEL:
            self._log_event(f"CANCELLED: {self.active_proposal.action_type}")
            self.active_proposal = None
            self._transition_to(ArmUIState.SELECTING_ACTION)
            self.cooldown_frames = 5  # Debounce
    
    def _tick_executing(self, controller) -> None:
        """
        Tick EXECUTING state: monitor controller until done.
        
        Week 5: Multi-frame execution (not instant).
        Supports cancellation mid-execution.
        
        Args:
            controller: ArmController instance (passed from orchestrator)
        """
        # Controller reports completion via orchestrator (not here)
        # State machine just waits in EXECUTING until orchestrator transitions it
        pass
    
    def _tick_done(self) -> None:
        """Tick DONE state: wait for next cycle."""
        # Auto-return to selecting after cooldown
        if self.cooldown_frames == 0:
            if self.active_target_id is not None and self.target_locked:
                self._log_event("Ready for next action")
                self.active_proposal = None
                self._transition_to(ArmUIState.SELECTING_ACTION)
                self.cooldown_frames = 10  # Brief pause before next proposal
            else:
                self._transition_to(ArmUIState.IDLE)
    
    def _tick_paused(self) -> None:
        """
        Tick PAUSED state: wait for recovery conditions.
        
        Week 8: Never auto-resume, requires explicit recovery completion.
        """
        # Check if recovery conditions are met
        if self.recovery_conditions_met:
            if not self.in_recovery:
                self._log_event("Recovery conditions met → RECOVERING")
                self.in_recovery = True
            
            # In recovery - check if target unlocked (user re-scoping)
            if self.active_target_id is None or not self.target_locked:
                # Target cleared - transition back to IDLE
                self._log_event("Recovery complete → IDLE")
                self._transition_to(ArmUIState.IDLE)
                self.in_recovery = False
                self.recovery_conditions_met = False
                self.eeg_unstable_frames = 0
    
    def _transition_to(self, new_state: ArmUIState) -> None:
        """
        Transition to new state.
        
        Args:
            new_state: Target state
        """
        if new_state != self.state:
            old_state = self.state
            self._log_event(f"State: {self.state} → {new_state}")
            # PATCH 7: Console logging for state transitions
            print(f"[STATE] {old_state.value} → {new_state.value}")
            self.state = new_state
    
    def reset(self) -> None:
        """Reset state machine to initial state."""
        self.state = ArmUIState.IDLE
        self.active_target_id = None
        self.target_locked = False
        self.active_proposal = None
        self.last_event = "reset"
        self.cooldown_frames = 0
        self.eeg_unstable_frames = 0
        self.in_recovery = False
        self.recovery_conditions_met = False
        self._log_event("State machine reset")
    
    def finish_execution(self, result) -> None:
        """
        Mark execution as complete (called by orchestrator).
        
        Args:
            result: ExecutionResult from controller
        """
        if result.success:
            self._log_event(f"EXECUTION SUCCESS: {result.reason}")
            self._transition_to(ArmUIState.DONE)
        else:
            self._log_event(f"EXECUTION FAILED: {result.reason}")
            # Return to selecting on failure
            self.active_proposal = None
            self._transition_to(ArmUIState.SELECTING_ACTION)
        
        self.executing_action = None
        self.execution_last_progress = 0.0
    
    def cancel_execution(self, controller) -> None:
        """
        Cancel execution in progress (called when X pressed during EXECUTING).
        
        Args:
            controller: ArmController instance
        """
        if self.state == ArmUIState.EXECUTING and controller is not None:
            self._log_event("USER CANCELLED EXECUTION")
            controller.cancel()
            # Wait for controller to finish cancellation, then orchestrator calls finish_execution
    
    def check_eeg_stability(self, eeg_meta: Optional[dict], recovery_status: Optional[dict] = None) -> bool:
        """
        Check if EEG signal is stable enough for decisions.
        
        Args:
            eeg_meta: EEG debug status from decision source
            recovery_status: Recovery controller status
            
        Returns:
            True if stable (or no EEG)
        """
        # If in PAUSED state, don't check stability (handled by recovery controller)
        if self.state == ArmUIState.PAUSED:
            return False
        
        if eeg_meta is None:
            return True  # No EEG = keyboard mode, always stable
        
        # Check if blocked
        if eeg_meta.get('blocked', False):
            self.eeg_unstable_frames += 1
            
            # Log instability
            if self.eeg_unstable_frames == 1:
                reason = eeg_meta.get('reason', 'unknown')
                self._log_event(f"EEG unstable: {reason}")
            
            return False
        else:
            # Reset counter when stable
            if self.eeg_unstable_frames > 0:
                self._log_event("EEG signal restored")
                self.eeg_unstable_frames = 0
            return True
    
    def trigger_pause(self, trigger_name: str) -> None:
        """
        Trigger pause state.
        
        Args:
            trigger_name: Pause trigger identifier
        """
        if self.state != ArmUIState.PAUSED:
            self._log_event(f"Pause triggered: {trigger_name}")
            self.active_proposal = None  # Clear proposal
            self.in_recovery = False
            self.recovery_conditions_met = False
            self._transition_to(ArmUIState.PAUSED)
    
    def check_recovery_ready(self, recovery_ready: bool) -> None:
        """
        Update recovery readiness.
        
        Args:
            recovery_ready: Whether recovery conditions are met
        """
        if self.state == ArmUIState.PAUSED:
            self.recovery_conditions_met = recovery_ready
    
    def get_snapshot(self) -> dict:
        """
        Get current state snapshot for UI/logging.
        
        Returns:
            Dict with state, proposal, target info
        """
        return {
            "state": str(self.state),
            "target_id": self.active_target_id,
            "target_locked": self.target_locked,
            "proposal": {
                "action": str(self.active_proposal.action_type) if self.active_proposal else None,
                "reason": self.active_proposal.reason if self.active_proposal else None,
                "available": [str(a) for a in self.active_proposal.available_actions] if self.active_proposal else [],
            } if self.active_proposal else None,
            "last_event": self.last_event,
            "cooldown": self.cooldown_frames,
        }

