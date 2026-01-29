"""
Arm recovery controller - orchestrate pause/resume decisions.
Week 8: Enforce safety invariants, never auto-resume.
"""

from typing import Optional
from .pause_triggers import PauseTrigger
from .recovery_plan import RecoveryPlan


class ArmRecoveryController:
    """
    Manages pause/recovery lifecycle.
    
    Responsibilities:
    - Evaluate safety conditions
    - Generate recovery plans
    - Track recovery progress
    - Enforce "no auto-resume" invariant
    
    Week 8: Paper-aligned "pause > partial execution" philosophy.
    """
    
    def __init__(self, cfg: dict):
        """
        Initialize recovery controller.
        
        Args:
            cfg: Configuration dict
        """
        self.cfg = cfg
        self.paused = False
        self.active_plan: Optional[RecoveryPlan] = None
        self.pause_start_time: Optional[float] = None
    
    def trigger_pause(self, plan: RecoveryPlan) -> None:
        """
        Trigger pause with recovery plan.
        
        Args:
            plan: RecoveryPlan specifying requirements
        """
        if not self.paused:
            self.paused = True
            self.active_plan = plan
            import time
            self.pause_start_time = time.time()
            
            print(f"⚠️  PAUSED: {plan.trigger}")
            print(f"   Reason: {plan.explanation}")
            print(f"   Recovery steps:")
            for i, step in enumerate(plan.required_steps, 1):
                print(f"     {i}. {step}")
    
    def check_recovery_ready(self, world, eeg_status, target_selector) -> bool:
        """
        Check if recovery conditions are met.
        
        Args:
            world: WorldModel instance
            eeg_status: EEG debug status dict
            target_selector: TargetSelector instance
            
        Returns:
            True if ready to exit PAUSED state
        """
        if not self.paused or self.active_plan is None:
            return False
        
        return self.active_plan.is_recovery_complete(world, eeg_status, target_selector)
    
    def clear_pause(self) -> None:
        """Clear pause state after recovery."""
        if self.paused:
            print("✓ Recovery complete, resuming")
            self.paused = False
            self.active_plan = None
            self.pause_start_time = None
    
    def get_status(self) -> dict:
        """
        Get recovery controller status.
        
        Returns:
            Dict with pause state and plan info
        """
        if not self.paused or self.active_plan is None:
            return {
                "paused": False,
                "trigger": None,
                "explanation": "",
                "required_steps": [],
            }
        
        import time
        pause_duration = time.time() - self.pause_start_time if self.pause_start_time else 0.0
        
        return {
            "paused": True,
            "trigger": str(self.active_plan.trigger),
            "explanation": self.active_plan.explanation,
            "required_steps": self.active_plan.required_steps,
            "pause_duration": pause_duration,
        }




