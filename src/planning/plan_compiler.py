"""
Plan compiler - implements PlanCompilerBase interface.
Week 3: Updated to use frozen interfaces.
"""
from typing import List, Optional
import numpy as np
from src.interfaces.plan_compiler_base import PlanCompilerBase
from src.interfaces.intent_proposal import IntentProposal, ActionType
from src.interfaces.scene_summary import SceneSummary, ObjectInfo
from src.interfaces.primitive import Primitive, PrimitiveType
from src.interfaces.errors import ErrorCode


class PlanCompiler(PlanCompilerBase):
    """
    Deterministic plan compiler.
    Validates all targets before generating primitives.
    
    This is the SAFETY GATEKEEPER - rejects invalid plans before execution.
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.clean_cfg = config['planning']['clean_table']
        self.last_validation_error: ErrorCode = ErrorCode.NONE
    
    def compile(
        self,
        proposal: IntentProposal,
        scene: SceneSummary
    ) -> List[Primitive]:
        """Compile proposal into validated primitives"""
        self.last_validation_error = ErrorCode.NONE

        # OpenVLA proposals carry fully formed trajectory metadata and should
        # compile to a single execution primitive.
        if self._is_openvla_proposal(proposal):
            return self._compile_openvla_plan(proposal)
        
        if proposal.action == ActionType.CLEAN_TABLE:
            # If Gemini suggested specific objects (Week 5+), use those
            if proposal.suggested_object_ids:
                target_obj = self._find_suggested_object(
                    proposal.suggested_object_ids, scene
                )
            else:
                target_obj = self._select_nearest_object(scene)
            
            if target_obj is None:
                return []
            
            return self._compile_pick_place(target_obj, scene)
        
        elif proposal.action == ActionType.IDLE:
            return []  # No action
        
        else:
            print(f"[COMPILER] Unknown action type: {proposal.action}")
            return []

    def compile_proposal(
        self,
        proposal: IntentProposal,
        scene: SceneSummary,
    ) -> List[Primitive]:
        """
        Compatibility helper for callers that use compile_proposal naming.

        Delegates to compile(), which already handles OpenVLA and heuristic
        proposal formats.
        """
        return self.compile(proposal, scene)
    
    def compile_for_object(
        self,
        object_id: int,
        scene: SceneSummary
    ) -> List[Primitive]:
        """Compile primitives for a specific object (used by TaskExecutor)"""
        self.last_validation_error = ErrorCode.NONE
        
        target_obj = next(
            (obj for obj in scene.objects_on_table if obj.object_id == object_id),
            None
        )
        
        if target_obj is None:
            self.last_validation_error = ErrorCode.OBJECT_MISSING
            return []
        
        return self._compile_pick_place(target_obj, scene)
    
    def _select_nearest_object(self, scene: SceneSummary) -> Optional[ObjectInfo]:
        """Select nearest object to robot base (deterministic)"""
        if not scene.objects_on_table:
            print("[COMPILER] No objects on table to clean")
            return None
        
        robot_base_xy = np.array([0.0, 0.0])  # Assume robot at origin
        target_obj = min(
            scene.objects_on_table,
            key=lambda obj: np.linalg.norm(np.array(obj.pos_xyz[:2]) - robot_base_xy)
        )
        
        return target_obj
    
    def _find_suggested_object(
        self,
        suggested_ids: List[int],
        scene: SceneSummary
    ) -> Optional[ObjectInfo]:
        """Find object from Gemini's suggested list (Week 5+)"""
        for obj in scene.objects_on_table:
            if obj.object_id in suggested_ids:
                return obj
        return None
    
    def _compile_pick_place(
        self,
        target_obj: ObjectInfo,
        scene: SceneSummary
    ) -> List[Primitive]:
        """
        Generate primitive sequence for pick-and-place.
        
        Week 3: Uses frozen ObjectInfo from interfaces.
        """
        target_xyz = np.array(target_obj.pos_xyz)
        
        # Validate workspace bounds
        if not self._validate_position(target_xyz):
            print(f"[COMPILER] Object at {target_xyz} outside workspace")
            self.last_validation_error = ErrorCode.OUT_OF_BOUNDS
            return []
        
        # Build primitive sequence
        approach_height = self.clean_cfg['approach_height']
        grasp_offset = self.clean_cfg['grasp_height_offset']
        bin_center = np.array(scene.bin_zone_center)
        bin_hover = self.clean_cfg['bin_hover_height']
        bin_drop_offset = self.clean_cfg['bin_drop_height_offset']
        safe_home = np.array(self.clean_cfg['safe_home_xyz'])
        
        plan = [
            # 1. Approach above object
            Primitive(
                type=PrimitiveType.REACH,
                target_xyz=target_xyz + np.array([0, 0, approach_height]),
                metadata={'step': 'approach', 'object_id': target_obj.object_id}
            ),
            
            # 2. Descend to grasp height
            Primitive(
                type=PrimitiveType.REACH,
                target_xyz=target_xyz + np.array([0, 0, grasp_offset]),
                metadata={'step': 'pre_grasp'}
            ),
            
            # 3. Grasp object
            Primitive(
                type=PrimitiveType.GRASP,
                object_id=target_obj.object_id,
                metadata={
                    'step': 'grasp',
                    'object_id': target_obj.object_id,
                    'object_position': target_xyz.tolist(),
                }
            ),
            
            # 4. Lift object
            Primitive(
                type=PrimitiveType.MOVE_TO,
                target_xyz=target_xyz + np.array([0, 0, approach_height]),
                metadata={'step': 'lift'}
            ),
            
            # 5. Move to bin (hover)
            Primitive(
                type=PrimitiveType.MOVE_TO,
                target_xyz=bin_center + np.array([0, 0, bin_hover]),
                metadata={'step': 'move_to_bin'}
            ),
            
            # 6. Lower to drop height
            Primitive(
                type=PrimitiveType.MOVE_TO,
                target_xyz=bin_center + np.array([0, 0, bin_drop_offset]),
                metadata={'step': 'lower_to_drop'}
            ),
            
            # 7. Release object
            Primitive(
                type=PrimitiveType.RELEASE,
                object_id=target_obj.object_id,
                metadata={'step': 'release'}
            ),
            
            # 8. Return to safe home
            Primitive(
                type=PrimitiveType.MOVE_TO,
                target_xyz=safe_home,
                metadata={'step': 'return_home'}
            )
        ]
        
        print(f"[COMPILER] Generated {len(plan)} primitives for object {target_obj.object_id}")
        return plan
    
    def _validate_position(self, xyz: np.ndarray) -> bool:
        """Check if position is within workspace bounds"""
        bounds = self.clean_cfg['workspace_bounds']
        x_min, x_max, y_min, y_max, z_min, z_max = bounds
        
        x, y, z = xyz
        return (
            x_min <= x <= x_max and
            y_min <= y <= y_max and
            z_min <= z <= z_max
        )

    @staticmethod
    def _is_openvla_proposal(proposal: IntentProposal) -> bool:
        """Return True when proposal metadata indicates OpenVLA trajectory."""
        meta = proposal.metadata or {}
        proposer = str(meta.get("proposer", proposal.source or "")).lower()
        primitive_type = str(meta.get("primitive_type", "")).lower()
        return (
            proposer == "openvla"
            or proposal.source == "openvla"
            or primitive_type == PrimitiveType.OPENVLA_TRAJECTORY.value
        )

    def _compile_openvla_plan(self, proposal: IntentProposal) -> List[Primitive]:
        """
        Build single primitive plan for OpenVLA trajectory execution.

        Required metadata fields mirror the OpenVLA proposer output.
        """
        meta = dict(proposal.metadata or {})
        required = ("delta_position", "delta_rotation", "gripper")
        if any(key not in meta for key in required):
            print("[COMPILER] Invalid OpenVLA metadata: missing trajectory fields")
            self.last_validation_error = ErrorCode.UNKNOWN
            return []

        # Preserve the same workspace safety checks used by heuristic plans
        # when the proposer provides a concrete target position.
        target_pos = meta.get("target_pos_xyz")
        if target_pos is not None:
            target_xyz = np.array(target_pos, dtype=float)
            if not self._validate_position(target_xyz):
                print(f"[COMPILER] OpenVLA target at {target_xyz} outside workspace")
                self.last_validation_error = ErrorCode.OUT_OF_BOUNDS
                return []

        meta.setdefault("proposer", "openvla")
        meta.setdefault("primitive_type", PrimitiveType.OPENVLA_TRAJECTORY.value)
        meta.setdefault("instruction", proposal.description)

        return [
            Primitive(
                type=PrimitiveType.OPENVLA_TRAJECTORY,
                metadata=meta,
            )
        ]
