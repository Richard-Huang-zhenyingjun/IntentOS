"""
Undo Controller - Manage undo with full safety (ENHANCED Week 8)

Provides symmetric undo flow with same rigor as initial execution.
Comprehensive safety checks and state validation.

Week 5: Basic undo with confirmation
Week 8: Symmetric to execution, comprehensive safety, pause-aware
"""

from typing import Optional, Tuple, Dict
from execution.action_history import ActionHistory, ActionRecord
from execution.smart_world_sim import SmartWorldSim
from execution.action_schema import ExecutionResult
from intent_core.schema import SystemState
import uuid


class UndoController:
    """
    Manage undo with full safety (ENHANCED Week 8)
    
    Responsibilities:
    - Check if undo is available (state-aware)
    - Validate undo requests (comprehensive checks)
    - Apply undo via SmartWorldSim (symmetric to execution)
    - Require explicit confirmation (no automatic undo)
    - Track refusal reasons (for debugging)
    
    Design Principle:
    "Undo is as rigorous as initial execution"
    
    Week 5: Basic undo with confirmation
    Week 8: Symmetric to execution, comprehensive safety checks, pause-aware
    
    Safety Guarantees:
    - Cannot undo from PAUSED state
    - Cannot undo from RECOVERING state
    - Cannot undo during EXECUTING
    - Cannot undo during CONFIRMING
    - Must re-confirm if state changes
    - Undos themselves not reversible (no redo in Week 8)
    """
    
    def __init__(self,
                 config: dict,
                 history: ActionHistory,
                 world: SmartWorldSim):
        self.config = config
        self.history = history
        self.world = world
        
        # Config
        self.enabled = config.get('enabled', True)
        self.require_confirmation = config.get('require_confirmation', True)
        self.block_during_pause = config.get('block_during_pause', True)  # NEW Week 8
        
        # State
        self.undo_requested = False
        self.requested_action: Optional[ActionRecord] = None
        self.request_timestamp: Optional[float] = None
        
        # Statistics (ENHANCED Week 8)
        self.total_undo_requests = 0
        self.total_undo_confirmations = 0
        self.total_undo_refusals = 0
        self.undo_refusal_reasons: Dict[str, int] = {}  # Track why undos refused
    
    def is_undo_available(self,
                         current_time: float,
                         system_state: Optional[SystemState] = None,
                         user_id: Optional[str] = None,
                         session_id: Optional[str] = None) -> bool:
        """
        Check if undo is available (ENHANCED Week 8)
        
        New checks:
        - System not in PAUSED state
        - System not in RECOVERING state
        - System not in EXECUTING state
        - System not in CONFIRMING state
        
        Args:
            current_time: Current timestamp
            system_state: Current system state (NEW Week 8)
            user_id: Optional user filter
            session_id: Optional session filter (NEW Week 8)
        
        Returns:
            True if undo available, False otherwise
        """
        if not self.enabled:
            return False
        
        # NEW Week 8: Block during pause/recovery
        if self.block_during_pause and system_state:
            if system_state in [SystemState.PAUSED, SystemState.RECOVERING]:
                return False
            if system_state in [SystemState.EXECUTING, SystemState.CONFIRMING]:
                return False
        
        # Check history for reversible action
        last = self.history.last_reversible(current_time, user_id, session_id)
        return last is not None
    
    def request_undo(self,
                    current_time: float,
                    system_state: SystemState,
                    user_id: Optional[str] = None,
                    session_id: Optional[str] = None) -> Tuple[bool, str]:
        """
        Request undo (ENHANCED Week 8)
        
        Validates:
        - Undo available
        - Not expired
        - Not in PAUSED/RECOVERING state
        - Not in EXECUTING/CONFIRMING state
        - Not already in UNDO_CONFIRMING state
        
        Args:
            current_time: Current timestamp
            system_state: Current system state (NEW Week 8)
            user_id: User requesting undo
            session_id: Session requesting undo (NEW Week 8)
        
        Returns:
            (success, reason) tuple
        """
        self.total_undo_requests += 1
        
        # Check if already in undo flow
        if self.undo_requested:
            return self._refuse("Undo already requested - confirm or cancel first")
        
        # Check system state (ENHANCED Week 8)
        if system_state == SystemState.PAUSED:
            return self._refuse("Cannot undo while system is paused - recovery required")
        
        if system_state == SystemState.RECOVERING:
            return self._refuse("Cannot undo while recovering - complete recovery first")
        
        if system_state == SystemState.EXECUTING:
            return self._refuse("Cannot undo while executing action")
        
        if system_state == SystemState.CONFIRMING:
            return self._refuse("Cannot undo while confirming action")
        
        if system_state == SystemState.UNDO_CONFIRMING:
            return self._refuse("Already in undo confirmation state")
        
        # Check if undo available
        last = self.history.last_reversible(current_time, user_id, session_id)
        
        if last is None:
            return self._refuse("No reversible action available")
        
        # Validate can undo (uses ActionRecord.can_undo)
        can_undo, reason = last.can_undo(current_time)
        if not can_undo:
            return self._refuse(reason)
        
        # Success - enter UNDO_CONFIRMING state
        self.undo_requested = True
        self.requested_action = last
        self.request_timestamp = current_time
        
        time_remaining = last.expires_at - current_time
        
        return (True, 
                f"Undo ready: {last.action_type} on {last.object_label} "
                f"(expires in {time_remaining:.1f}s)")
    
    def confirm_undo(self,
                    current_time: float,
                    system_state: SystemState,
                    user_id: Optional[str] = None,
                    session_id: Optional[str] = None) -> ExecutionResult:
        """
        Confirm and execute undo (ENHANCED Week 8)
        
        Symmetric to action execution:
        - Validate state (comprehensive)
        - Check permissions (if multi-user)
        - Execute via world simulator
        - Record in history (mark as undone)
        - Return ExecutionResult (consistent interface)
        
        Args:
            current_time: Current timestamp
            system_state: Current system state (NEW Week 8)
            user_id: User confirming undo
            session_id: Session confirming undo (NEW Week 8)
        
        Returns:
            ExecutionResult (ok=True if undone successfully)
        """
        self.total_undo_confirmations += 1
        
        # Must have requested first
        if not self.undo_requested or self.requested_action is None:
            return self._refuse_execution(
                "No undo request active - request undo first",
                current_time,
                error_code="NO_UNDO_REQUEST"
            )
        
        # Validate system state (ENHANCED Week 8)
        valid_states = [SystemState.UNDO_CONFIRMING, SystemState.SCOPED, SystemState.IDLE]
        if system_state not in valid_states:
            self._cancel_undo()
            return self._refuse_execution(
                f"Cannot undo from {system_state.value} state - must be in "
                f"{[s.value for s in valid_states]}",
                current_time,
                error_code="INVALID_STATE",
                error_details={'system_state': system_state.value}
            )
        
        # Check if still valid (may have expired during confirmation)
        can_undo, reason = self.requested_action.can_undo(current_time)
        if not can_undo:
            self._cancel_undo()
            return self._refuse_execution(
                f"Undo no longer valid: {reason}",
                current_time,
                error_code="UNDO_INVALID",
                error_details={'validation_reason': reason}
            )
        
        # Execute undo (symmetric to execution)
        try:
            before_undo, after_undo = self.world.apply_undo(
                object_id=self.requested_action.object_id,
                before_state=self.requested_action.before_state,
                timestamp=current_time
            )
            
            # Generate undo action ID (NEW Week 8)
            undo_action_id = f"undo_{uuid.uuid4().hex[:8]}"
            
            # Mark as undone in history (ENHANCED Week 8)
            self.history.mark_undone(
                action_id=self.requested_action.action_id,
                timestamp=current_time,
                undo_action_id=undo_action_id,
                session_id=session_id
            )
            
            # Store details for result
            undone_action_id = self.requested_action.action_id
            undone_object_label = self.requested_action.object_label
            undone_action_type = self.requested_action.action_type
            
            # Clear request
            self._cancel_undo()
            
            return ExecutionResult(
                ok=True,
                before_state=before_undo,
                after_state=after_undo,
                reason=f"Undid {undone_action_type} on {undone_object_label}",
                reversible=False,  # Undos themselves are not reversible (no redo in Week 8)
                action_id=undo_action_id,
                timestamp=current_time
            )
        
        except Exception as e:
            self._cancel_undo()
            return self._refuse_execution(
                f"Undo execution error: {str(e)}",
                current_time,
                error_code="UNDO_ERROR",
                error_details={
                    'exception': str(e),
                    'action_id': self.requested_action.action_id if self.requested_action else None
                }
            )
    
    def cancel_undo(self, reason: str = "User cancelled"):
        """
        Cancel undo request (user-initiated or system-initiated)
        
        Args:
            reason: Why undo was cancelled
        """
        if self.undo_requested:
            self._cancel_undo()
    
    def _cancel_undo(self):
        """Internal cancel (clear state)"""
        self.undo_requested = False
        self.requested_action = None
        self.request_timestamp = None
    
    def _refuse(self, reason: str) -> Tuple[bool, str]:
        """
        Helper for request refusal (NEW Week 8)
        
        Tracks refusal reasons for statistics.
        
        Args:
            reason: Why undo was refused
        
        Returns:
            (False, reason) tuple
        """
        self.total_undo_refusals += 1
        self.undo_refusal_reasons[reason] = self.undo_refusal_reasons.get(reason, 0) + 1
        return (False, reason)
    
    def _refuse_execution(self,
                         reason: str,
                         timestamp: float,
                         error_code: str,
                         error_details: Optional[Dict] = None) -> ExecutionResult:
        """
        Helper for execution refusal (NEW Week 8)
        
        Returns ExecutionResult for consistency with execution path.
        
        Args:
            reason: Why execution was refused
            timestamp: Current timestamp
            error_code: Machine-readable error code
            error_details: Additional error details
        
        Returns:
            ExecutionResult with ok=False
        """
        self.total_undo_refusals += 1
        self.undo_refusal_reasons[error_code] = self.undo_refusal_reasons.get(error_code, 0) + 1
        
        return ExecutionResult(
            ok=False,
            before_state=None,
            after_state=None,
            reason=reason,
            reversible=False,
            action_id="undo_refused",
            timestamp=timestamp,
            error_code=error_code,
            error_details=error_details or {}
        )
    
    def get_undo_info(self, current_time: float) -> Optional[Dict]:
        """
        Get info about available/requested undo (ENHANCED Week 8)
        
        Provides complete undo state for UI display.
        
        Args:
            current_time: Current timestamp
        
        Returns:
            Dictionary with undo info or None if no undo available
        """
        # Check if undo requested (awaiting confirmation)
        if self.undo_requested and self.requested_action:
            remaining = self.requested_action.expires_at - current_time
            return {
                'available': True,
                'requested': True,
                'confirming': True,
                'action_id': self.requested_action.action_id,
                'object_id': self.requested_action.object_id,
                'object_label': self.requested_action.object_label,
                'action_type': self.requested_action.action_type,
                'time_remaining': max(0.0, remaining),
                'expired': remaining <= 0.0
            }
        
        # Check if undo available (not yet requested)
        last = self.history.last_reversible(current_time)
        if last:
            remaining = last.expires_at - current_time
            return {
                'available': True,
                'requested': False,
                'confirming': False,
                'action_id': last.action_id,
                'object_id': last.object_id,
                'object_label': last.object_label,
                'action_type': last.action_type,
                'time_remaining': max(0.0, remaining),
                'expired': remaining <= 0.0
            }
        
        # No undo available
        return None
    
    def get_statistics(self) -> Dict:
        """
        Get undo statistics (ENHANCED Week 8)
        
        Returns:
            Dictionary with comprehensive undo metrics
        """
        return {
            'enabled': self.enabled,
            'total_undo_requests': self.total_undo_requests,
            'total_undo_confirmations': self.total_undo_confirmations,
            'total_undo_refusals': self.total_undo_refusals,
            'confirmation_rate': self.total_undo_confirmations / max(1, self.total_undo_requests),
            'refusal_rate': self.total_undo_refusals / max(1, self.total_undo_requests),
            'refusal_reasons': self.undo_refusal_reasons,
            'currently_requested': self.undo_requested
        }
