"""Action Executor - Execute actions on world state."""

from typing import Set
from execution.action_schema import ActionRequest, ActionType, ExecutionResult
from execution.smart_world_sim import SmartWorldSim
import time


class ActionExecutor:
    """
    Execute actions on world state
    
    Responsibilities:
    - Validate execution permissions
    - Apply actions via SmartWorldSim
    - Return execution results
    - Rate limiting
    
    CRITICAL: This is the ONLY way actions get executed
    Router calls this after all safety checks pass
    """
    
    def __init__(self, config: dict, world: SmartWorldSim):
        self.config = config
        self.world = world
        
        # Permissions
        self.enabled = config.get('enabled', False)
        self.allowed_categories: Set[str] = set(config.get('allowed_categories', []))
        self.allowed_actions: Set[str] = set(config.get('allowed_actions', []))
        self.refuse_unknown_category = config.get('refuse_unknown_category', True)
        self.refuse_unknown_action = config.get('refuse_unknown_action', True)
        
        # Rate limiting
        self.max_actions_per_second = config.get('max_actions_per_second', 2)
        self.recent_actions = []  # (timestamp, action_id)
        
        # Statistics
        self.total_executions = 0
        self.total_refusals = 0
        self.refusal_reasons = {}
    
    def execute(self, request: ActionRequest) -> ExecutionResult:
        """
        Execute action request
        
        Args:
            request: Action to execute
        
        Returns:
            ExecutionResult (ok=True if succeeded, ok=False if refused)
        """
        start_time = time.time()
        
        # === SAFETY CHECK 1: Execution enabled? ===
        if not self.enabled:
            return self._refuse(
                request=request,
                reason="Execution disabled in config",
                error_code="EXECUTION_DISABLED",
                timestamp=request.timestamp
            )
        
        # === SAFETY CHECK 2: Category allowed? ===
        if self.refuse_unknown_category and request.category not in self.allowed_categories:
            return self._refuse(
                request=request,
                reason=f"Category '{request.category}' not in allowed list",
                error_code="CATEGORY_NOT_ALLOWED",
                timestamp=request.timestamp
            )
        
        # === SAFETY CHECK 3: Action type allowed? ===
        if self.refuse_unknown_action and request.action_type.value not in self.allowed_actions:
            return self._refuse(
                request=request,
                reason=f"Action '{request.action_type.value}' not in allowed list",
                error_code="ACTION_NOT_ALLOWED",
                timestamp=request.timestamp
            )
        
        # === SAFETY CHECK 4: Placeholder action? ===
        if request.action_type in [ActionType.PICK_UP, ActionType.PUT_DOWN, ActionType.MOVE]:
            return self._refuse(
                request=request,
                reason=f"Action '{request.action_type.value}' is a placeholder (not implemented)",
                error_code="PLACEHOLDER_ACTION",
                timestamp=request.timestamp
            )
        
        # === SAFETY CHECK 5: Rate limiting ===
        if not self._check_rate_limit(request.timestamp):
            return self._refuse(
                request=request,
                reason=f"Rate limit exceeded ({self.max_actions_per_second}/s)",
                error_code="RATE_LIMIT",
                timestamp=request.timestamp
            )
        
        # === ALL CHECKS PASSED - EXECUTE ===
        try:
            before_state, after_state = self.world.apply_action(request)
            
            execution_time = (time.time() - start_time) * 1000  # ms
            self.total_executions += 1
            
            # Record for rate limiting
            self.recent_actions.append((request.timestamp, request.action_id))
            
            # Determine reversibility
            reversible = self._is_reversible(request.action_type)
            
            return ExecutionResult(
                ok=True,
                before_state=before_state,
                after_state=after_state,
                reason=f"Executed {request.action_type.value} on {request.category}",
                reversible=reversible,
                action_id=request.action_id,
                timestamp=request.timestamp,
                execution_time_ms=execution_time
            )
        
        except Exception as e:
            return self._refuse(
                request=request,
                reason=f"Execution error: {str(e)}",
                error_code="EXECUTION_ERROR",
                timestamp=request.timestamp,
                error_details={'exception': str(e)}
            )
    
    def _is_reversible(self, action_type: ActionType) -> bool:
        """Check if action is reversible"""
        # Toggle actions are reversible (applying same action undoes it)
        reversible_actions = {
            ActionType.TOGGLE_POWER,
            ActionType.TOGGLE_OPEN,
            ActionType.TOGGLE_SCREEN
        }
        return action_type in reversible_actions
    
    def _check_rate_limit(self, current_time: float) -> bool:
        """Check if rate limit allows execution"""
        # Clean old actions (older than 1 second)
        cutoff = current_time - 1.0
        self.recent_actions = [(t, aid) for t, aid in self.recent_actions if t >= cutoff]
        
        # Check count
        return len(self.recent_actions) < self.max_actions_per_second
    
    def _refuse(self,
                request: ActionRequest,
                reason: str,
                error_code: str,
                timestamp: float,
                error_details: dict = None) -> ExecutionResult:
        """Helper to create refusal result"""
        self.total_refusals += 1
        self.refusal_reasons[error_code] = self.refusal_reasons.get(error_code, 0) + 1
        
        return ExecutionResult(
            ok=False,
            before_state=None,
            after_state=None,
            reason=reason,
            reversible=False,
            action_id=request.action_id,
            timestamp=timestamp,
            error_code=error_code,
            error_details=error_details
        )
    
    def get_statistics(self) -> dict:
        """Get executor statistics"""
        return {
            'total_executions': self.total_executions,
            'total_refusals': self.total_refusals,
            'refusal_rate': self.total_refusals / max(1, self.total_executions + self.total_refusals),
            'refusal_reasons': self.refusal_reasons
        }




