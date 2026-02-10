"""
Autonomy level governance.

Levels:
- A1_MICRO_CONFIRM: User confirms each object individually
- A2_TASK_CONFIRM: One confirm authorizes full session (current default)

Rules:
- Autonomy level NEVER auto-increases (only user action can increase)
- System CAN decrease autonomy (A2 → A1) on trust drop, but only via re-auth
- Config-driven, no ML
"""
import logging
from enum import Enum
from dataclasses import dataclass
from src.core.authorization import AuthScope

logger = logging.getLogger(__name__)


class AutonomyLevel(Enum):
    """Shared autonomy gearbox"""
    A1_MICRO_CONFIRM = "A1_MICRO_CONFIRM"    # Confirm per object
    A2_TASK_CONFIRM = "A2_TASK_CONFIRM"      # Confirm per session


# Map autonomy level to token scope
AUTONOMY_TO_SCOPE = {
    AutonomyLevel.A1_MICRO_CONFIRM: AuthScope.SINGLE_OBJECT,
    AutonomyLevel.A2_TASK_CONFIRM: AuthScope.TASK_SESSION,
}

# Map autonomy level to max_objects for token
AUTONOMY_MAX_OBJECTS = {
    AutonomyLevel.A1_MICRO_CONFIRM: 1,
    AutonomyLevel.A2_TASK_CONFIRM: 0,  # 0 = unlimited
}


@dataclass
class AutonomyPolicy:
    """Parsed autonomy policy from config"""
    level: AutonomyLevel
    allow_auto_decrease: bool
    decrease_trust_threshold: float
    decrease_consecutive_failures: int
    
    @staticmethod
    def from_config(config: dict) -> 'AutonomyPolicy':
        auto_cfg = config.get('autonomy', {})
        decrease_cfg = auto_cfg.get('decrease_on', {})
        
        level_str = auto_cfg.get('level', 'A2_TASK_CONFIRM')
        try:
            level = AutonomyLevel(level_str)
        except ValueError:
            level = AutonomyLevel.A2_TASK_CONFIRM
        
        return AutonomyPolicy(
            level=level,
            allow_auto_decrease=auto_cfg.get('allow_auto_decrease', True),
            decrease_trust_threshold=decrease_cfg.get('trust_below', 0.55),
            decrease_consecutive_failures=decrease_cfg.get('consecutive_failures', 2),
        )
    
    def get_token_scope(self) -> AuthScope:
        return AUTONOMY_TO_SCOPE[self.level]
    
    def get_max_objects(self) -> int:
        return AUTONOMY_MAX_OBJECTS[self.level]


