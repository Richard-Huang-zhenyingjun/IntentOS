"""Keyboard input source - active controller."""

import pybullet as p
import time
from src.core.schema import ArmDecision, DecisionSignal
from src.input.decision_source import DecisionSource


class KeyboardInput(DecisionSource):
    """Read keyboard and produce ArmDecision."""
    
    def __init__(self, config: dict):
        self.config = config
        self.debounce_time = config.get('debounce_seconds', 0.3)
        self.last_confirm_time = 0.0
        self.last_cancel_time = 0.0
        
        # Key codes
        self.CONFIRM_KEY = ord('c')
        self.CANCEL_KEY = ord('x')
    
    def read_decision(self) -> ArmDecision:
        """Read keyboard state and produce decision.
        
        This is called ONCE per frame by the orchestrator.
        """
        now = time.time()
        
        # Read PyBullet keyboard events (SINGLE READ POINT)
        keys = p.getKeyboardEvents()
        
        # Check for CONFIRM (C key)
        if self.CONFIRM_KEY in keys:
            key_state = keys[self.CONFIRM_KEY]
            # Check for key press (not hold)
            if key_state & p.KEY_WAS_TRIGGERED:
                # Check debounce
                if now - self.last_confirm_time > self.debounce_time:
                    self.last_confirm_time = now
                    print(f"[KEYBOARD] ✓ CONFIRM pressed")
                    return ArmDecision(
                        signal=DecisionSignal.CONFIRM,
                        confidence=1.0,
                        source="keyboard",
                        timestamp=now
                    )
        
        # Check for CANCEL (X key)
        if self.CANCEL_KEY in keys:
            key_state = keys[self.CANCEL_KEY]
            if key_state & p.KEY_WAS_TRIGGERED:
                if now - self.last_cancel_time > self.debounce_time:
                    self.last_cancel_time = now
                    print(f"[KEYBOARD] ✗ CANCEL pressed")
                    return ArmDecision(
                        signal=DecisionSignal.CANCEL,
                        confidence=1.0,
                        source="keyboard",
                        timestamp=now
                    )
        
        # No decision
        return ArmDecision(
            signal=DecisionSignal.IDLE,
            confidence=0.0,
            source="keyboard",
            timestamp=now
        )
    
    def get_source_name(self) -> str:
        return "Keyboard (C=confirm, X=cancel)"
    
    def reset(self):
        """Reset debounce timers."""
        self.last_confirm_time = 0.0
        self.last_cancel_time = 0.0

