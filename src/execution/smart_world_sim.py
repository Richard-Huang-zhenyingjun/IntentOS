"""Smart World Simulator - Simulated smart environment for safe action execution."""

from dataclasses import dataclass, field
from typing import Dict, Any, Tuple, Optional
from execution.action_schema import ActionType, ActionRequest
import copy


@dataclass
class WorldObjectState:
    """State of a simulated object"""
    object_id: str
    category: str
    state: Dict[str, Any]  # Category-specific state
    last_updated: float
    update_count: int = 0


class SmartWorldSim:
    """
    Simulated smart environment (ENHANCED Week 6)
    
    Week 5: Simple state machine for lamp/door/phone with toggle actions
    Week 6: Added specific state-setting actions (turn_on/off, open/close, wake/sleep)
    Week 8+: Could connect to Home Assistant, IoT APIs
    
    Design principle: Deterministic, reversible, safe
    """
    
    def __init__(self, config: dict, seed: int = 42):
        self.config = config
        self.seed = seed
        
        # World state
        self.objects: Dict[str, WorldObjectState] = {}
        
        # Initial states from config
        self.initial_states = config.get('initial_states', {
            'lamp': 'off',
            'door': 'closed',
            'phone': 'screen_off'
        })
        
        # Statistics
        self.total_actions = 0
        self.total_undos = 0
    
    def ensure_object(self, object_id: str, category: str, timestamp: float):
        """
        Ensure object exists in world state
        
        Creates with default state if not present
        """
        if object_id not in self.objects:
            initial_state = self._get_initial_state(category)
            self.objects[object_id] = WorldObjectState(
                object_id=object_id,
                category=category,
                state=initial_state,
                last_updated=timestamp,
                update_count=0
            )
    
    def _get_initial_state(self, category: str) -> Dict[str, Any]:
        """Get initial state for category"""
        if category == 'lamp':
            return {'power': self.initial_states.get('lamp', 'off')}
        elif category == 'door':
            return {'position': self.initial_states.get('door', 'closed')}
        elif category == 'phone':
            return {'screen': self.initial_states.get('phone', 'screen_off')}
        else:
            return {'state': 'unknown'}
    
    def apply_action(self, 
                    request: ActionRequest) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Apply action to world state
        
        Args:
            request: Action to execute
        
        Returns:
            (before_state, after_state) tuple
        
        Raises:
            ValueError: If action cannot be applied
        """
        self.total_actions += 1
        
        # Ensure object exists
        self.ensure_object(request.object_id, request.category, request.timestamp)
        
        obj = self.objects[request.object_id]
        
        # Copy current state
        before_state = copy.deepcopy(obj.state)
        
        # Apply action based on category + type
        if request.category == 'lamp':
            after_state = self._apply_lamp_action(obj, request.action_type)
        elif request.category == 'door':
            after_state = self._apply_door_action(obj, request.action_type)
        elif request.category == 'phone':
            after_state = self._apply_phone_action(obj, request.action_type)
        else:
            raise ValueError(f"Unknown category: {request.category}")
        
        # Update object
        obj.state = after_state
        obj.last_updated = request.timestamp
        obj.update_count += 1
        
        return (before_state, after_state)
    
    def _apply_lamp_action(self, obj: WorldObjectState, action: ActionType) -> Dict[str, Any]:
        """Apply action to lamp (ENHANCED Week 6)"""
        current_power = obj.state.get('power', 'off')
        
        if action == ActionType.TOGGLE_POWER:
            # Toggle (Week 5)
            new_power = 'on' if current_power == 'off' else 'off'
            return {'power': new_power}
        
        elif action == ActionType.TURN_ON:
            # NEW Week 6: Set to ON
            return {'power': 'on'}
        
        elif action == ActionType.TURN_OFF:
            # NEW Week 6: Set to OFF
            return {'power': 'off'}
        
        else:
            raise ValueError(f"Invalid lamp action: {action}")
    
    def _apply_door_action(self, obj: WorldObjectState, action: ActionType) -> Dict[str, Any]:
        """Apply action to door (ENHANCED Week 6)"""
        current_position = obj.state.get('position', 'closed')
        
        if action == ActionType.TOGGLE_OPEN:
            # Toggle (Week 5)
            new_position = 'open' if current_position == 'closed' else 'closed'
            return {'position': new_position}
        
        elif action == ActionType.OPEN:
            # NEW Week 6: Set to OPEN
            return {'position': 'open'}
        
        elif action == ActionType.CLOSE:
            # NEW Week 6: Set to CLOSED
            return {'position': 'closed'}
        
        else:
            raise ValueError(f"Invalid door action: {action}")
    
    def _apply_phone_action(self, obj: WorldObjectState, action: ActionType) -> Dict[str, Any]:
        """Apply action to phone (ENHANCED Week 6)"""
        current_screen = obj.state.get('screen', 'screen_off')
        
        if action == ActionType.TOGGLE_SCREEN:
            # Toggle (Week 5)
            new_screen = 'screen_on' if current_screen == 'screen_off' else 'screen_off'
            return {'screen': new_screen}
        
        elif action == ActionType.WAKE:
            # NEW Week 6: Set to SCREEN_ON
            return {'screen': 'screen_on'}
        
        elif action == ActionType.SLEEP:
            # NEW Week 6: Set to SCREEN_OFF
            return {'screen': 'screen_off'}
        
        else:
            raise ValueError(f"Invalid phone action: {action}")
    
    def apply_undo(self,
                   object_id: str,
                   before_state: Dict[str, Any],
                   timestamp: float) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Restore object to previous state
        
        Args:
            object_id: Object to restore
            before_state: State to restore to
            timestamp: When undo occurred
        
        Returns:
            (before_undo_state, after_undo_state) tuple
        """
        self.total_undos += 1
        
        if object_id not in self.objects:
            raise ValueError(f"Object {object_id} not found")
        
        obj = self.objects[object_id]
        
        # Current state becomes "before undo"
        before_undo = copy.deepcopy(obj.state)
        
        # Restore previous state
        obj.state = copy.deepcopy(before_state)
        obj.last_updated = timestamp
        obj.update_count += 1
        
        # After undo is the restored state
        after_undo = copy.deepcopy(obj.state)
        
        return (before_undo, after_undo)
    
    def get_object_state(self, object_id: str) -> Optional[Dict[str, Any]]:
        """Get current state of object"""
        if object_id in self.objects:
            return copy.deepcopy(self.objects[object_id].state)
        return None
    
    def get_all_objects(self) -> Dict[str, WorldObjectState]:
        """Get all objects (for UI visualization)"""
        return copy.deepcopy(self.objects)
    
    def reset(self):
        """Reset world to initial state"""
        self.objects.clear()
        self.total_actions = 0
        self.total_undos = 0

