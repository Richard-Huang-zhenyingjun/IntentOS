"""
Safety monitor - detect runtime hazards.
Week 8: Continuous safety monitoring, pause-on-failure.
"""

from typing import Optional
import time
from .recovery.pause_triggers import PauseTrigger
from .recovery.recovery_plan import RecoveryPlan


class SafetyMonitor:
    """
    Monitors system for safety hazards.
    
    Checks:
    - EEG signal stability
    - Target object presence
    - Action timeout
    - (Future) Collision risk
    
    Week 8: Generates RecoveryPlan when hazards detected.
    """
    
    def __init__(self, cfg: dict):
        """
        Initialize safety monitor.
        
        Args:
            cfg: Configuration dict
        """
        self.cfg = cfg
        
        # Config shortcuts
        recovery_cfg = cfg['recovery']
        self.pause_on_eeg_unstable = recovery_cfg['pause_on']['eeg_unstable']
        self.pause_on_target_lost = recovery_cfg['pause_on']['target_lost']
        self.pause_on_timeout = recovery_cfg['pause_on']['action_timeout']
        
        self.target_loss_grace = recovery_cfg['target_loss_grace_frames']
        self.eeg_unstable_grace = recovery_cfg['eeg_unstable_grace_frames']
        
        # Tracking state
        self.target_lost_frames = 0
        self.eeg_unstable_frames = 0
        self.last_check_time = time.time()
    
    def check(self, world, state_machine, controller, eeg_status, target_selector) -> RecoveryPlan:
        """
        Check for safety hazards.
        
        Args:
            world: WorldModel instance
            state_machine: ArmStateMachine instance
            controller: ArmController instance
            eeg_status: EEG debug status dict
            target_selector: TargetSelector instance
            
        Returns:
            RecoveryPlan (should_pause=True if hazard detected)
        """
        # Only monitor during critical states
        if state_machine.state.value not in ['awaiting_confirm', 'executing']:
            # Reset counters in non-critical states
            self.target_lost_frames = 0
            self.eeg_unstable_frames = 0
            return RecoveryPlan.no_pause()
        
        # Check 1: EEG unstable
        if self.pause_on_eeg_unstable and eeg_status:
            if eeg_status.get('blocked', False) or not eeg_status.get('stable', True):
                self.eeg_unstable_frames += 1
                
                if self.eeg_unstable_frames > self.eeg_unstable_grace:
                    return RecoveryPlan.create(
                        PauseTrigger.EEG_UNSTABLE,
                        grace_remaining=0
                    )
            else:
                self.eeg_unstable_frames = 0
        
        # Check 2: Target lost
        if self.pause_on_target_lost:
            if not target_selector.is_locked() and world.target_object_id is not None:
                # Target was locked but now lost
                self.target_lost_frames += 1
                
                if self.target_lost_frames > self.target_loss_grace:
                    return RecoveryPlan.create(
                        PauseTrigger.TARGET_LOST,
                        grace_remaining=0
                    )
                else:
                    # Still in grace period
                    grace_remaining = self.target_loss_grace - self.target_lost_frames
                    return RecoveryPlan(
                        should_pause=False,
                        trigger=PauseTrigger.TARGET_LOST,
                        explanation=f"Target unstable (grace: {grace_remaining} frames)",
                        grace_remaining=grace_remaining
                    )
            else:
                self.target_lost_frames = 0
        
        # Check 3: Action timeout
        if self.pause_on_timeout and controller.is_active():
            max_steps = self.cfg['control']['max_steps_per_action']
            if controller.steps_used > max_steps:
                return RecoveryPlan.create(PauseTrigger.ACTION_TIMEOUT)
        
        # Check 4: Collision risk (reserved for future)
        # if self.pause_on_collision:
        #     if self._check_collision():
        #         return RecoveryPlan.create(PauseTrigger.COLLISION_RISK)
        
        # No hazards detected
        return RecoveryPlan.no_pause()
    
    def reset(self) -> None:
        """Reset monitoring state."""
        self.target_lost_frames = 0
        self.eeg_unstable_frames = 0




