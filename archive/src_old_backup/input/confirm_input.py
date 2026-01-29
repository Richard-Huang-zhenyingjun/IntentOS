"""
Confirm input - keyboard-based decision signals.
Week 4: C = CONFIRM, X = CANCEL.
Week 6: Replace with EEG input (same interface).
"""

from typing import Dict
import time
import pybullet as p
from intent_core.arm_intent_schema import DecisionSignal, ArmDecision


class KeyboardConfirmInput:
    """
    Keyboard-based confirm/cancel input.
    
    Key mappings:
    - C (99): CONFIRM
    - X (120): CANCEL
    - (no key): IDLE
    
    Debouncing: Only triggers on key-down (WAS_TRIGGERED flag).
    """
    
    def __init__(self):
        """Initialize keyboard input reader."""
        self.last_keys: Dict[int, int] = {}
        
        # FIX 7: Throttle key logging
        self._last_key_time = 0.0
    
    def read(self) -> ArmDecision:
        """
        Read current decision from keyboard.
        
        FIX 7: Throttled logging to prevent spam.
        
        Returns:
            ArmDecision with signal (CONFIRM/CANCEL/IDLE)
        """
        # FIX: Read keys here FIRST (before main loop reads them)
        keys = p.getKeyboardEvents()
        
        # === DIAGNOSTIC STEP 2: Prove confirm_input sees keys ===
        if keys:
            print(f"\n[DBG CONFIRM_INPUT] Key events received: {keys}")
            for k, st in keys.items():
                ch = chr(k) if 32 <= k <= 126 else None
                if st & p.KEY_WAS_TRIGGERED:
                    print(f"[DBG CONFIRM_INPUT] ✓ TRIGGERED: key={k} char='{ch}'")
        
        print(f"[DBG CONFIRM_INPUT] Checking ord('c')={ord('c')} in keys: {ord('c') in keys}")
        print(f"[DBG CONFIRM_INPUT] Checking ord('C')={ord('C')} in keys: {ord('C') in keys}")
        print(f"[DBG CONFIRM_INPUT] Checking key code 99 in keys: {99 in keys}")
        
        if ord('c') in keys:
            print(f"[DBG CONFIRM_INPUT] 'c' state: {keys[ord('c')]}")
        if ord('C') in keys:
            print(f"[DBG CONFIRM_INPUT] 'C' state: {keys[ord('C')]}")
        if 99 in keys:
            print(f"[DBG CONFIRM_INPUT] Key code 99 state: {keys[99]}")
        
        current_time = time.time()
        
        # Check BOTH lowercase and uppercase C, plus key code 99
        c_triggered = ((ord('c') in keys and keys[ord('c')] & p.KEY_WAS_TRIGGERED) or
                       (ord('C') in keys and keys[ord('C')] & p.KEY_WAS_TRIGGERED) or
                       (99 in keys and keys[99] & p.KEY_WAS_TRIGGERED))
        
        if c_triggered:
            print(f"\n[DBG CONFIRM_INPUT] ★★★ CONFIRM DETECTED ★★★")
            if current_time - self._last_key_time > 0.3:
                print("[KEY] C -> CONFIRM")
                self._last_key_time = current_time
            return ArmDecision.from_keyboard(DecisionSignal.CONFIRM)
        
        # X key (handle both cases, plus key code 120)
        x_triggered = ((ord('x') in keys and keys[ord('x')] & p.KEY_WAS_TRIGGERED) or
                       (ord('X') in keys and keys[ord('X')] & p.KEY_WAS_TRIGGERED) or
                       (120 in keys and keys[120] & p.KEY_WAS_TRIGGERED))
        
        if x_triggered:
            print(f"\n[DBG CONFIRM_INPUT] ★★★ CANCEL DETECTED ★★★")
            if current_time - self._last_key_time > 0.3:
                print("[KEY] X -> CANCEL")
                self._last_key_time = current_time
            return ArmDecision.from_keyboard(DecisionSignal.CANCEL)
        
        # No decision
        print(f"[DBG CONFIRM_INPUT] No decision - returning IDLE")
        return ArmDecision.idle()
    
    def get_help_text(self) -> str:
        """Get user-facing help text for controls."""
        return "C=CONFIRM, X=CANCEL"

