"""
Oscillation Detection System - Week 7

Detects and suppresses rapid attention switching (oscillation/thrashing).
Prevents UI instability from user glancing between two objects repeatedly.
"""

from dataclasses import dataclass
from typing import List, Optional, Deque
from collections import deque

@dataclass
class FocusSwitch:
    """Record of a focus switch event"""
    from_id: Optional[str]
    to_id: str
    timestamp: float

@dataclass
class OscillationResult:
    """Result of oscillation detection"""
    oscillating: bool  # Is oscillation currently detected?
    suppressed_ids: List[str]  # Object IDs currently suppressed
    suppressed_until: Optional[float]  # When suppression ends
    reason: str
    switch_count: int  # Switches in current window

class OscillationDetector:
    """
    Detect and suppress rapid attention switching (oscillation)
    
    Problem: User glances between two objects repeatedly
    Solution: Suppress both objects temporarily, force clarity
    
    Week 7: Critical for preventing thrashing in cluttered scenes
    
    Design:
    - Track focus switches in a time window (e.g., 3 seconds)
    - If >N switches detected (e.g., 3), suppress all involved objects
    - Suppression lasts for duration (e.g., 2 seconds)
    - Cooldown period before re-detection
    """
    
    def __init__(self, config: dict):
        self.config = config
        
        # Oscillation detection
        oscillation_config = config.get('oscillation', {})
        self.window_seconds = oscillation_config.get('window_seconds', 3.0)
        self.switch_threshold = oscillation_config.get('switch_threshold', 3)
        self.suppress_duration = oscillation_config.get('suppress_duration_seconds', 2.0)
        self.cooldown_frames = oscillation_config.get('cooldown_frames', 10)
        
        # State
        self.switch_history: Deque[FocusSwitch] = deque(maxlen=20)
        self.suppressed_ids: List[str] = []
        self.suppressed_until: Optional[float] = None
        self.cooldown_counter = 0
        
        # Statistics
        self.total_updates = 0
        self.oscillation_events = 0
        self.total_suppressions = 0
    
    def update(self,
               primary_id: Optional[str],
               timestamp: float) -> OscillationResult:
        """
        Update oscillation detector with new primary focus
        
        Args:
            primary_id: Current primary object ID (or None)
            timestamp: Current timestamp
        
        Returns:
            OscillationResult with suppression info
        """
        self.total_updates += 1
        
        # Check if suppression expired
        if self.suppressed_until and timestamp >= self.suppressed_until:
            # Suppression period over
            self.suppressed_ids = []
            self.suppressed_until = None
            self.cooldown_counter = self.cooldown_frames
        
        # Cooldown (gradual re-enable after suppression)
        if self.cooldown_counter > 0:
            self.cooldown_counter -= 1
            if self.cooldown_counter == 0:
                # Cooldown complete - clear history to start fresh
                self.switch_history.clear()
        
        # Record switch if primary changed
        if len(self.switch_history) > 0:
            last_switch = self.switch_history[-1]
            if primary_id != last_switch.to_id and primary_id is not None:
                # Focus switched
                self.switch_history.append(FocusSwitch(
                    from_id=last_switch.to_id,
                    to_id=primary_id,
                    timestamp=timestamp
                ))
        elif primary_id is not None:
            # First focus
            self.switch_history.append(FocusSwitch(
                from_id=None,
                to_id=primary_id,
                timestamp=timestamp
            ))
        
        # Detect oscillation in recent window
        recent_switches = [
            s for s in self.switch_history
            if (timestamp - s.timestamp) <= self.window_seconds
        ]
        
        if len(recent_switches) >= self.switch_threshold:
            # Oscillation detected!
            # Find which objects are involved
            involved_ids = set()
            for switch in recent_switches:
                if switch.from_id:
                    involved_ids.add(switch.from_id)
                involved_ids.add(switch.to_id)
            
            # Suppress all involved objects
            if len(involved_ids) >= 2:
                self.suppressed_ids = list(involved_ids)
                self.suppressed_until = timestamp + self.suppress_duration
                self.oscillation_events += 1
                self.total_suppressions += len(involved_ids)
                
                return OscillationResult(
                    oscillating=True,
                    suppressed_ids=self.suppressed_ids,
                    suppressed_until=self.suppressed_until,
                    reason=f"Oscillation detected: {len(recent_switches)} switches between {len(involved_ids)} objects in {self.window_seconds}s",
                    switch_count=len(recent_switches)
                )
        
        # No oscillation (but may still be suppressed from earlier)
        return OscillationResult(
            oscillating=False,
            suppressed_ids=self.suppressed_ids,  # May still be suppressed from earlier
            suppressed_until=self.suppressed_until,
            reason="No oscillation" if len(self.suppressed_ids) == 0 else f"Suppressing {len(self.suppressed_ids)} objects until {self.suppressed_until - timestamp:.1f}s",
            switch_count=len(recent_switches)
        )
    
    def is_suppressed(self, object_id: str, timestamp: float) -> bool:
        """
        Check if an object is currently suppressed
        
        Args:
            object_id: Object track ID
            timestamp: Current timestamp
        
        Returns:
            True if object is suppressed
        """
        if self.suppressed_until is None or timestamp >= self.suppressed_until:
            return False
        return object_id in self.suppressed_ids
    
    def reset(self):
        """Reset oscillation state"""
        self.switch_history.clear()
        self.suppressed_ids = []
        self.suppressed_until = None
        self.cooldown_counter = 0
        self.total_updates = 0
        self.oscillation_events = 0
        self.total_suppressions = 0
    
    def get_statistics(self) -> dict:
        """Get oscillation statistics"""
        return {
            'total_updates': self.total_updates,
            'oscillation_events': self.oscillation_events,
            'total_suppressions': self.total_suppressions,
            'oscillation_rate': self.oscillation_events / max(1, self.total_updates),
            'current_suppressed_count': len(self.suppressed_ids),
            'cooldown_active': self.cooldown_counter > 0
        }




