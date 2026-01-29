"""
Mock EEG - keyboard passthrough and scripted decision source.
Week 6: Allows testing EEG pipeline without real BCI hardware.
"""

from typing import List, Tuple, Optional
import time
import pybullet as p
from .eeg_interface import EEGDecisionSource
from intent_core.arm_intent_schema import DecisionSignal


class MockEEG(EEGDecisionSource):
    """
    Mock EEG decision source for testing.
    
    Modes:
    - keyboard: Pass through C/X keys (default)
    - scripted: Pre-defined decision sequence with timing
    
    Week 6: Keyboard passthrough (same as Week 5).
    Week 7+: Can use scripted mode for deterministic demos.
    """
    
    def __init__(self, mode: str = "keyboard", script: Optional[List[Tuple[float, DecisionSignal]]] = None):
        """
        Initialize mock EEG.
        
        Args:
            mode: "keyboard" or "scripted"
            script: List of (timestamp, signal) for scripted mode
        """
        self.mode = mode
        self.script = script or []
        self.script_idx = 0
        self.start_time = 0.0
        self._running = False
        self.last_confidence = 1.0
    
    def start(self) -> bool:
        """Start mock EEG."""
        self._running = True
        self.start_time = time.time()
        print(f"✓ MockEEG started (mode: {self.mode})")
        return True
    
    def read_signal(self) -> DecisionSignal:
        """
        Read decision signal.
        
        Returns:
            DecisionSignal based on mode
        """
        if not self._running:
            return DecisionSignal.IDLE
        
        if self.mode == "keyboard":
            return self._read_keyboard()
        elif self.mode == "scripted":
            return self._read_scripted()
        else:
            return DecisionSignal.IDLE
    
    def _read_keyboard(self) -> DecisionSignal:
        """Read from keyboard (C/X keys)."""
        keys = p.getKeyboardEvents()
        
        # STEP 3: Log key detection for diagnostics
        # C = CONFIRM (key 99)
        if 99 in keys and keys[99] & p.KEY_WAS_TRIGGERED:
            print("[KEY DETECTED] C -> CONFIRM (via MockEEG)")
            return DecisionSignal.CONFIRM
        
        # X = CANCEL (key 120)
        if 120 in keys and keys[120] & p.KEY_WAS_TRIGGERED:
            print("[KEY DETECTED] X -> CANCEL (via MockEEG)")
            return DecisionSignal.CANCEL
        
        return DecisionSignal.IDLE
    
    def _read_scripted(self) -> DecisionSignal:
        """Read from pre-defined script."""
        elapsed = time.time() - self.start_time
        
        # Check if current script entry should fire
        if self.script_idx < len(self.script):
            trigger_time, signal = self.script[self.script_idx]
            
            if elapsed >= trigger_time:
                self.script_idx += 1
                return signal
        
        return DecisionSignal.IDLE
    
    def close(self) -> None:
        """Stop mock EEG."""
        self._running = False
        print("✓ MockEEG closed")
    
    def get_source_name(self) -> str:
        """Get source name."""
        return f"MockEEG ({self.mode})"
    
    def get_confidence(self) -> float:
        """Get confidence (always 1.0 for mock)."""
        return self.last_confidence
    
    def reset_script(self) -> None:
        """Reset scripted playback to beginning."""
        self.script_idx = 0
        self.start_time = time.time()

