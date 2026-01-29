"""
World model - internal representation of robot + object state.
Implements paper's "world model determines available actions" concept.
Week 2: State tracking + action availability + proposal logic.
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass
import numpy as np

from robotics.arm_state import ArmState, read_arm_state
from perception.object_state import ObjectState, read_object_state
from robotics.action_types import ArmActionType
from robotics.arm_actions import ACTION_SPECS
from robotics.gripper_state import GripperState, GripperSnapshot


class WorldModel:
    """
    Internal world model for hybrid BCI control.
    
    Responsibilities:
        - Track robot arm state (joint angles, EE pose)
        - Track object state (position, velocity, visibility)
        - Compute available actions (precondition checks)
        - Propose next action (deterministic priority logic)
    
    Week 2: Read-only world state + availability rules.
    Week 5+: Add execution tracking.
    """
    
    def __init__(self, cfg: Dict[str, Any]):
        """
        Initialize world model.
        
        Args:
            cfg: Configuration dict from robotics.yaml
        """
        self.cfg = cfg
        
        # State (updated each frame)
        self.arm_state: Optional[ArmState] = None
        self.object_state: Optional[ObjectState] = None
        
        # Week 3: Target selection
        self.target_object_id: Optional[int] = None
        self.selection_locked: bool = False
        
        # Proposal tracking
        self.last_proposed_action: Optional[ArmActionType] = None
        
        # Week 6: Grasp state
        self.held_object_id: Optional[int] = None
        self.gripper_snapshot: Optional[GripperSnapshot] = None
    
        # Place zone target (for visualization/future use)
        self._place_zone_pos: Optional[np.ndarray] = None
    
    def update_from_sim(self, sim) -> None:
        """
        Update world model from simulator state.
        
        Args:
            sim: ArmSimulator instance
        """
        # Read robot state
        self.arm_state = read_arm_state(sim.robot)
        
        # Read object state
        self.object_state = read_object_state(sim.object_id)
    
    def set_target(self, object_id: Optional[int], locked: bool = False) -> None:
        """
        Set current target object.
        
        Args:
            object_id: Target object ID, or None to clear
            locked: Whether target is locked (stable)
        """
        self.target_object_id = object_id
        self.selection_locked = locked
    
    def set_target_place_zone(self, place_pos) -> None:
        """
        Set place zone as active target.
        
        This is used for visualization and consistency, but PLACE action
        doesn't strictly require a target to be set (it uses config position).
        
        Args:
            place_pos: [x, y, z] position of place zone (list or np.ndarray)
        """
        # Place zone doesn't have a body ID, so we use None
        # (target_object_id remains None for place zone)
        self.selection_locked = True
        
        # Store place zone position for visualization/future use
        self._place_zone_pos = np.array(place_pos) if not isinstance(place_pos, np.ndarray) else place_pos
        
        print(f"✓ Place zone set as target at {self._place_zone_pos}")
    
    def get_available_actions(self) -> list[ArmActionType]:
        """
        Compute which actions are currently available.
        
        Returns:
            List of action types that satisfy preconditions
        """
        if self.arm_state is None or self.object_state is None:
            return []
        
        available = []
        
        for action_type, spec in ACTION_SPECS.items():
            if spec.precondition(self):
                available.append(action_type)
        
        return available
    
    def propose_next_action(self) -> Optional[ArmActionType]:
        """
        Propose next action using deterministic priority logic.
        
        Priority (paper-aligned sequential task):
        1. MOVE_ARM_UP (if arm too low)
        2. REACH_FORWARD (if arm ready but far from object)
        3. GRASP_OBJECT (if arm at object)
        4. PLACE_OBJECT (if holding object and at place zone)
        
        Returns:
            Next action to execute, or None if no action available
        """
        print(f"\n[WORLD] propose_next_action() called")
        
        available = self.get_available_actions()
        print(f"[WORLD] Available actions: {available}")
        
        if not available:
            print(f"[WORLD] ❌ NO ACTIONS AVAILABLE")
            print(f"  Object visible: {self.object_state.visible}")
            print(f"  Object pos: {self.object_state.pos}")
            print(f"  EE pos: {self.arm_state.ee_pos}")
            self.last_proposed_action = None
            return None
        
        # Priority ordering
        priority = [
            ArmActionType.MOVE_ARM_UP,
            ArmActionType.REACH_FORWARD,
            ArmActionType.GRASP_OBJECT,
            ArmActionType.PLACE_OBJECT,  # NEW: Place after grasping
        ]
        
        for action in priority:
            if action in available:
                print(f"[WORLD] ✓ Proposing: {action}")
                self.last_proposed_action = action
                return action
        
        # Fallback (should never reach here)
        print(f"[WORLD] Using first available: {available[0]}")
        self.last_proposed_action = available[0]
        return available[0]
    
    def get_action_reason(self, action_type: ArmActionType) -> str:
        """
        Get human-readable reason why action was proposed.
        
        Args:
            action_type: Action to explain
            
        Returns:
            Explanation string
        """
        if self.arm_state is None or self.object_state is None:
            return "State not initialized"
        
        ee_z = self.arm_state.ee_pos[2]
        ee_pos = self.arm_state.ee_pos
        obj_pos = self.object_state.pos
        
        from robotics.arm_actions import distance_xy, distance_3d
        
        if action_type == ArmActionType.MOVE_ARM_UP:
            min_z = self.cfg['thresholds']['ee_min_z']
            return f"End effector too low (z={ee_z:.2f}m < {min_z:.2f}m)"
        
        elif action_type == ArmActionType.REACH_FORWARD:
            dist = distance_xy(ee_pos, obj_pos)
            threshold = self.cfg['thresholds']['reach_close_xy']
            return f"End effector far from target (xy_dist={dist:.2f}m > {threshold:.2f}m)"
        
        elif action_type == ArmActionType.GRASP_OBJECT:
            dist = distance_3d(ee_pos, obj_pos)
            threshold = self.cfg['thresholds']['grasp_dist']
            return f"End effector at target (dist={dist:.2f}m < {threshold:.2f}m)"
        
        else:
            return f"Unknown action: {action_type}"
    
    def set_grasp_state(self, gripper_snapshot: Optional[GripperSnapshot]) -> None:
        """
        Update grasp state from controller.
        
        Args:
            gripper_snapshot: Current gripper snapshot
        """
        self.gripper_snapshot = gripper_snapshot
        if gripper_snapshot:
            self.held_object_id = gripper_snapshot.holding_object_id
        else:
            self.held_object_id = None
    
    def is_object_held(self, object_id: int) -> bool:
        """
        Check if specific object is held.
        
        Args:
            object_id: Object ID to check
            
        Returns:
            True if this object is currently held
        """
        return self.held_object_id == object_id
    
    def is_holding_any(self) -> bool:
        """Check if holding any object."""
        return self.held_object_id is not None
    
    def debug_snapshot(self) -> Dict[str, Any]:
        """
        Get debug snapshot of current state.
        
        Returns:
            Dict with state summary for printing/logging
        """
        if self.arm_state is None or self.object_state is None:
            return {"error": "State not initialized"}
        
        available = self.get_available_actions()
        proposed = self.propose_next_action()
        
        return {
            "ee_pos": np.round(self.arm_state.ee_pos, 3).tolist(),
            "obj_pos": np.round(self.object_state.pos, 3).tolist(),
            "obj_visible": self.object_state.visible,
            "target_id": self.target_object_id,
            "selection_locked": self.selection_locked,
            "available_actions": [str(a) for a in available],
            "proposed_action": str(proposed) if proposed else None,
            "num_available": len(available),
            "held_object_id": self.held_object_id,
            "gripper_state": str(self.gripper_snapshot.state) if self.gripper_snapshot else "unknown",
        }

