"""Action planner - determines next action to propose."""

from typing import Optional
from src.robot.actions import ActionType
from src.robot.world_state import WorldState
from src.planning.preconditions import Preconditions


class ActionPlanner:
    """Deterministic action planner using priority rules."""
    
    def __init__(self, config: dict):
        self.preconditions = Preconditions(config)
        
        # Priority order (first available wins)
        self.priority = [
            ActionType.MOVE_UP,   # 1. Safety: get to working height
            ActionType.REACH,     # 2. Approach object
            ActionType.GRASP,     # 3. Attach object
            ActionType.PLACE,     # 4. Release at target
        ]
    
    def propose_next_action(self, state: WorldState) -> Optional[ActionType]:
        """Propose next action based on current state.
        
        Returns:
            ActionType to propose, or None if nothing available
        """
        print(f"[PLANNER] propose_next_action called")
        print(f"  World state: holding={state.holding}, ee_pos={state.ee_position}, obj_pos={state.object_position}")
        
        # Get all available actions
        available = self.preconditions.get_available_actions(state)
        print(f"[PLANNER DEBUG] Available actions: {[a.value for a in available]}")
        
        if not available:
            print(f"[PLANNER DEBUG] No available actions!")
            print(f"[PLANNER] Returning action: None")
            return None
        
        # Pick highest priority available action
        for action in self.priority:
            if action in available:
                print(f"[PLANNER DEBUG] Selected action: {action.value}")
                print(f"[PLANNER] Returning action: {action}")
                return action
        
        # Fallback
        print(f"[PLANNER DEBUG] Fallback, returning first available")
        result = available[0] if available else None
        print(f"[PLANNER] Returning action: {result}")
        return result
    
    def get_action_reason(self, action: ActionType, state: WorldState) -> str:
        """Get human-readable reason for action."""
        if action == ActionType.MOVE_UP:
            return f"End effector too low (z={state.ee_position[2]:.2f}m)"
        elif action == ActionType.REACH:
            dist = state.distance_to_object()
            return f"Moving to object (distance={dist:.2f}m)"
        elif action == ActionType.GRASP:
            return "Close enough to grasp"
        elif action == ActionType.PLACE:
            return f"Holding object {state.attached_id}, ready to place"
        else:
            return f"Action: {action.value}"

