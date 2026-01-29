"""
Recovery controller - monitors failures and triggers pauses.
Week 8: Safety-first approach with grace periods and no auto-resume.
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass, field
import time

from .pause_triggers import PauseTrigger
from .recovery_state import RecoveryState


@dataclass
class RecoveryStatus:
    """
    Current recovery status.
    
    Provides transparent view of what's happening and why.
    """
    state: RecoveryState
    trigger: Optional[PauseTrigger] = None
    explanation: str = ""
    paused_at: Optional[float] = None
    grace_frames_remaining: int = 0
    
    def is_paused(self) -> bool:
        """Is system currently paused?"""
        return self.state in (RecoveryState.PAUSED, RecoveryState.RECOVERING)
    
    def can_execute(self) -> bool:
        """Can system execute actions?"""
        return self.state.is_operational()
    
    def should_freeze_motion(self) -> bool:
        """Should robot motion be frozen?"""
        return self.state.is_frozen()


class RecoveryController:
    """
    Recovery controller - detects failures and triggers pauses.
    
    Week 8 design:
    - Grace periods before pause (avoid false positives)
    - Explicit pause triggers with explanations
    - Never auto-resume (user must re-select target)
    - Freeze robot motion when paused
    
    Philosophy: Better to pause than execute incorrectly.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize recovery controller.
        
        Args:
            config: Recovery section from robotics.yaml
        """
        self.config = config
        self.enabled = config.get("enable", True)
        
        # Pause triggers configuration
        self.pause_on = config.get("pause_on", {})
        
        # Grace periods (frames before pause)
        self.target_loss_grace = config.get("target_loss_grace_frames", 10)
        self.eeg_unstable_grace = config.get("eeg_unstable_grace_frames", 30)
        
        # Recovery requirements
        self.require_rescope = config.get("require_rescope_after_pause", True)
        self.clear_confirmation = config.get("clear_confirmation_on_pause", True)
        self.freeze_on_pause = config.get("freeze_on_pause", True)
        
        # State
        self._state = RecoveryState.NORMAL
        self._current_trigger: Optional[PauseTrigger] = None
        self._paused_at: Optional[float] = None
        
        # Grace period tracking
        self._grace_counters: Dict[PauseTrigger, int] = {}
        
    def reset(self):
        """Reset to normal state (used after successful target re-selection)."""
        self._state = RecoveryState.NORMAL
        self._current_trigger = None
        self._paused_at = None
        self._grace_counters.clear()
    
    def get_status(self) -> RecoveryStatus:
        """Get current recovery status."""
        explanation = ""
        grace_remaining = 0
        
        if self._state == RecoveryState.GRACE and self._current_trigger:
            grace_remaining = self._get_grace_frames(self._current_trigger) - \
                              self._grace_counters.get(self._current_trigger, 0)
            explanation = f"Grace period: {self._current_trigger.get_explanation()}"
        elif self._state == RecoveryState.PAUSED and self._current_trigger:
            explanation = f"PAUSED: {self._current_trigger.get_explanation()}"
        elif self._state == RecoveryState.NORMAL:
            explanation = "System operational"
        
        return RecoveryStatus(
            state=self._state,
            trigger=self._current_trigger,
            explanation=explanation,
            paused_at=self._paused_at,
            grace_frames_remaining=grace_remaining
        )
    
    def check_eeg_stable(self, is_stable: bool) -> bool:
        """
        Check EEG stability.
        
        Args:
            is_stable: Whether EEG signal is currently stable
            
        Returns:
            True if check passed (system can continue), False if paused
        """
        if not self.enabled or not self.pause_on.get("eeg_unstable", True):
            return True
        
        if self._state.is_frozen():
            return False  # Already paused
        
        if is_stable:
            # Reset grace counter
            self._grace_counters[PauseTrigger.EEG_UNSTABLE] = 0
            if self._state == RecoveryState.GRACE and \
               self._current_trigger == PauseTrigger.EEG_UNSTABLE:
                self._state = RecoveryState.NORMAL
                self._current_trigger = None
            return True
        
        # Unstable - increment grace counter
        return self._handle_trigger(PauseTrigger.EEG_UNSTABLE)
    
    def check_eeg_connected(self, is_connected: bool) -> bool:
        """
        Check EEG connection.
        
        Args:
            is_connected: Whether EEG is currently connected
            
        Returns:
            True if check passed, False if paused
        """
        if not self.enabled:
            return True
        
        if self._state.is_frozen():
            return False
        
        if not is_connected:
            # EEG dropout - pause immediately (no grace period)
            self._trigger_pause(PauseTrigger.EEG_DROPOUT)
            return False
        
        return True
    
    def check_target_visible(self, is_visible: bool) -> bool:
        """
        Check target visibility.
        
        Args:
            is_visible: Whether target is currently visible
            
        Returns:
            True if check passed, False if paused
        """
        if not self.enabled or not self.pause_on.get("target_lost", True):
            return True
        
        if self._state.is_frozen():
            return False
        
        if is_visible:
            # Reset grace counter
            self._grace_counters[PauseTrigger.TARGET_LOST] = 0
            if self._state == RecoveryState.GRACE and \
               self._current_trigger == PauseTrigger.TARGET_LOST:
                self._state = RecoveryState.NORMAL
                self._current_trigger = None
            return True
        
        # Target lost - use grace period
        return self._handle_trigger(PauseTrigger.TARGET_LOST)
    
    def check_action_timeout(self, action_started_time: Optional[float], 
                            max_duration: float) -> bool:
        """
        Check if action has timed out.
        
        Args:
            action_started_time: When action started (unix timestamp)
            max_duration: Maximum allowed duration (seconds)
            
        Returns:
            True if check passed, False if timed out
        """
        if not self.enabled or not self.pause_on.get("action_timeout", True):
            return True
        
        if self._state.is_frozen():
            return False
        
        if action_started_time is None:
            return True
        
        elapsed = time.time() - action_started_time
        if elapsed > max_duration:
            self._trigger_pause(PauseTrigger.ACTION_TIMEOUT)
            return False
        
        return True
    
    def trigger_cancel(self):
        """Trigger pause due to user cancellation."""
        if not self.enabled:
            return
        
        self._trigger_pause(PauseTrigger.CANCEL_REQUESTED)
    
    def _handle_trigger(self, trigger: PauseTrigger) -> bool:
        """
        Handle a potential trigger with grace period.
        
        Returns:
            True if still in grace, False if paused
        """
        grace_frames = self._get_grace_frames(trigger)
        
        if trigger not in self._grace_counters:
            self._grace_counters[trigger] = 0
        
        self._grace_counters[trigger] += 1
        
        if self._grace_counters[trigger] >= grace_frames:
            # Grace period expired - trigger pause
            self._trigger_pause(trigger)
            return False
        
        # Still in grace period
        if self._state == RecoveryState.NORMAL:
            self._state = RecoveryState.GRACE
            self._current_trigger = trigger
        
        return True
    
    def _trigger_pause(self, trigger: PauseTrigger):
        """Trigger immediate pause."""
        self._state = RecoveryState.PAUSED
        self._current_trigger = trigger
        self._paused_at = time.time()
        self._grace_counters.clear()
    
    def _get_grace_frames(self, trigger: PauseTrigger) -> int:
        """Get grace period for trigger (in frames)."""
        if trigger == PauseTrigger.TARGET_LOST:
            return self.target_loss_grace
        elif trigger == PauseTrigger.EEG_UNSTABLE:
            return self.eeg_unstable_grace
        else:
            return 0  # No grace period for other triggers
    
    @property
    def is_paused(self) -> bool:
        """Is system currently paused?"""
        return self._state in (RecoveryState.PAUSED, RecoveryState.RECOVERING)
    
    @property
    def should_freeze_motion(self) -> bool:
        """Should robot motion be frozen?"""
        return self.freeze_on_pause and self._state.is_frozen()
    
    @property
    def requires_rescope(self) -> bool:
        """Does recovery require target re-selection?"""
        return self.require_rescope and self.is_paused
    
    @property
    def should_clear_confirmation(self) -> bool:
        """Should confirmation be cleared on pause?"""
        return self.clear_confirmation and self.is_paused




