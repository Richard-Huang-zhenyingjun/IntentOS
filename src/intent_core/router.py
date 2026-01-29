"""Router - Route confirmed intents to action execution."""

from typing import Optional
import logging
from execution.action_executor import ActionExecutor
from execution.action_schema import ActionRequest, ActionType, ExecutionResult
from affordances.option_selector import HighlightedOption

logger = logging.getLogger(__name__)


class Router:
    """
    Route intents to actions (ENHANCED Week 6)
    
    Week 1-4: Refused all execution
    Week 5: Routes to ActionExecutor with toggle actions
    Week 6: Added specific state-setting actions
    """
    
    def __init__(self, config: dict, action_executor: ActionExecutor):
        self.config = config
        self.action_executor = action_executor
        
        # Existing state
        self.execution_count = 0
        self.refusal_count = 0
        
        # Affordance → Action mapping (ENHANCED Week 6)
        self.affordance_to_action_map = {
            # Toggles (Week 5)
            'toggle_power': ActionType.TOGGLE_POWER,
            'toggle_open': ActionType.TOGGLE_OPEN,
            'toggle_screen': ActionType.TOGGLE_SCREEN,
            
            # Specific actions (NEW Week 6)
            'turn_on': ActionType.TURN_ON,
            'turn_off': ActionType.TURN_OFF,
            'open': ActionType.OPEN,
            'close': ActionType.CLOSE,
            'wake': ActionType.WAKE,
            'sleep': ActionType.SLEEP,
            
            # Placeholders (Week 5)
            'pick_up': ActionType.PICK_UP,  # Will be refused by executor
        }
    
    def route(self,
              execution_allowed: bool,
              highlighted_option: Optional[HighlightedOption],
              scoped_object_id: Optional[str],
              scoped_object_label: Optional[str],
              scoped_category: Optional[str],
              timestamp: float) -> Optional[ExecutionResult]:
        """
        Route confirmed intent to execution (MODIFIED)
        
        Args:
            execution_allowed: Flag from state machine
            highlighted_option: Current highlighted affordance
            scoped_object_id: Scoped object track ID
            scoped_object_label: Human-readable label
            scoped_category: Object category
            timestamp: Current timestamp
        
        Returns:
            ExecutionResult if executed, None if refused
        """
        
        # === REFUSAL 1: Execution not allowed ===
        if not execution_allowed:
            self._log_refusal("execution_allowed flag is False")
            return None
        
        # === REFUSAL 2: No highlighted option ===
        if highlighted_option is None:
            self._log_refusal("No highlighted option")
            return None
        
        # === REFUSAL 3: No scope ===
        if scoped_object_id is None:
            self._log_refusal("No scoped object")
            return None
        
        # === REFUSAL 4: No category ===
        if scoped_category is None:
            self._log_refusal("No object category")
            return None
        
        # === MAP AFFORDANCE → ACTION ===
        affordance_type_str = highlighted_option.option.affordance_type.value
        
        if affordance_type_str not in self.affordance_to_action_map:
            self._log_refusal(f"Unknown affordance type: {affordance_type_str}")
            return None
        
        action_type = self.affordance_to_action_map[affordance_type_str]
        
        # === CREATE ACTION REQUEST ===
        action_request = ActionRequest.create(
            object_id=scoped_object_id,
            object_label=scoped_object_label,
            category=scoped_category,
            action_type=action_type,
            timestamp=timestamp,
            metadata={
                'affordance_title': highlighted_option.option.title,
                'affordance_confidence': highlighted_option.option.confidence,
                'affordance_risk': highlighted_option.option.risk.value
            }
        )
        
        # === EXECUTE ===
        result = self.action_executor.execute(action_request)
        
        if result.ok:
            self.execution_count += 1
        else:
            self.refusal_count += 1
            self._log_refusal(f"Executor refused: {result.reason}")
        
        return result
    
    def _log_refusal(self, reason: str):
        """Log refusal reason"""
        logger.debug(f"Router refused execution: {reason}")
    
    def get_statistics(self) -> dict:
        """Get router statistics"""
        return {
            'execution_count': self.execution_count,
            'refusal_count': self.refusal_count,
            'total_requests': self.execution_count + self.refusal_count
        }

