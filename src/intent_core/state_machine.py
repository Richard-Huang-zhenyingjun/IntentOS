"""
State Machine - Manage system state transitions (ENHANCED Week 8)

Handles normal operation, undo flow, pause/recovery, and execution permission.

Week 5: Undo flow
Week 7: PAUSED state support
Week 8: RECOVERING state, structured recovery, comprehensive safety
"""

from typing import Optional, List
import logging
from intent_core.schema import SystemState, Intent, IntentType, SystemContext
from execution.undo_controller import UndoController

# Import RecoveryPlan if available
try:
    from src.vision.recovery_controller import RecoveryPlan, RecoveryAction
except ImportError:
    RecoveryPlan = None
    RecoveryAction = None

logger = logging.getLogger(__name__)


class StateMachine:
    """
    Intent state machine (ENHANCED Week 8)
    
    State Flow:
    - Normal: IDLE → SCOPED → CONFIRMING → EXECUTING → SCOPED
    - Undo: SCOPED → UNDO_CONFIRMING → EXECUTING (undo) → SCOPED
    - Pause & Recovery: Any → PAUSED → RECOVERING → SCOPED (NEW Week 8)
    
    New Week 8 Features:
    - PAUSED state blocks all execution
    - RECOVERING state requires validation
    - SystemContext tracks pause/recovery state
    - Recovery actions must be completed
    
    Safety Guarantees:
    - Cannot execute from PAUSED
    - Cannot skip recovery validation
    - Undo cleared on pause (configurable)
    """
    
    def __init__(self, config: dict, undo_controller: Optional[UndoController] = None):
        self.config = config
        self.undo_controller = undo_controller
        
        # Current state
        self.current_state = SystemState.IDLE
        
        # NEW Week 8: System context
        self.context = SystemContext()
        
        # Track scope changes for auto-cancel undo
        self.last_scoped_object_id: Optional[str] = None
        
        # Execution flag (set when execution is allowed)
        self.execution_allowed = False
        
        # Recovery tracking (NEW Week 8)
        self.recovery_actions_needed: List[str] = []
        self.recovery_actions_completed: List[str] = []
        
        # Statistics
        self.state_transitions = []
        self.total_transitions = 0
    
    def update(self,
               intent: Optional[Intent] = None,
               scoped_object_id: Optional[str] = None,
               timestamp: float = 0.0,
               recovery_plan: Optional['RecoveryPlan'] = None,
               confidence_stable: bool = True,
               ambiguity: bool = False) -> SystemState:
        """
        Update state machine with new intent (ENHANCED Week 8)
        
        Args:
            intent: User intent (or None)
            scoped_object_id: Current scoped object ID
            timestamp: Current timestamp
            recovery_plan: RecoveryPlan from RecoveryController (NEW Week 8)
            confidence_stable: Whether scope is stable (NEW Week 8)
            ambiguity: Whether ambiguity detected (NEW Week 8)
        
        Returns:
            New system state
        """
        old_state = self.current_state
        
        # === PAUSE HANDLING (NEW Week 8) ===
        if recovery_plan and recovery_plan.should_pause:
            new_state = self._handle_pause(recovery_plan)
            if new_state != old_state:
                self._log_transition(old_state, new_state, "pause_triggered")
            return new_state
        
        # === PAUSED STATE RESTRICTIONS (NEW Week 8) ===
        if self.current_state == SystemState.PAUSED:
            new_state = self._handle_paused_state(intent, timestamp)
            if new_state != old_state:
                self._log_transition(old_state, new_state, "from_paused")
            return new_state
        
        # === RECOVERING STATE (NEW Week 8) ===
        if self.current_state == SystemState.RECOVERING:
            new_state = self._handle_recovering_state(
                intent, confidence_stable, ambiguity, timestamp
            )
            if new_state != old_state:
                self._log_transition(old_state, new_state, "recovery_transition")
            return new_state
        
        # === NORMAL STATE TRANSITIONS (Week 1-7) ===
        
        # Check for scope changes (auto-cancel undo)
        scope_changed = False
        if scoped_object_id != self.last_scoped_object_id:
            scope_changed = True
            self.last_scoped_object_id = scoped_object_id
        
        # Auto-cancel undo if scope changes
        if self.current_state == SystemState.UNDO_CONFIRMING and scope_changed:
            if self.undo_controller:
                self.undo_controller.cancel_undo()
            self.current_state = SystemState.IDLE
            self._log_transition(old_state, self.current_state, "scope_changed")
            return self.current_state
        
        # Handle intents
        if intent is None:
            return self.current_state
        
        new_state = self.current_state
        
        # Route intent to appropriate handler
        if intent.type == IntentType.UNDO_REQUEST:
            new_state = self.handle_undo_request(intent, timestamp)
        elif intent.type == IntentType.UNDO_CONFIRM:
            new_state = self.handle_undo_confirm(intent, timestamp)
        elif intent.type == IntentType.UNDO_CANCEL:
            new_state = self.handle_undo_cancel(intent)
        elif intent.type == IntentType.RECOVERY_START:  # NEW Week 8
            new_state = self.handle_recovery_start(intent)
        elif intent.type == IntentType.RECOVERY_COMPLETE:  # NEW Week 8
            new_state = self.handle_recovery_complete(intent)
        elif intent.type == IntentType.SELECT:
            new_state = self.handle_select(intent, scoped_object_id)
        elif intent.type == IntentType.CONFIRM:
            new_state = self.handle_confirm(intent)
        elif intent.type == IntentType.CANCEL:
            new_state = self.handle_cancel(intent)
        elif intent.type == IntentType.IDLE:
            new_state = self.handle_idle(intent)
        
        # Update state
        if new_state != self.current_state:
            self._log_transition(old_state, new_state, intent.type.value)
            self.current_state = new_state
        
        return self.current_state
    
    def _handle_pause(self, recovery_plan: 'RecoveryPlan') -> SystemState:
        """
        Handle pause trigger (NEW Week 8)
        
        Actions:
        - Transition to PAUSED
        - Store pause context in SystemContext
        - Clear execution flag
        - Set recovery requirements
        - Clear undo if configured
        
        Args:
            recovery_plan: Plan from RecoveryController
        
        Returns:
            PAUSED state
        """
        # Store pause context
        self.context.pause_trigger = recovery_plan.trigger.value if recovery_plan.trigger else None
        self.context.pause_reason = recovery_plan.reason
        self.context.pause_timestamp = recovery_plan.timestamp
        
        # Set recovery requirements
        self.context.recovery_required = True
        self.context.recovery_instructions = recovery_plan.recovery_explanation.split('\n')
        self.recovery_actions_needed = [
            action.value for action in recovery_plan.recovery_actions
        ]
        self.recovery_actions_completed = []
        
        # Clear execution permission (CRITICAL)
        self.execution_allowed = False
        
        # Clear undo if specified
        if recovery_plan.clear_undo:
            self.context.undo_available = False
            self.context.undo_expires_at = None
            self.context.undo_action_id = None
        
        # Transition to PAUSED
        logger.info(f"System PAUSED: {recovery_plan.reason}")
        return SystemState.PAUSED
    
    def _handle_paused_state(self, intent: Optional[Intent], timestamp: float) -> SystemState:
        """
        Handle intents while in PAUSED state (NEW Week 8)
        
        Allowed intents:
        - SELECT: Starts recovery by scoping new object
        - CANCEL: Give up and return to IDLE
        - UNDO_REQUEST: Allow if undo available (and not cleared)
        - RECOVERY_START: Explicit recovery initiation
        
        Blocked intents:
        - CONFIRM: Must recover first
        - All execution-related intents
        
        Args:
            intent: Current intent
            timestamp: Current timestamp
        
        Returns:
            New state (PAUSED, RECOVERING, IDLE, or UNDO_CONFIRMING)
        """
        if intent is None:
            return SystemState.PAUSED
        
        # RECOVERY_START: Explicit recovery
        if intent.type == IntentType.RECOVERY_START:
            return self.handle_recovery_start(intent)
        
        # SELECT: New scope attempt (starts recovery)
        if intent.type == IntentType.SELECT:
            logger.info("Starting recovery via new scope")
            self.context.recovery_steps_completed = []
            return SystemState.RECOVERING
        
        # CANCEL: Give up recovery
        if intent.type == IntentType.CANCEL:
            logger.info("Recovery cancelled - returning to IDLE")
            self._clear_pause_context()
            return SystemState.IDLE
        
        # UNDO_REQUEST: Allow if undo available
        if intent.type == IntentType.UNDO_REQUEST:
            if self.context.undo_available:
                if self.undo_controller and self.undo_controller.is_undo_available(timestamp):
                    logger.info("Undo requested from PAUSED state")
                    return SystemState.UNDO_CONFIRMING
        
        # All other intents blocked
        logger.debug(f"Intent {intent.type.value} blocked in PAUSED state")
        return SystemState.PAUSED
    
    def _handle_recovering_state(self,
                                 intent: Optional[Intent],
                                 confidence_stable: bool,
                                 ambiguity: bool,
                                 timestamp: float) -> SystemState:
        """
        Handle recovery process (NEW Week 8)
        
        Recovery steps:
        1. Re-establish scope (stable, no ambiguity)
        2. Wait for confirmation readiness
        3. Validate recovery complete
        4. Transition to SCOPED
        
        Args:
            intent: Current intent
            confidence_stable: Whether scope is stable
            ambiguity: Whether ambiguity detected
            timestamp: Current timestamp
        
        Returns:
            New state (RECOVERING, PAUSED, or SCOPED)
        """
        # Check for recovery completion intent
        if intent and intent.type == IntentType.RECOVERY_COMPLETE:
            return self.handle_recovery_complete(intent)
        
        # Check for cancel
        if intent and intent.type == IntentType.CANCEL:
            logger.info("Recovery cancelled - back to PAUSED")
            return SystemState.PAUSED
        
        # Automatic recovery validation
        # Check if scope is stable
        if not confidence_stable:
            # Scope not stable yet - stay in RECOVERING
            logger.debug("Recovery waiting for stable scope")
            return SystemState.RECOVERING
        
        # Check for ambiguity (failure during recovery)
        if ambiguity:
            # Ambiguity during recovery - back to PAUSED
            logger.warning("Ambiguity during recovery - back to PAUSED")
            self.context.pause_reason = "Ambiguity appeared during recovery"
            return SystemState.PAUSED
        
        # Scope is stable and clear
        # Mark rescope action as complete
        if 'rescope_object' in self.recovery_actions_needed:
            if 'rescope_object' not in self.recovery_actions_completed:
                self.recovery_actions_completed.append('rescope_object')
                self.context.recovery_steps_completed.append('rescope_object')
        
        # Check if all recovery actions completed
        all_complete = all(
            action in self.recovery_actions_completed
            for action in self.recovery_actions_needed
        )
        
        if all_complete:
            # Recovery complete - transition to SCOPED
            logger.info("Recovery complete - transitioning to SCOPED")
            self._clear_pause_context()
            return SystemState.SCOPED
        
        # Still have actions to complete - stay in RECOVERING
        logger.debug(f"Recovery in progress: {len(self.recovery_actions_completed)}/{len(self.recovery_actions_needed)} actions done")
        return SystemState.RECOVERING
    
    def handle_recovery_start(self, intent: Intent) -> SystemState:
        """
        Handle RECOVERY_START intent (NEW Week 8)
        
        Transitions:
        - From PAUSED → RECOVERING
        """
        if self.current_state == SystemState.PAUSED:
            logger.info("Recovery started")
            self.recovery_actions_completed = []
            self.context.recovery_steps_completed = []
            return SystemState.RECOVERING
        
        return self.current_state
    
    def handle_recovery_complete(self, intent: Intent) -> SystemState:
        """
        Handle RECOVERY_COMPLETE intent (NEW Week 8)
        
        Validates recovery and transitions to SCOPED if complete.
        
        Transitions:
        - From RECOVERING → SCOPED (if validated)
        - Otherwise → stay in RECOVERING
        """
        if self.current_state != SystemState.RECOVERING:
            return self.current_state
        
        # Validate all recovery actions completed
        all_complete = all(
            action in self.recovery_actions_completed
            for action in self.recovery_actions_needed
        )
        
        if all_complete:
            logger.info("Recovery validated - transitioning to SCOPED")
            self._clear_pause_context()
            return SystemState.SCOPED
        else:
            missing = [
                action for action in self.recovery_actions_needed
                if action not in self.recovery_actions_completed
            ]
            logger.warning(f"Recovery incomplete: missing actions {missing}")
            return SystemState.RECOVERING
    
    def _clear_pause_context(self):
        """Clear pause/recovery context (NEW Week 8)"""
        self.context.pause_trigger = None
        self.context.pause_reason = None
        self.context.pause_timestamp = None
        self.context.recovery_required = False
        self.context.recovery_steps_completed = []
        self.context.recovery_instructions = []
        self.recovery_actions_needed = []
        self.recovery_actions_completed = []
    
    def transition_to(self, new_state: SystemState, reason: str = "forced"):
        """
        Force state transition (ENHANCED Week 8)
        
        Used by orchestrator for direct state changes.
        Validates transition safety.
        
        Args:
            new_state: Target state
            reason: Reason for transition
        
        Raises:
            ValueError: If transition violates safety rules
        """
        old_state = self.current_state
        
        # Validate critical safety rules
        if new_state == SystemState.EXECUTING and self.current_state == SystemState.PAUSED:
            # CRITICAL: Cannot execute from PAUSED
            raise ValueError("Cannot execute from PAUSED state - recovery required")
        
        if new_state == SystemState.EXECUTING and self.current_state == SystemState.RECOVERING:
            # CRITICAL: Cannot execute during recovery
            raise ValueError("Cannot execute during RECOVERING - must complete recovery first")
        
        if new_state == SystemState.PAUSED:
            # Ensure execution is blocked
            self.execution_allowed = False
        
        # Log transition
        if new_state != old_state:
            self._log_transition(old_state, new_state, reason)
        
        self.current_state = new_state
    
    def can_execute(self) -> tuple[bool, str]:
        """
        Check if execution is allowed (ENHANCED Week 8)
        
        Checks:
        - State machine execution flag
        - Current state restrictions
        - Pause/recovery status
        
        Returns:
            (allowed, reason) tuple
        """
        if self.current_state == SystemState.PAUSED:
            return (False, "System is paused - recovery required")
        
        if self.current_state == SystemState.RECOVERING:
            return (False, "Recovery in progress - cannot execute")
        
        if not self.execution_allowed:
            return (False, "Execution not allowed by state machine")
        
        if self.context.recovery_required:
            return (False, "Recovery required before execution")
        
        return (True, "Execution allowed")
    
    def complete_recovery_action(self, action: str):
        """
        Mark a recovery action as completed (NEW Week 8)
        
        Args:
            action: Action name (e.g., 'rescope_object', 'reconfirm_action')
        """
        if action not in self.recovery_actions_completed:
            self.recovery_actions_completed.append(action)
            self.context.recovery_steps_completed.append(action)
            logger.debug(f"Recovery action completed: {action}")
    
    # === EXISTING HANDLERS (Week 1-7) ===
    
    def handle_undo_request(self, intent: Intent, timestamp: float) -> SystemState:
        """
        Handle UNDO_REQUEST intent
        
        Transitions:
        - From IDLE/SCOPED → UNDO_CONFIRMING (if undo available)
        - Otherwise → stay in current state
        """
        # Only allow from IDLE or SCOPED
        if self.current_state not in [SystemState.IDLE, SystemState.SCOPED]:
            logger.debug(f"Undo request refused: current state is {self.current_state.value}")
            return self.current_state
        
        # Check if undo available (via UndoController)
        if self.undo_controller:
            if self.undo_controller.is_undo_available(timestamp):
                success, reason = self.undo_controller.request_undo(timestamp)
                if success:
                    logger.info(f"Undo requested: {reason}")
                    return SystemState.UNDO_CONFIRMING
                else:
                    logger.debug(f"Undo request failed: {reason}")
                    return self.current_state
            else:
                logger.debug("Undo request refused: no undo available")
                return self.current_state
        else:
            logger.warning("Undo request refused: no undo controller")
            return self.current_state
    
    def handle_undo_confirm(self, intent: Intent, timestamp: float) -> SystemState:
        """
        Handle UNDO_CONFIRM intent
        
        Transitions:
        - From UNDO_CONFIRMING → EXECUTING (undo execution)
        """
        if self.current_state == SystemState.UNDO_CONFIRMING:
            if self.undo_controller:
                result = self.undo_controller.confirm_undo(timestamp)
                if result.ok:
                    logger.info(f"Undo confirmed and executed: {result.reason}")
                    return SystemState.EXECUTING
                else:
                    logger.warning(f"Undo confirmation failed: {result.reason}")
                    return SystemState.IDLE
            else:
                logger.warning("Undo confirm refused: no undo controller")
                return SystemState.IDLE
        
        return self.current_state
    
    def handle_undo_cancel(self, intent: Intent) -> SystemState:
        """
        Handle UNDO_CANCEL intent or automatic cancellation
        
        Transitions:
        - From UNDO_CONFIRMING → IDLE
        """
        if self.current_state == SystemState.UNDO_CONFIRMING:
            if self.undo_controller:
                self.undo_controller.cancel_undo()
            logger.info("Undo cancelled")
            return SystemState.IDLE
        
        return self.current_state
    
    def handle_select(self, intent: Intent, scoped_object_id: Optional[str]) -> SystemState:
        """Handle SELECT intent"""
        if scoped_object_id:
            return SystemState.SCOPED
        return SystemState.IDLE
    
    def handle_confirm(self, intent: Intent) -> SystemState:
        """Handle CONFIRM intent"""
        if self.current_state == SystemState.SCOPED:
            self.execution_allowed = True
            # Mark reconfirm action as complete if in recovery
            if 'reconfirm_action' in self.recovery_actions_needed:
                self.complete_recovery_action('reconfirm_action')
            return SystemState.CONFIRMING
        return self.current_state
    
    def handle_cancel(self, intent: Intent) -> SystemState:
        """Handle CANCEL intent"""
        self.execution_allowed = False
        if self.current_state == SystemState.UNDO_CONFIRMING:
            return self.handle_undo_cancel(intent)
        return SystemState.IDLE
    
    def handle_idle(self, intent: Intent) -> SystemState:
        """Handle IDLE intent"""
        self.execution_allowed = False
        return SystemState.IDLE
    
    def _log_transition(self, old_state: SystemState, new_state: SystemState, reason: str):
        """Log state transition"""
        self.total_transitions += 1
        self.state_transitions.append({
            'from': old_state.value,
            'to': new_state.value,
            'reason': reason
        })
        # Keep only last 100 transitions
        if len(self.state_transitions) > 100:
            self.state_transitions.pop(0)
        logger.debug(f"State transition: {old_state.value} → {new_state.value} ({reason})")
    
    def get_statistics(self) -> dict:
        """Get state machine statistics"""
        return {
            'current_state': self.current_state.value,
            'total_transitions': self.total_transitions,
            'execution_allowed': self.execution_allowed,
            'recovery_required': self.context.recovery_required,
            'pause_reason': self.context.pause_reason
        }
