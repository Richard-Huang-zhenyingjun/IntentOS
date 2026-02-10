"""Keyboard input source - active controller."""

import pybullet as p
import time
from src.interfaces.decision_source_base import DecisionSourceBase, Decision
from src.core.schema import ArmDecision, DecisionSignal  # For backward compatibility


class KeyboardInput(DecisionSourceBase):
    """Keyboard decision source - implements DecisionSourceBase"""
    
    def __init__(self, config: dict):
        self.config = config
        self.debounce_time = config.get('debounce_seconds', 0.3)
        self.last_confirm_time = 0.0
        self.last_cancel_time = 0.0
        self._cached_keys = None  # For sharing keys from main loop
        
        # Key codes
        self.CONFIRM_KEY = ord('c')
        self.CANCEL_KEY = ord('x')
    
    def read(self, keys: dict = None) -> Decision:
        """
        Read keyboard state and produce Decision (Week 3: interface method).
        
        This is called ONCE per frame by the orchestrator.
        
        Args:
            keys: Optional pre-read keyboard events dict. If None, reads from PyBullet.
        """
        now = time.time()
        confirm_pressed = False
        cancel_pressed = False
        
        # Read PyBullet keyboard events (SINGLE READ POINT)
        # If keys provided, use them (avoids double-read buffer clearing issue)
        # Also check cached keys (set by main loop to share keyboard events)
        if keys is None:
            if self._cached_keys is not None:
                keys = self._cached_keys
                self._cached_keys = None  # Clear after use
            else:
                keys = p.getKeyboardEvents()
        
        # Check for CONFIRM (C key)
        if self.CONFIRM_KEY in keys:
            key_state = keys[self.CONFIRM_KEY]
            print(f"[KEYBOARD DEBUG] C key detected, state: {key_state}")
            
            # Check for key press (not hold)
            if key_state & p.KEY_WAS_TRIGGERED:
                print(f"[KEYBOARD DEBUG] C key TRIGGERED")
                
                # Check debounce
                if now - self.last_confirm_time > self.debounce_time:
                    self.last_confirm_time = now
                    print(f"[KEYBOARD] ✓ CONFIRM pressed")
                    confirm_pressed = True
                else:
                    print(f"[KEYBOARD DEBUG] C key debounced (too soon)")
            else:
                print(f"[KEYBOARD DEBUG] C key not triggered (held or released)")
        
        # Check for CANCEL (X key)
        if self.CANCEL_KEY in keys:
            key_state = keys[self.CANCEL_KEY]
            if key_state & p.KEY_WAS_TRIGGERED:
                if now - self.last_cancel_time > self.debounce_time:
                    self.last_cancel_time = now
                    print(f"[KEYBOARD] ✗ CANCEL pressed")
                    cancel_pressed = True
        
        # Return Decision (Week 3: interface format)
        return Decision(
            confirm=confirm_pressed,
            cancel=cancel_pressed,
            quality=1.0,
            source="keyboard"
        )
    
    def read_decision(self, keys: dict = None) -> ArmDecision:
        """
        Backward compatibility method (Week 3: deprecated).
        Converts Decision to ArmDecision for old code.
        """
        decision = self.read(keys)
        signal = DecisionSignal.CONFIRM if decision.confirm else (
            DecisionSignal.CANCEL if decision.cancel else DecisionSignal.IDLE
        )
        return ArmDecision(
            signal=signal,
            confidence=decision.quality,
            source=decision.source,
            timestamp=time.time()
        )
    
    def name(self) -> str:
        """Human-readable source name (Week 3: interface method)"""
        return "keyboard"
    
    def get_source_name(self) -> str:
        """Backward compatibility method (Week 3: deprecated)"""
        return "Keyboard (C=confirm, X=cancel)"
    
    def reset(self):
        """Reset debounce timers."""
        self.last_confirm_time = 0.0
        self.last_cancel_time = 0.0

