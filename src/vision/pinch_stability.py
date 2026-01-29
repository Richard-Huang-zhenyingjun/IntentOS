"""Pinch Stability Controller - Convert noisy observations into stable confirmation signals."""

from dataclasses import dataclass
from typing import Optional
from vision.pinch_detector import PinchObservation


@dataclass
class PinchState:
    """
    Stable pinch state (temporal filtering applied)
    
    This is the output after stability checking
    Only 'just_confirmed' triggers confirmation
    """
    # Current state
    stable: bool  # Is pinch currently stable?
    confirmed: bool  # Has confirmation been triggered?
    
    # Counters
    frames_held: int  # Consecutive frames of pinch held
    frames_released: int  # Consecutive frames of no pinch
    
    # Confirmation (edge-triggered)
    just_confirmed: bool  # TRUE only on the frame confirmation happens
    
    # Metadata
    timestamp: float
    reason: str  # Human-readable state explanation
    
    # Debug
    last_observation: Optional[PinchObservation] = None


class PinchStability:
    """
    Convert noisy pinch observations into stable confirmation signals
    
    Safety requirements:
    - Must hold pinch for N consecutive frames (no flicker)
    - Confirmation is edge-triggered (happens once per gesture)
    - Must release for M frames to reset
    - Timeout if held too long (prevents stuck state)
    
    Design principle: Intentionality over speed
    """
    
    def __init__(self, config: dict):
        self.config = config
        
        # Stability requirements
        self.stable_frames_required = config.get('stable_frames_required', 6)
        self.release_frames_required = config.get('release_frames_required', 4)
        self.max_hold_time = config.get('max_hold_time_seconds', 3.0)
        
        # State
        self.frames_held = 0
        self.frames_released = 0
        self.confirmed = False  # Has confirmation already fired?
        self.confirm_timestamp: Optional[float] = None
        
        # Statistics
        self.total_confirmations = 0
        self.total_timeouts = 0
    
    def step(self, 
             observation: Optional[PinchObservation],
             timestamp: float) -> PinchState:
        """
        Update stability state with new observation
        
        Args:
            observation: Current frame pinch observation (or None)
            timestamp: Current timestamp
        
        Returns:
            PinchState with just_confirmed=True if confirmation triggered
        """
        
        # === CASE 1: No observation (hand lost or not pinching) ===
        if observation is None or not observation.pinching:
            self.frames_released += 1
            
            # Reset if released long enough
            if self.frames_released >= self.release_frames_required:
                was_confirmed = self.confirmed
                self.frames_held = 0
                self.confirmed = False
                self.confirm_timestamp = None
                
                reason = "reset: released" if was_confirmed else "waiting for pinch"
            else:
                reason = f"releasing: {self.frames_released}/{self.release_frames_required}"
            
            return PinchState(
                stable=False,
                confirmed=self.confirmed,
                frames_held=self.frames_held,
                frames_released=self.frames_released,
                just_confirmed=False,
                timestamp=timestamp,
                reason=reason,
                last_observation=observation
            )
        
        # === CASE 2: Pinch detected ===
        self.frames_held += 1
        self.frames_released = 0
        
        # Check timeout
        if self.confirm_timestamp and (timestamp - self.confirm_timestamp) > self.max_hold_time:
            # Held too long - force reset
            self.total_timeouts += 1
            self.frames_held = 0
            self.confirmed = False
            self.confirm_timestamp = None
            
            return PinchState(
                stable=False,
                confirmed=False,
                frames_held=0,
                frames_released=0,
                just_confirmed=False,
                timestamp=timestamp,
                reason="timeout: held too long",
                last_observation=observation
            )
        
        # Check if reached stability threshold
        stable = self.frames_held >= self.stable_frames_required
        
        # Edge-triggered confirmation
        just_confirmed = False
        if stable and not self.confirmed:
            # Confirmation fires!
            self.confirmed = True
            self.confirm_timestamp = timestamp
            self.total_confirmations += 1
            just_confirmed = True
            reason = "CONFIRMED"
        elif stable and self.confirmed:
            reason = f"holding: {self.frames_held} frames"
        else:
            reason = f"building: {self.frames_held}/{self.stable_frames_required}"
        
        return PinchState(
            stable=stable,
            confirmed=self.confirmed,
            frames_held=self.frames_held,
            frames_released=self.frames_released,
            just_confirmed=just_confirmed,
            timestamp=timestamp,
            reason=reason,
            last_observation=observation
        )
    
    def reset(self):
        """Force reset (for recovery scenarios)"""
        self.frames_held = 0
        self.frames_released = 0
        self.confirmed = False
        self.confirm_timestamp = None
    
    def get_statistics(self) -> dict:
        """Get stability statistics"""
        return {
            'total_confirmations': self.total_confirmations,
            'total_timeouts': self.total_timeouts,
            'current_frames_held': self.frames_held,
            'current_confirmed': self.confirmed
        }




