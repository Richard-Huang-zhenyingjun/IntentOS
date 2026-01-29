"""
Object Loss Detector - Week 7 Failure Recovery

Detects loss of scoped object during vulnerable states.
Critical safety component to prevent actions on disappeared objects.
"""

from typing import Optional, Dict, Tuple
from intent_core.schema import SystemState
from vision.object_tracker import ObjectTracker


class ObjectLossDetector:
    """
    Detect loss of scoped object during vulnerable states
    
    Problem: User confirms action, object moves away or is occluded
    Solution: Detect loss, trigger PAUSED, require re-scope
    
    Week 7: Critical safety component
    
    Design:
    - Monitor scoped object during SCOPED/CONFIRMING/EXECUTING
    - Allow brief grace period (N frames) for temporary occlusion
    - Trigger PAUSE if object truly lost
    - Clear state on recovery
    """
    
    def __init__(self, config: dict):
        self.config = config
        
        # Config
        loss_config = config.get('object_loss', {})
        self.pause_on_loss = loss_config.get('pause_on_loss', True)
        self.grace_frames = loss_config.get('loss_grace_frames', 3)
        
        # State
        self.frames_missing = 0
        self.last_scoped_id: Optional[str] = None
        
        # Statistics
        self.total_checks = 0
        self.loss_events = 0
    
    def check(self,
              scoped_object_id: Optional[str],
              tracker: ObjectTracker,
              system_state: SystemState,
              timestamp: float) -> Tuple[bool, str]:
        """
        Check if scoped object is lost during vulnerable state
        
        Args:
            scoped_object_id: Currently scoped object ID
            tracker: Object tracker (to verify object still exists)
            system_state: Current system state
            timestamp: Current timestamp
        
        Returns:
            (should_pause, reason) tuple
            - should_pause: True if object lost and pause needed
            - reason: Human-readable explanation
        """
        self.total_checks += 1
        
        # Only check during vulnerable states
        vulnerable_states = [
            SystemState.SCOPED,
            SystemState.CONFIRMING,
            SystemState.EXECUTING
        ]
        
        if system_state not in vulnerable_states:
            self.frames_missing = 0
            self.last_scoped_id = scoped_object_id
            return (False, "")
        
        # No scoped object → not applicable
        if scoped_object_id is None:
            self.frames_missing = 0
            self.last_scoped_id = None
            return (False, "")
        
        # Check if object still tracked
        track = tracker.get_track(scoped_object_id)
        
        if track is None or track.should_delete(tracker.max_age):
            # Object missing
            self.frames_missing += 1
            
            if self.frames_missing >= self.grace_frames:
                # Grace period expired - trigger pause
                self.loss_events += 1
                return (True, f"Scoped object lost ({scoped_object_id}) during {system_state.value}")
        else:
            # Object still present
            self.frames_missing = 0
            self.last_scoped_id = scoped_object_id
        
        return (False, "")
    
    def reset(self):
        """Reset detector state"""
        self.frames_missing = 0
        self.last_scoped_id = None
        self.total_checks = 0
        self.loss_events = 0
    
    def get_statistics(self) -> dict:
        """Get detector statistics"""
        return {
            'total_checks': self.total_checks,
            'loss_events': self.loss_events,
            'loss_rate': self.loss_events / max(1, self.total_checks),
            'frames_missing': self.frames_missing,
            'last_scoped_id': self.last_scoped_id
        }




