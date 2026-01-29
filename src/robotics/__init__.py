"""
Robotics simulation module for hybrid BCI control.
Week 1: Static arm + physics world.
Week 5: IK + trajectory + autonomous execution.
Week 6: Grasping physics + gripper simulation.
Week 8: Recovery + safety monitoring.
"""

from .arm_model import ArmModel
from .arm_state import ArmState, read_arm_state
from .arm_simulator import ArmSimulator
from .action_types import ArmActionType
from .arm_actions import ACTION_SPECS, get_action_spec, get_goal_pose, is_executable, requires_grasp_attach
from .ik_solver import solve_ik
from .trajectory import TrajectoryPlan, plan_steps
from .safety_limits import clamp_joint_targets, within_limits, compute_pose_error
from .execution_result import ExecutionResult
from .arm_controller import ArmController
from .gripper_state import GripperState, GripperSnapshot
from .grasp_logic import GraspLogic
from .safety_monitor import SafetyMonitor
from .recovery import PauseTrigger, RecoveryPlan, ArmRecoveryController

__all__ = [
    'ArmModel',
    'ArmState',
    'read_arm_state',
    'ArmSimulator',
    'ArmActionType',
    'ACTION_SPECS',
    'get_action_spec',
    'get_goal_pose',
    'is_executable',
    'requires_grasp_attach',
    'solve_ik',
    'TrajectoryPlan',
    'plan_steps',
    'clamp_joint_targets',
    'within_limits',
    'compute_pose_error',
    'ExecutionResult',
    'ArmController',
    'GripperState',
    'GripperSnapshot',
    'GraspLogic',
    'SafetyMonitor',
    'PauseTrigger',
    'RecoveryPlan',
    'ArmRecoveryController',
]
