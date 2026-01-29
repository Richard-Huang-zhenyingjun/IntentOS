"""Affordance Registry - Maps object categories to affordance options."""

from typing import List, Dict
from affordances.affordance_schema import (
    ObjectCategory, AffordanceType, AffordanceOption, AffordanceRisk
)


class AffordanceRegistry:
    """
    Central registry mapping object categories to affordances
    
    Week 3: Simple rule-based templates
    Week 6: Add state-aware affordances (lamp on → turn off)
    Week 8+: Context-aware affordances (user preferences, history)
    
    Design principles:
    - Bounded (max 3 options per category)
    - Conservative (only suggest safe, well-understood actions)
    - Transparent (every affordance explains why it exists)
    - Extensible (easy to add new categories/actions)
    """
    
    def __init__(self, config: dict):
        self.config = config
        
        # Limits
        self.max_options = config.get('max_affordance_options', 3)
        
        # Build registry
        self.registry = self._build_registry()
    
    def _build_registry(self) -> Dict[ObjectCategory, List[AffordanceOption]]:
        """
        Build category → affordances mapping
        
        Returns:
            Dict[ObjectCategory, List[AffordanceOption]]
        """
        registry = {}
        
        # LAMP: Toggle power
        registry[ObjectCategory.LAMP] = [
            AffordanceOption(
                affordance_type=AffordanceType.TOGGLE_POWER,
                title="Toggle Power",
                description="Turn the lamp on or off",
                risk=AffordanceRisk.LOW,
                requires_confirmation=True,
                reason="Lamps can be toggled on/off",
                confidence=0.95,
                metadata={'reversible': True, 'safe': True}
            )
        ]
        
        # DOOR: Toggle open/close (Week 3: generic toggle, Week 6: state-aware)
        registry[ObjectCategory.DOOR] = [
            AffordanceOption(
                affordance_type=AffordanceType.TOGGLE_OPEN,
                title="Toggle Door",
                description="Open or close the door",
                risk=AffordanceRisk.MEDIUM,
                requires_confirmation=True,
                reason="Doors can be opened or closed",
                confidence=0.90,
                metadata={'reversible': True, 'requires_state_inference': True}
            )
        ]
        
        # PHONE: Toggle screen
        registry[ObjectCategory.PHONE] = [
            AffordanceOption(
                affordance_type=AffordanceType.TOGGLE_SCREEN,
                title="Toggle Screen",
                description="Wake or sleep the phone screen",
                risk=AffordanceRisk.LOW,
                requires_confirmation=True,
                reason="Phone screens can be toggled",
                confidence=0.85,
                metadata={'reversible': True}
            )
        ]
        
        # CUP: Pick up (placeholder)
        registry[ObjectCategory.CUP] = [
            AffordanceOption.create_placeholder(
                affordance_type=AffordanceType.PICK_UP,
                reason="Manipulation not yet implemented"
            )
        ]
        
        # BOOK: Pick up (placeholder)
        registry[ObjectCategory.BOOK] = [
            AffordanceOption.create_placeholder(
                affordance_type=AffordanceType.PICK_UP,
                reason="Manipulation not yet implemented"
            )
        ]
        
        # BOTTLE: Pick up (placeholder)
        registry[ObjectCategory.BOTTLE] = [
            AffordanceOption.create_placeholder(
                affordance_type=AffordanceType.PICK_UP,
                reason="Manipulation not yet implemented"
            )
        ]
        
        # UNKNOWN: No affordances
        registry[ObjectCategory.UNKNOWN] = []
        
        return registry
    
    def get_affordances(self, category: ObjectCategory) -> List[AffordanceOption]:
        """
        Get affordances for a category
        
        Args:
            category: Object category
        
        Returns:
            List of AffordanceOption (length <= max_options)
        """
        affordances = self.registry.get(category, [])
        
        # Enforce max options
        if len(affordances) > self.max_options:
            affordances = affordances[:self.max_options]
        
        return affordances
    
    def has_affordances(self, category: ObjectCategory) -> bool:
        """Check if category has any affordances"""
        return len(self.get_affordances(category)) > 0
    
    def get_all_categories(self) -> List[ObjectCategory]:
        """Get all registered categories"""
        return list(self.registry.keys())
    
    def add_affordance(self, category: ObjectCategory, option: AffordanceOption):
        """
        Dynamically add an affordance (for extensions)
        
        Week 3: Not used
        Week 8+: Could support user-defined affordances
        """
        if category not in self.registry:
            self.registry[category] = []
        
        if len(self.registry[category]) < self.max_options:
            self.registry[category].append(option)
        else:
            raise ValueError(f"Cannot add affordance: already at max ({self.max_options})")




