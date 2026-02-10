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
        print(f"[PRECOND] Checking all preconditions...")
        print(f"  State: holding={state.holding}, ee_pos={state.ee_position}, obj_pos={state.object_position}")
        
        available = []
        
        # Check each action
        can_move_up = self.check_move_up(state)
        print(f"  MOVE_UP: {can_move_up}")
        if can_move_up:
            available.append(ActionType.MOVE_UP)
        
        can_reach = self.check_reach(state)
        print(f"  REACH: {can_reach}")
        if can_reach:
            available.append(ActionType.REACH)
        
        can_grasp = self.check_grasp(state)
        print(f"  GRASP: {can_grasp}")
        if can_grasp:
            available.append(ActionType.GRASP)
        
        can_place = self.check_place(state)
        print(f"  PLACE: {can_place}")
        if can_place:
            available.append(ActionType.PLACE)
        
        print(f"[PRECOND] Available actions: {available}")
        return available

