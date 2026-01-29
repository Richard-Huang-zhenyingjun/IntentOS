"""
Pause triggers - reasons for pausing execution.
Week 8: Safety-first approach to failure handling.
"""

from enum import Enum


class PauseTrigger(str, Enum):
    """
    Reasons for pausing execution.
    
    Week 8: Each trigger has specific recovery requirements.
    """
    EEG_UNSTABLE = "eeg_unstable"           # EEG signal unstable
    EEG_DROPOUT = "eeg_dropout"             # EEG disconnected
    TARGET_LOST = "target_lost"             # Selected object disappeared
    SELECTION_UNSTABLE = "selection_unstable"  # Selection flickering
    ACTION_TIMEOUT = "action_timeout"       # Action took too long
    CANCEL_REQUESTED = "cancel_requested"   # User cancelled
    COLLISION_RISK = "collision_risk"       # Collision detected (reserved)
    
    def get_explanation(self) -> str:
        """Get human-readable explanation."""
        explanations = {
            PauseTrigger.EEG_UNSTABLE: "EEG signal became unstable",
            PauseTrigger.EEG_DROPOUT: "EEG connection lost",
            PauseTrigger.TARGET_LOST: "Target object lost from view",
            PauseTrigger.SELECTION_UNSTABLE: "Target selection unstable",
            PauseTrigger.ACTION_TIMEOUT: "Action execution timed out",
            PauseTrigger.CANCEL_REQUESTED: "User requested cancellation",
            PauseTrigger.COLLISION_RISK: "Collision risk detected",
        }
        return explanations.get(self, "Unknown pause trigger")




