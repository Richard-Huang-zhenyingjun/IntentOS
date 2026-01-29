"""Action precondition checks."""

import numpy as np
from typing import List
from src.robot.actions import ActionType
from src.robot.world_state import WorldState


class Preconditions:
    """Check which actions are available given world state."""
    
    def __init__(self, config: dict):
        self.config = config
        
        # Thresholds
        self.min_ee_height = config.get('min_ee_height', 0.15)
        self.reach_distance = config.get('reach_distance', 0.15)
        self.grasp_distance = config.get('grasp_distance', 0.10)
    
    def check_move_up(self, state: WorldState) -> bool:
        """Can we move up?"""
        if state.ee_position is None:
            return False
        return state.ee_position[2] < self.min_ee_height
    
    def check_reach(self, state: WorldState) -> bool:
        """Can we reach?"""
        if state.holding:
            return False  # Already holding
        if state.object_position is None:
            return False  # No object
        if state.ee_position is None:
            return False
        
        # Check if far enough to need reaching
        dist = state.distance_to_object()
        return dist is not None and dist > self.reach_distance
    
    def check_grasp(self, state: WorldState) -> bool:
        """Can we grasp?"""
        if state.holding:
            return False  # Already holding
        if state.object_position is None:
            return False  # No object
        
        # Check if close enough
        dist = state.distance_to_object()
        return dist is not None and dist < self.grasp_distance
    
    def check_place(self, state: WorldState) -> bool:
        """Can we place?"""
        return state.holding  # Must be holding something
    
    def get_available_actions(self, state: WorldState) -> List[ActionType]:
        """Get all currently available actions."""
        available = []
        
        if self.check_move_up(state):
            available.append(ActionType.MOVE_UP)
        if self.check_reach(state):
            available.append(ActionType.REACH)
        if self.check_grasp(state):
            available.append(ActionType.GRASP)
        if self.check_place(state):
            available.append(ActionType.PLACE)
        
        return available

