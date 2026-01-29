"""Option Selector - Select exactly ONE affordance option to be confirmable."""

from dataclasses import dataclass
from typing import Optional
from affordances.affordance_schema import AffordanceSet, AffordanceOption


@dataclass(frozen=True)
class HighlightedOption:
    """
    The ONE affordance option that is currently confirmable
    
    Week 5: Always index 0 (first option)
    Week 7+: Could cycle through options via gesture/attention
    """
    option_index: int  # Index in affordance_set.options
    option: AffordanceOption  # The actual option
    affordance_set: AffordanceSet  # Parent set (for context)
    
    # Metadata
    timestamp: float
    reason: str  # Why this option selected


class OptionSelector:
    """
    Select exactly ONE affordance option to be confirmable
    
    Week 5: Deterministic (always first option)
    Design: Extensible for future selection strategies
    
    Selection strategies (Week 5 → future):
    - Week 5: Always index 0
    - Week 7: Cycle via secondary gesture
    - Week 8: Attention-based (gaze direction)
    - Week 9: Learning-based (user preference)
    """
    
    def __init__(self, config: dict):
        self.config = config
        
        # Selection strategy
        self.strategy = config.get('strategy', 'first')  # 'first', 'cycle', 'attention'
        
        # State (for cycling - not used in Week 5)
        self.current_index = 0
        self.last_affordance_set_id = None
        
        # Statistics
        self.total_selections = 0
    
    def select(self, 
               affordance_set: Optional[AffordanceSet],
               timestamp: float) -> Optional[HighlightedOption]:
        """
        Select highlighted option from affordance set
        
        Args:
            affordance_set: Current affordance set (or None)
            timestamp: Current timestamp
        
        Returns:
            HighlightedOption or None if no options available
        """
        
        # No affordances → no highlight
        if affordance_set is None:
            return None
        
        # Blocked → no highlight
        if affordance_set.blocked:
            return None
        
        # Empty → no highlight
        if len(affordance_set.options) == 0:
            return None
        
        # Week 5: Always select first option
        if self.strategy == 'first':
            selected_index = 0
            reason = "first option (default)"
        
        # Future strategies (not implemented in Week 5)
        elif self.strategy == 'cycle':
            # Check if affordance set changed
            current_set_id = affordance_set.object_id
            if current_set_id != self.last_affordance_set_id:
                self.current_index = 0
                self.last_affordance_set_id = current_set_id
            
            selected_index = self.current_index % len(affordance_set.options)
            reason = f"cycling ({selected_index + 1}/{len(affordance_set.options)})"
        
        else:
            # Default to first
            selected_index = 0
            reason = "first option (fallback)"
        
        # Validate index
        if selected_index >= len(affordance_set.options):
            return None
        
        self.total_selections += 1
        
        return HighlightedOption(
            option_index=selected_index,
            option=affordance_set.options[selected_index],
            affordance_set=affordance_set,
            timestamp=timestamp,
            reason=reason
        )
    
    def cycle_next(self):
        """
        Cycle to next option (for future use)
        
        Week 5: Not called
        Week 7+: Trigger via secondary gesture
        """
        self.current_index += 1
    
    def reset(self):
        """Reset selection state"""
        self.current_index = 0
        self.last_affordance_set_id = None




