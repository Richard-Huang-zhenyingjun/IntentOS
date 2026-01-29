"""Pause controller - triggers pause on failures."""

from src.robot.world_state import WorldState
from src.core.state_machine import StateMachine


class PauseController:
    """Check for conditions requiring pause."""
    
    def __init__(self, config: dict):
        self.config = config
        self.pause_reason = ""
    
    def should_pause(self, world: WorldState, state_machine: StateMachine) -> bool:
        """Check if system should pause.
        
        Returns:
            True if pause needed
        """
        # Target lost during critical states
        critical_states = ['selecting', 'confirming', 'executing']
        if state_machine.state.value in critical_states:
            if world.object_position is None or not world.object.visible:
                self.pause_reason = "Target object lost"
                return True
        
        return False
    
    def get_pause_reason(self) -> str:
        """Get current pause reason."""
        return self.pause_reason

