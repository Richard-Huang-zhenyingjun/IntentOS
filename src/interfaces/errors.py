"""
Error taxonomy for execution failures.
Week 2: Explicit error codes enable intelligent recovery.
"""
from enum import Enum


class ErrorCode(Enum):
    """Explicit error codes for execution failures"""
    # No error
    NONE = "none"                        # No error occurred
    
    # Validation errors (compiler rejects before execution)
    OUT_OF_BOUNDS = "out_of_bounds"      # Object outside workspace
    IK_FAIL = "ik_fail"                  # Inverse kinematics failed
    OBJECT_MISSING = "object_missing"    # Object not found in scene
    
    # Execution errors (during primitive execution)
    TIMEOUT = "timeout"                   # Primitive exceeded time limit
    GRASP_FAIL = "grasp_fail"            # Grasp constraint failed to attach
    RELEASE_FAIL = "release_fail"        # Release constraint failed
    MOTION_FAIL = "motion_fail"          # Controller failed to converge
    
    # Object-level errors
    OBJECT_TIMEOUT = "object_timeout"    # Entire object sequence timed out
    
    # Unknown/unexpected
    UNKNOWN = "unknown"


class ExecStatus(Enum):
    """Execution status for primitives and tasks"""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    SKIPPED = "skipped"  # Object skipped due to validation failure

