"""
Recovery plan - pause requirements and recovery steps.
Week 8: Explicit recovery requirements, never auto-resume.
"""

from dataclasses import dataclass
from typing import List, Optional
from .pause_triggers import PauseTrigger


@dataclass
class RecoveryPlan:
    """
    Recovery plan for pause/resume.
    
    Attributes:
        should_pause: Whether to trigger pause
        trigger: Pause trigger type
        explanation: Human-readable explanation
        required_steps: List of recovery requirements
        grace_remaining: Grace period remaining (frames)
    """
    should_pause: bool
    trigger: Optional[PauseTrigger] = None
    explanation: str = ""
    required_steps: List[str] = None
    grace_remaining: int = 0
    
    def __post_init__(self):
        """Initialize required_steps if None."""
        if self.required_steps is None:
            self.required_steps = []
    
    def is_recovery_complete(self, world, eeg_status, target_selector) -> bool:
        """
        Check if all recovery requirements are met.
        
        Args:
            world: WorldModel instance
            eeg_status: EEG debug status dict
            target_selector: TargetSelector instance
            
        Returns:
            True if recovery complete
        """
        if self.trigger == PauseTrigger.EEG_UNSTABLE or self.trigger == PauseTrigger.EEG_DROPOUT:
            # Require stable EEG
            if eeg_status and not eeg_status.get('stable', False):
                return False
            if eeg_status and eeg_status.get('blocked', True):
                return False
        
        if self.trigger == PauseTrigger.TARGET_LOST or self.trigger == PauseTrigger.SELECTION_UNSTABLE:
            # Require target re-locked
            if not target_selector.is_locked():
                return False
        
        if self.trigger == PauseTrigger.ACTION_TIMEOUT:
            # Require target re-select
            if not target_selector.is_locked():
                return False
        
        # All checks passed
        return True
    
    @staticmethod
    def no_pause() -> 'RecoveryPlan':
        """Create plan indicating no pause needed."""
        return RecoveryPlan(should_pause=False)
    
    @staticmethod
    def create(trigger: PauseTrigger, grace_remaining: int = 0) -> 'RecoveryPlan':
        """
        Create recovery plan for trigger.
        
        Args:
            trigger: Pause trigger
            grace_remaining: Grace frames remaining
            
        Returns:
            RecoveryPlan with requirements
        """
        explanation = trigger.get_explanation()
        
        # Determine required steps
        steps = []
        
        if trigger in [PauseTrigger.EEG_UNSTABLE, PauseTrigger.EEG_DROPOUT]:
            steps.append("Wait for EEG signal to stabilize")
            steps.append("Ensure good contact with headset")
            steps.append("Re-confirm action when stable")
        
        if trigger in [PauseTrigger.TARGET_LOST, PauseTrigger.SELECTION_UNSTABLE]:
            steps.append("Re-acquire target (gaze/mouse over object)")
            steps.append("Hold steady until target locks")
            steps.append("Re-confirm action when locked")
        
        if trigger == PauseTrigger.ACTION_TIMEOUT:
            steps.append("Action took too long - may be unreachable")
            steps.append("Re-select target to retry")
            steps.append("Consider adjusting target position")
        
        if trigger == PauseTrigger.CANCEL_REQUESTED:
            steps.append("Action cancelled")
            steps.append("Robot will return to safe pose")
            steps.append("Re-select target when ready")
        
        return RecoveryPlan(
            should_pause=True,
            trigger=trigger,
            explanation=explanation,
            required_steps=steps,
            grace_remaining=grace_remaining
        )




