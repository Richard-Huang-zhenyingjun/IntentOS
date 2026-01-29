"""
Execution result - structured outcome reporting.
Week 5: Report success/failure with diagnostic info.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ExecutionResult:
    """
    Result of action execution.
    
    Attributes:
        success: Whether execution succeeded
        reason: Human-readable outcome explanation
        steps_used: Number of simulation steps consumed
        final_error_pos: Final position error (meters)
        final_error_orn: Final orientation error (radians), if applicable
        action_type: Action that was executed
    """
    success: bool
    reason: str
    steps_used: int
    final_error_pos: float
    final_error_orn: Optional[float] = None
    action_type: Optional[str] = None
    
    def __repr__(self) -> str:
        """Human-readable summary."""
        status = "SUCCESS" if self.success else "FAILED"
        return (
            f"ExecutionResult({status}: {self.reason}, "
            f"steps={self.steps_used}, pos_err={self.final_error_pos:.3f}m)"
        )




