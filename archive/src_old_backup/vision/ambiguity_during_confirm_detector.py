"""
Ambiguity During Confirm Detector - Week 7 Failure Recovery

Detects ambiguity that appears during confirmation gesture.
Prevents confirmations when intent becomes unclear mid-gesture.
"""

from typing import Optional, Tuple
from intent_core.schema import SystemState

# Import RankedCandidates if available
try:
    from src.vision.candidate_ranker import RankedCandidates
except ImportError:
    RankedCandidates = None  # Fallback


class AmbiguityDuringConfirmDetector:
    """
    Detect ambiguity appearing during confirmation
    
    Problem: User confirms, then second object enters scene
    Solution: Detect ambiguity during vulnerable states, pause
    
    Week 7: Prevents executing on wrong object
    
    Design:
    - Monitor ambiguity during CONFIRMING and EXECUTING states
    - Use RankedCandidates for detailed reason
    - Trigger PAUSE immediately if ambiguity appears
    - Require user to re-establish clear scope
    """
    
    def __init__(self, config: dict):
        self.config = config
        
        # Config
        ambiguity_config = config.get('ambiguity_during_confirm', {})
        self.pause_on_ambiguity = ambiguity_config.get('pause_on_ambiguity', True)
        
        # State
        self.was_in_vulnerable_state = False
        
        # Statistics
        self.total_checks = 0
        self.ambiguity_events = 0
    
    def check(self,
              ranked_candidates: 'RankedCandidates',
              system_state: SystemState,
              timestamp: float) -> Tuple[bool, str]:
        """
        Check if ambiguity appeared during vulnerable state
        
        Args:
            ranked_candidates: Current ranking result
            system_state: Current system state
            timestamp: Current timestamp
        
        Returns:
            (should_pause, reason) tuple
            - should_pause: True if ambiguity appeared during vulnerable state
            - reason: Human-readable explanation with details
        """
        self.total_checks += 1
        
        # Only check during vulnerable states
        vulnerable_states = [
            SystemState.CONFIRMING,
            SystemState.EXECUTING
        ]
        
        if system_state not in vulnerable_states:
            self.was_in_vulnerable_state = False
            return (False, "")
        
        self.was_in_vulnerable_state = True
        
        # Check if ambiguity detected
        if ranked_candidates.ambiguity_detected and self.pause_on_ambiguity:
            # Ambiguity during vulnerable state - immediate pause
            self.ambiguity_events += 1
            return (True, f"Ambiguity during {system_state.value}: {ranked_candidates.reason}")
        
        return (False, "")
    
    def reset(self):
        """Reset detector state"""
        self.was_in_vulnerable_state = False
        self.total_checks = 0
        self.ambiguity_events = 0
    
    def get_statistics(self) -> dict:
        """Get detector statistics"""
        return {
            'total_checks': self.total_checks,
            'ambiguity_events': self.ambiguity_events,
            'ambiguity_rate': self.ambiguity_events / max(1, self.total_checks),
            'was_in_vulnerable_state': self.was_in_vulnerable_state
        }

