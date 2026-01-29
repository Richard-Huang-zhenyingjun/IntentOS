"""
Arm action specifications - semantics and availability rules.
Week 2: Preconditions + goals defined, no execution.
Week 5+: Execution logic added.
"""

from dataclasses import dataclass
from typing import Dict, Any, Callable, TYPE_CHECKING, Optional
import numpy as np
from .action_types import ArmActionType

if TYPE_CHECKING:
    from src.world.world_model import WorldModel


def distance_xy(pos_a: np.ndarray, pos_b: np.ndarray) -> float:
    """Compute XY-plane distance between two 3D positions."""
    return np.linalg.norm(pos_a[:2] - pos_b[:2])


def distance_3d(pos_a: np.ndarray, pos_b: np.ndarray) -> float:
    """Compute 3D Euclidean distance between two positions."""
    return np.linalg.norm(pos_a - pos_b)


@dataclass
class ArmActionSpec:
    """
    Action specification - semantics without execution.
    
    Attributes:
        action_type: Action identifier
        description: Human-readable description
        goal_hint: High-level goal parameters (used in Week 5+ for IK)
        precondition: Function(world_model) -> bool (is action available?)
        success_condition: Function(world_model) -> bool (is goal achieved?)
        undo_hint: Metadata for undo (Week 8+)
    """
    action_type: ArmActionType
    description: str
    goal_hint: Dict[str, Any]
    precondition: Callable[['WorldModel'], bool]
    success_condition: Callable[['WorldModel'], bool]
    undo_hint: Dict[str, Any]


# ============================================================================
# Action Preconditions (availability rules)
# ============================================================================

def move_up_available(world: 'WorldModel') -> bool:
    """
    MOVE_ARM_UP is available if EE is below minimum height.
    
    Logic: Arm needs to lift before reaching forward.
    """
    ee_z = world.arm_state.ee_pos[2]
    min_z = world.cfg['thresholds']['ee_min_z']
    return ee_z < min_z


def reach_forward_available(world: 'WorldModel') -> bool:
    """
    REACH_FORWARD is available if:
    - Object is visible
    - EE is at sufficient height
    - EE is far from object in XY plane
    
    Logic: After lifting, move toward object.
    """
    if not world.object_state.visible:
        return False
    
    ee_z = world.arm_state.ee_pos[2]
    min_z = world.cfg['thresholds']['ee_min_z']
    
    if ee_z < min_z:
        return False  # Must lift first
    
    dist_xy = distance_xy(world.arm_state.ee_pos, world.object_state.pos)
    threshold = world.cfg['thresholds']['reach_close_xy']
    
    return dist_xy > threshold


def grasp_available(world: 'WorldModel') -> bool:
    """
    GRASP_OBJECT is available if:
    - Object is visible
    - EE is close to object in 3D space
    
    Logic: After reaching, grasp when within threshold.
    """
    if not world.object_state.visible:
        return False
    
    dist_3d = distance_3d(world.arm_state.ee_pos, world.object_state.pos)
    threshold = world.cfg['thresholds']['grasp_dist']
    
    return dist_3d < threshold


def place_available(world: 'WorldModel') -> bool:
    """
    PLACE_OBJECT is available if:
    - Currently holding an object
    - End-effector is close to place zone
    """
    # Must be holding something
    if not world.is_holding_any():
        return False
    
    # Must be at place zone
    place_pos = np.array(world.cfg['place_zone']['position'])
    ee_pos = world.arm_state.ee_pos
    dist_3d = distance_3d(ee_pos, place_pos)
    threshold = world.cfg['place_zone']['place_dist_threshold']
    
    return dist_3d < threshold


# ============================================================================
# Action Success Conditions (goal achievement)
# ============================================================================

def move_up_success(world: 'WorldModel') -> bool:
    """MOVE_ARM_UP succeeds when EE reaches target height."""
    ee_z = world.arm_state.ee_pos[2]
    target_z = world.cfg['thresholds']['ee_target_z']
    return ee_z >= target_z


def reach_forward_success(world: 'WorldModel') -> bool:
    """REACH_FORWARD succeeds when EE is close to object in XY."""
    dist_xy = distance_xy(world.arm_state.ee_pos, world.object_state.pos)
    threshold = world.cfg['thresholds']['reach_close_xy']
    return dist_xy <= threshold


def grasp_success(world: 'WorldModel') -> bool:
    """
    GRASP_OBJECT succeeds when object is attached.
    Week 2: Always True (placeholder - Week 7 adds real grasp physics).
    """
    return True  # Placeholder


def place_success(world: 'WorldModel') -> bool:
    """
    PLACE_OBJECT succeeds if:
    - Object is released (no longer holding)
    """
    # Success if no longer holding object
    return not world.is_holding_any()


# ============================================================================
# Action Specifications (the 3 core actions)
# ============================================================================

ACTION_SPECS = {
    ArmActionType.MOVE_ARM_UP: ArmActionSpec(
        action_type=ArmActionType.MOVE_ARM_UP,
        description="Lift end effector to safe height before reaching",
        goal_hint={
            "target_delta_z": 0.10  # Lift by 10cm (Week 5: used for trajectory)
        },
        precondition=move_up_available,
        success_condition=move_up_success,
        undo_hint={"reverse_delta_z": -0.10}
    ),
    
    ArmActionType.REACH_FORWARD: ArmActionSpec(
        action_type=ArmActionType.REACH_FORWARD,
        description="Move end effector toward object pre-grasp position",
        goal_hint={
            "target_offset": [0.0, 0.0, 0.10]  # 10cm above object (Week 5: IK target)
        },
        precondition=reach_forward_available,
        success_condition=reach_forward_success,
        undo_hint={"retreat": True}
    ),
    
    ArmActionType.GRASP_OBJECT: ArmActionSpec(
        action_type=ArmActionType.GRASP_OBJECT,
        description="Close gripper and attach object to end effector",
        goal_hint={
            "grasp_constraint": "fixed"  # Week 7: creates constraint
        },
        precondition=grasp_available,
        success_condition=grasp_success,
        undo_hint={"release": True}
    ),
    
    ArmActionType.PLACE_OBJECT: ArmActionSpec(
        action_type=ArmActionType.PLACE_OBJECT,
        description="Place held object in place zone",
        goal_hint={
            "place_zone": "center"  # Place at configured place zone
        },
        precondition=place_available,
        success_condition=place_success,
        undo_hint={"regrasp": True}
    ),
}


def get_action_spec(action_type: ArmActionType) -> ArmActionSpec:
    """Retrieve action specification by type."""
    return ACTION_SPECS[action_type]


def get_goal_pose(action_type: ArmActionType, 
                  world: 'WorldModel',
                  cfg: dict) -> tuple[np.ndarray, Optional[np.ndarray], str]:
    """
    Compute target end-effector pose for action.
    
    Args:
        action_type: Action to execute
        world: WorldModel with current state
        cfg: Configuration dict
        
    Returns:
        (target_pos, target_orn, reason) where:
        - target_pos: Target position [x, y, z]
        - target_orn: Target orientation (None to keep current)
        - reason: Why this pose was chosen
    """
    if action_type == ArmActionType.MOVE_ARM_UP:
        return _goal_pose_move_up(world, cfg)
    elif action_type == ArmActionType.REACH_FORWARD:
        return _goal_pose_reach_forward(world, cfg)
    elif action_type == ArmActionType.GRASP_OBJECT:
        return _goal_pose_grasp(world, cfg)
    elif action_type == ArmActionType.PLACE_OBJECT:
        return _goal_pose_place(world, cfg)
    else:
        raise ValueError(f"Unknown action type: {action_type}")


def _goal_pose_move_up(world: 'WorldModel', cfg: dict) -> tuple[np.ndarray, None, str]:
    """Compute goal pose for MOVE_ARM_UP."""
    current_pos = world.arm_state.ee_pos
    delta_z = cfg['actions']['move_up']['delta_z']
    min_z = cfg['actions']['move_up']['min_z']
    max_z = cfg['actions']['move_up']['max_z']
    
    target_z = current_pos[2] + delta_z
    target_z = max(min_z, min(max_z, target_z))  # Clamp
    
    target_pos = np.array([current_pos[0], current_pos[1], target_z])
    
    reason = f"Lift end effector from z={current_pos[2]:.2f}m to z={target_z:.2f}m"
    
    return target_pos, None, reason


def _goal_pose_reach_forward(world: 'WorldModel', cfg: dict) -> tuple[np.ndarray, None, str]:
    """Compute goal pose for REACH_FORWARD."""
    obj_pos = world.object_state.pos
    approach_height = cfg['actions']['reach_forward']['approach_height_z']
    max_reach = cfg['actions']['reach_forward']['max_reach_dist_m']
    
    # Target: above object
    target_pos = np.array([obj_pos[0], obj_pos[1], obj_pos[2] + approach_height])
    
    # Safety: clamp reach distance from robot base
    robot_base = np.array([0.0, 0.0, 0.6])  # From config
    reach_dist = np.linalg.norm(target_pos[:2] - robot_base[:2])
    
    if reach_dist > max_reach:
        # Scale back to max reach
        direction = (target_pos[:2] - robot_base[:2]) / reach_dist
        target_pos[:2] = robot_base[:2] + direction * max_reach
    
    reason = f"Move end effector to pre-grasp position above object ({reach_dist:.2f}m reach)"
    
    return target_pos, None, reason


def _goal_pose_grasp(world: 'WorldModel', cfg: dict) -> tuple[np.ndarray, None, str]:
    """Compute goal pose for GRASP_OBJECT (Week 6: now functional)."""
    obj_pos = world.object_state.pos
    approach_height = cfg['grasp']['pregrasp_height_z']
    
    # Target: same as reach_forward (above object)
    target_pos = np.array([obj_pos[0], obj_pos[1], obj_pos[2] + approach_height])
    
    # Check if already in position
    ee_pos = world.arm_state.ee_pos
    dist = distance_3d(ee_pos, obj_pos)
    
    if dist < cfg['grasp']['attach_dist_m']:
        reason = f"At grasp position (dist={dist:.3f}m) - ready to attach"
    else:
        reason = f"Moving to grasp position (dist={dist:.3f}m)"
    
    return target_pos, None, reason


def _goal_pose_place(world: 'WorldModel', cfg: dict) -> tuple[np.ndarray, None, str]:
    """
    Compute goal pose for PLACE_OBJECT: above place zone.
    
    Returns:
        (target_pos, target_orn, reason) where:
        - target_pos: Target position above place zone
        - target_orn: None (keep current orientation)
        - reason: Why this pose was chosen
    """
    place_cfg = cfg['place_zone']
    place_pos = np.array(place_cfg['position'])
    approach_height = place_cfg['approach_height_z']
    
    # Target position: above place zone
    target_pos = place_pos.copy()
    target_pos[2] += approach_height  # 10cm above surface
    
    # Check current distance
    ee_pos = world.arm_state.ee_pos
    dist = distance_3d(ee_pos, place_pos)
    
    if dist < place_cfg['place_dist_threshold']:
        reason = f"At place zone (dist={dist:.3f}m) - ready to place"
    else:
        reason = f"Moving to place zone (dist={dist:.3f}m)"
    
    return target_pos, None, reason


def is_executable(action_type: ArmActionType) -> bool:
    """
    Check if action is executable in current week.
    
    Week 5: MOVE_UP and REACH_FORWARD.
    Week 6: Add GRASP_OBJECT.
    Week 7+: Add PLACE_OBJECT.
    """
    return action_type in [
        ArmActionType.MOVE_ARM_UP,
        ArmActionType.REACH_FORWARD,
        ArmActionType.GRASP_OBJECT,  # Week 6: Now executable
        ArmActionType.PLACE_OBJECT   # Week 7+: Now executable
    ]


def requires_grasp_attach(action_type: ArmActionType) -> bool:
    """
    Check if action requires grasp attachment.
    
    Week 6: Only GRASP_OBJECT.
    
    Args:
        action_type: Action to check
        
    Returns:
        True if action needs attachment logic
    """
    return action_type == ArmActionType.GRASP_OBJECT

