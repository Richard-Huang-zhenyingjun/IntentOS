"""
Hand Loss Detector - Week 7 Failure Recovery

Detects hand loss during pinch confirmation gesture.
Prevents partial confirmations from interrupted gestures.
"""

from typing import Optional, Tuple
from intent_core.schema import SystemState

# Import HandDetectionResult if available
try:
    from src.vision.hand_detector import HandDetectionResult
except ImportError:
    HandDetectionResult = None  # Fallback


class HandLossDetector:
    """
    Detect hand loss during confirmation gesture
    
    Problem: User starts pinch confirmation, hand moves out of frame
    Solution: Detect hand loss, trigger PAUSED, require re-confirm
    
    Week 7: Prevents partial/interrupted confirmations
    
    Design:
    - Monitor hand detection during CONFIRMING state
    - Allow brief grace period (N frames) for tracking glitches
    - Trigger PAUSE if hand truly lost
    - Clear confirmation state on loss
    """
    
    def __init__(self, config: dict):
        self.config = config
        
        # Config
        loss_config = config.get('hand_loss', {})
        self.pause_during_confirm = loss_config.get('pause_during_confirm', True)
        self.grace_frames = loss_config.get('loss_grace_frames', 2)
        
        # State
        self.frames_without_hand = 0
        self.was_confirming = False
        
        # Statistics
        self.total_checks = 0
        self.loss_events = 0
    
    def check(self,
              hand_detection: Optional['HandDetectionResult'],
              system_state: SystemState,
              timestamp: float) -> Tuple[bool, str]:
        """
        Check if hand is lost during confirmation
        
        Args:
            hand_detection: Current hand detection result (or None)
            system_state: Current system state
            timestamp: Current timestamp
        
        Returns:
            (should_pause, reason) tuple
            - should_pause: True if hand lost during confirmation
            - reason: Human-readable explanation
        """
        self.total_checks += 1
        
        # Only check during CONFIRMING state
        if system_state != SystemState.CONFIRMING:
            self.frames_without_hand = 0
            self.was_confirming = False
            return (False, "")
        
        self.was_confirming = True
        
        # Check if hand detected
        hand_detected = (hand_detection is not None and 
                        getattr(hand_detection, 'detected', False))
        
        if not hand_detected:
            # Hand missing during confirmation
            self.frames_without_hand += 1
            
            if self.frames_without_hand >= self.grace_frames:
                # Grace period expired - trigger pause
                self.loss_events += 1
                
                # Get failure reason if available
                if hand_detection and hasattr(hand_detection, 'failure_reason'):
                    reason = hand_detection.failure_reason
                else:
                    reason = "Hand not detected"
                
                return (True, f"Hand lost during confirmation: {reason}")
        else:
            # Hand present
            self.frames_without_hand = 0
        
        return (False, "")
    
    def reset(self):
        """Reset detector state"""
        self.frames_without_hand = 0
        self.was_confirming = False
        self.total_checks = 0
        self.loss_events = 0
    
    def get_statistics(self) -> dict:
        """Get detector statistics"""
        return {
            'total_checks': self.total_checks,
            'loss_events': self.loss_events,
            'loss_rate': self.loss_events / max(1, self.total_checks),
            'frames_without_hand': self.frames_without_hand,
            'was_confirming': self.was_confirming
        }

