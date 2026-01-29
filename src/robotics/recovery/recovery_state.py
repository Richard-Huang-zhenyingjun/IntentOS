"""
Recovery states - state machine for pause/recovery flow.
Week 8: Formal pause semantics with no auto-resume.
"""

from enum import Enum


class RecoveryState(str, Enum):
    """
    Recovery state machine states.
    
    Week 8: Once paused, system never auto-resumes.
    User must explicitly re-select target to continue.
    """
    NORMAL = "normal"                   # No issues, operating normally
    GRACE = "grace"                     # Issue detected, grace period active
    PAUSED = "paused"                   # Execution paused, awaiting user action
    RECOVERING = "recovering"           # User initiated recovery (reserved)
    
    def is_operational(self) -> bool:
        """Can system execute actions in this state?"""
        return self == RecoveryState.NORMAL
    
    def is_frozen(self) -> bool:
        """Should robot motion be frozen?"""
        return self in (RecoveryState.PAUSED, RecoveryState.RECOVERING)




