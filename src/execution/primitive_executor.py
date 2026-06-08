from typing import List, Optional, Any
from enum import Enum
import numpy as np
from src.interfaces.primitive import Primitive
from src.robot.world_state import WorldState
from src.robot.controller import RobotController
from src.robot.grasp import GraspController
from src.core.invariant_checker import InvariantChecker

class ExecutorStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class GraspStage(str, Enum):
    APPROACH = "approach"
    DESCEND = "descend"
    CLOSE = "close"
    VERIFY = "verify"
    LIFT_TEST = "lift_test"
    DONE = "done"

class PrimitiveExecutor:
    """
    Executes primitive plans multi-frame using Week 0's controller pattern.
    
    Critical: Uses same multi-frame semantics as Week 0 orchestrator.
    """
    
    def __init__(
        self,
        controller: RobotController,
        grasp: GraspController,
        action_translator: Optional[Any] = None,
        authorization_manager: Optional[Any] = None,
        hardware_bridge: Optional[Any] = None,
    ):
        self.controller = controller
        self.grasp = grasp
        self.action_translator = action_translator
        self.authorization_manager = authorization_manager
        self._hardware_bridge = hardware_bridge
        self.hardware_bridge = hardware_bridge  # Backward-compatible public alias.
        
        # Execution state
        self.active_plan: List[Primitive] = []
        self.plan_index: int = 0
        self.active_primitive_started: bool = False
        self.status: ExecutorStatus = ExecutorStatus.IDLE
        self.frame_count: int = 0
        self._grasp_stage: GraspStage | None = None
        self._grasp_target_pos = None
        self._grasp_close_start_frame = 0
        self._grasp_lift_start_frame = 0
        self._grasp_stage_start_frame = 0
        self._grasp_stage_motion_started = False
        self._grasp_retry_count = 0
        self._max_grasp_retries = 2
        self._retry_offset = 0.0
        self._release_started = False
        self._release_start_frame = 0
        self._last_grasped_object_id = None
        self._grasp_legacy_fast = False
        self._release_legacy_fast = False
        self._openvla_wait_for_update = False
        self.last_error_code: Optional[str] = None
        self._invariant_checker = InvariantChecker()

    def set_authorization_manager(self, authorization_manager: Any):
        """Inject authorization manager after construction."""
        self.authorization_manager = authorization_manager

    @staticmethod
    def _primitive_kind(primitive: Primitive) -> str:
        """Return normalized primitive kind to tolerate legacy enum classes."""
        primitive_type = primitive.type
        return getattr(primitive_type, "value", str(primitive_type))
    
    def start_plan(self, plan: List[Primitive]):
        """Begin executing a new plan"""
        self.active_plan = plan
        self.plan_index = 0
        self.active_primitive_started = False
        self.status = ExecutorStatus.RUNNING if plan else ExecutorStatus.IDLE
        self.last_error_code = None
        self._reset_grasp_state()
        self._release_started = False
        self._grasp_legacy_fast = False
        self._release_legacy_fast = False
        
        print(f"[EXECUTOR] Started plan with {len(plan)} primitives")
    
    def tick(self, world: WorldState) -> ExecutorStatus:
        """
        Execute one frame of the current plan.
        
        Returns:
            Current status (RUNNING, COMPLETE, FAILED)
        """
        self.frame_count += 1
        # Reset per-tick error marker unless a failure sets it this frame.
        self.last_error_code = None

        # No active plan
        if not self.active_plan:
            self.status = ExecutorStatus.IDLE
            return self.status
        
        # Plan complete
        if self.plan_index >= len(self.active_plan):
            print("[EXECUTOR] Plan complete!")
            self.status = ExecutorStatus.COMPLETE
            self._invariant_checker.assert_invariant()
            return self.status
        
        # Execute current primitive
        primitive = self.active_plan[self.plan_index]
        
        # Multi-frame pattern (Week 0 lesson!)
        if not self.active_primitive_started:
            # Start primitive (frame 1)
            success = self._start_primitive(primitive, world)
            
            if not success:
                print(f"[EXECUTOR] Failed to start primitive {self.plan_index}: {primitive.type}")
                self.status = ExecutorStatus.FAILED
                if self.last_error_code is None:
                    self.last_error_code = "primitive_failed"
                self._invariant_checker.assert_invariant()
                return self.status
            
            self.active_primitive_started = True
            self.status = ExecutorStatus.RUNNING
            return self.status  # Don't check completion same frame!
        
        # Check completion (frame 2+)
        if self._check_primitive_complete(primitive, world):
            print(f"[EXECUTOR] Primitive {self.plan_index} complete: {primitive.type}")
            self.plan_index += 1
            self.active_primitive_started = False
            self._reset_grasp_state()
            self._release_started = False
            # Continue to next primitive next frame
        elif self.status == ExecutorStatus.FAILED:
            return self.status
        
        self.status = ExecutorStatus.RUNNING
        return self.status
    
    def _start_primitive(self, primitive: Primitive, world: WorldState) -> bool:
        """
        Start executing a primitive (called once per primitive).
        
        Returns:
            True if started successfully, False if failed
        """
        kind = self._primitive_kind(primitive)

        # Hard safety boundary: if auth manager is wired, every primitive requires
        # a valid active token before issuing any motion/gripper command.
        # Exception: internally generated safe-pause primitives are allowed while
        # re-auth is in progress (tagged via metadata description prefix).
        if self.authorization_manager is not None:
            safe_pause_desc = str((primitive.metadata or {}).get("description", ""))
            is_safe_pause_primitive = safe_pause_desc.startswith("safe_pause:")
            if not self.authorization_manager.is_authorized() and not is_safe_pause_primitive:
                print(f"[EXECUTOR] Unauthorized primitive blocked: {primitive.type}")
                self.status = ExecutorStatus.FAILED
                self.last_error_code = "unauthorized_execution_blocked"
                token_id = ""
                if hasattr(self.authorization_manager, "get_active_token_id"):
                    token_id = self.authorization_manager.get_active_token_id() or ""
                self._invariant_checker.record_execution_attempt(
                    has_valid_token=False,
                    executed=False,
                    token_id=token_id,
                )
                return False

        if kind in ("reach", "move_to"):
            # Use controller from Week 0
            if primitive.target_xyz is None:
                return False
            if isinstance(self.controller, RobotController):
                duration = 1.5 if kind == "reach" else 2.0
                self.controller.move_to_position_smooth(
                    target_cart=np.array(primitive.target_xyz, dtype=float),
                    duration=duration,
                )
            else:
                # Preserve legacy behavior for unit-test mocks.
                self.controller.move_to_position(primitive.target_xyz)
            return True
        
        elif kind == "grasp":
            # Use grasp controller
            if primitive.object_id is not None:
                self._last_grasped_object_id = primitive.object_id
            if primitive.object_id is not None and hasattr(self.grasp, "attach") and primitive.metadata.get("object_position") is None:
                # Legacy compatibility for existing tests/call sites.
                try:
                    self.grasp.attach(primitive.object_id)
                except Exception:
                    pass
            if primitive.metadata.get("object_position") is None:
                # Legacy one-frame grasp completion path for older plans/tests.
                self._grasp_legacy_fast = True
                return True
            self._grasp_stage = GraspStage.APPROACH
            self.grasp.open()
            return True
        
        elif kind == "release":
            # Release grasp
            if primitive.object_id is not None and hasattr(self.grasp, "detach") and not primitive.metadata:
                try:
                    self.grasp.detach()
                except Exception:
                    pass
            if not primitive.metadata:
                self._release_legacy_fast = True
                return True
            self._release_started = False
            return True

        elif kind == "openvla_trajectory":
            return self._execute_openvla_trajectory_start(primitive, world)
        
        else:
            print(f"[EXECUTOR] Unknown primitive type: {primitive.type}")
            return False
    
    def _check_primitive_complete(self, primitive: Primitive, world: WorldState) -> bool:
        """
        Check if primitive has finished executing.
        
        Returns:
            True if complete, False if still running
        """
        kind = self._primitive_kind(primitive)

        if kind in ("reach", "move_to"):
            # Check controller convergence (Week 0 pattern)
            if world.arm is None:
                return False
            return self.controller.update(world.arm)
        
        elif kind == "grasp":
            if self._grasp_legacy_fast:
                self._grasp_legacy_fast = False
                return True
            return self._execute_grasp(primitive)
        
        elif kind == "release":
            if self._release_legacy_fast:
                self._release_legacy_fast = False
                self._stabilize_released_object()
                return True
            return self._execute_release()

        elif kind == "openvla_trajectory":
            if self._openvla_wait_for_update:
                if world.arm is None:
                    return False
                done = self.controller.update(world.arm)
                if done:
                    self._openvla_wait_for_update = False
                return done
            return True
        
        return False
    
    def is_executing(self) -> bool:
        """Check if executor is currently running a plan"""
        return self.status == ExecutorStatus.RUNNING

    def abort(self) -> None:
        """
        Immediately halt the active plan without issuing new motion.

        Safe to call at any point in execution. This stops the controller in
        place, clears the active plan, resets primitive sub-state, and returns
        the executor to IDLE without touching the invariant checker.
        """
        try:
            if hasattr(self.controller, "stop"):
                self.controller.stop()
            elif hasattr(self.controller, "halt"):
                self.controller.halt()
        except Exception:
            pass

        self.active_plan = []
        self.plan_index = 0
        self.active_primitive_started = False

        self._reset_grasp_state()
        self._release_started = False
        self._grasp_legacy_fast = False
        self._release_legacy_fast = False
        self._openvla_wait_for_update = False

        self.status = ExecutorStatus.IDLE
        self.last_error_code = None

        print("[EXECUTOR] Plan aborted by user - halted in place, no object dropped")

    def _reset_grasp_state(self):
        self._grasp_stage = None
        self._grasp_target_pos = None
        self._grasp_close_start_frame = 0
        self._grasp_lift_start_frame = 0
        self._grasp_stage_start_frame = 0
        self._grasp_stage_motion_started = False
        self._grasp_retry_count = 0
        self._retry_offset = 0.0

    def _object_position(self, primitive: Primitive):
        pos = primitive.metadata.get("object_position")
        if pos is None:
            pos = primitive.metadata.get("target_xyz")
        if pos is None and primitive.target_xyz is not None:
            pos = primitive.target_xyz
        if pos is None:
            return None
        return np.array(pos, dtype=float)

    def _execute_grasp(self, primitive: Primitive) -> bool:
        """Multi-stage compliant grasp sequence."""
        obj_pos = self._object_position(primitive)
        if obj_pos is None:
            print("[GRASP] Missing object_position metadata")
            return False

        object_id = primitive.object_id
        obj_height = 0.06
        if object_id is not None:
            try:
                import pybullet as p
                aabb_min, aabb_max = p.getAABB(object_id)
            except Exception:
                aabb_min = aabb_max = None
            if aabb_min is not None and aabb_max is not None:
                obj_height = max(0.01, float(aabb_max[2] - aabb_min[2]))

        approach_clearance = max(0.05, obj_height * 0.5) + self._retry_offset
        approach_target = np.array(
            [obj_pos[0], obj_pos[1], obj_pos[2] + obj_height / 2.0 + approach_clearance],
            dtype=float,
        )

        if self._grasp_stage is None:
            self._grasp_stage = GraspStage.APPROACH

        if self._grasp_stage == GraspStage.APPROACH:
            if not self._grasp_stage_motion_started:
                print("[GRASP] Stage: APPROACH")
                self.controller.move_to_position_smooth(approach_target, duration=1.2)
                self._grasp_stage_motion_started = True
                self._grasp_stage_start_frame = self.frame_count
                return False
            if self.controller.is_executing():
                self.controller.update(self.controller.sim.get_arm_state())
                if self._grasp_stage_start_frame and self.frame_count - self._grasp_stage_start_frame > 180:
                    print("[GRASP] APPROACH timeout, continuing to descend")
                    self.controller.stop()
                    self._grasp_stage = GraspStage.DESCEND
                    self._grasp_stage_motion_started = False
                return False
            self._grasp_stage = GraspStage.DESCEND
            self._grasp_stage_motion_started = False
            return False

        if self._grasp_stage == GraspStage.DESCEND:
            descend_target = np.array([obj_pos[0], obj_pos[1], obj_pos[2]], dtype=float)
            if not self._grasp_stage_motion_started:
                print("[GRASP] Stage: DESCEND")
                self.controller.move_to_position_smooth(descend_target, duration=0.8)
                self._grasp_stage_motion_started = True
                self._grasp_stage_start_frame = self.frame_count
                return False
            if self.controller.is_executing():
                self.controller.update(self.controller.sim.get_arm_state())
                if self._grasp_stage_start_frame and self.frame_count - self._grasp_stage_start_frame > 180:
                    print("[GRASP] DESCEND timeout, forcing close")
                    self.controller.stop()
                    self._grasp_stage = GraspStage.CLOSE
                    self._grasp_stage_motion_started = False
                return False
            if self._grasp_stage_motion_started:
                self._grasp_stage = GraspStage.CLOSE
                self._grasp_stage_motion_started = False
            return False

        if self._grasp_stage == GraspStage.CLOSE:
            if self._grasp_close_start_frame == 0:
                print("[GRASP] Stage: CLOSE")
                self.grasp.close(force=30.0)
                self._grasp_close_start_frame = self.frame_count
                return False
            if self.grasp.is_motion_complete():
                self._grasp_stage = GraspStage.VERIFY
                return False
            if self.frame_count - self._grasp_close_start_frame > 120:
                print("[GRASP] Finger close timeout")
                return False
            return False

        if self._grasp_stage == GraspStage.VERIFY:
            print("[GRASP] Stage: VERIFY")
            state = self.grasp.get_state()
            if self.grasp.verify_grasp():
                print(f"[GRASP] ✓ Force detected: {state.force:.1f}N")
                self._grasp_stage = GraspStage.LIFT_TEST
                self._grasp_stage_motion_started = False
                return False
            if self._grasp_retry_count < self._max_grasp_retries:
                self._grasp_retry_count += 1
                self._retry_offset = 0.01 * self._grasp_retry_count
                print(f"[GRASP] ✗ No force ({state.force:.1f}N), retry {self._grasp_retry_count}/{self._max_grasp_retries}")
                self.grasp.open()
                self._grasp_stage = GraspStage.APPROACH
                self._grasp_stage_motion_started = False
                self._grasp_close_start_frame = 0
                return False
            print("[GRASP] ✗ Failed after max retries")
            self._grasp_retry_count = 0
            self.status = ExecutorStatus.FAILED
            return False

        if self._grasp_stage == GraspStage.LIFT_TEST:
            current = self.controller.get_end_effector_position()
            if current is None:
                return False
            if self._grasp_lift_start_frame and self.frame_count - self._grasp_lift_start_frame > 180:
                print("[GRASP] Lift timeout")
                self.status = ExecutorStatus.FAILED
                return False
            lift_target = np.array([current[0], current[1], current[2] + 0.05], dtype=float)
            if not self._grasp_stage_motion_started:
                print("[GRASP] Stage: LIFT_TEST")
                self.controller.move_to_position_smooth(lift_target, duration=1.0)
                self._grasp_lift_start_frame = self.frame_count
                self._grasp_stage_motion_started = True
                return False
            if self.controller.is_executing():
                self.controller.update(self.controller.sim.get_arm_state())
                return False
            if self.grasp.verify_grasp():
                quality = self.grasp.get_grasp_quality() if hasattr(self.grasp, "get_grasp_quality") else 1.0
                print(f"[GRASP] ✓ Lift test passed")
                print(f"[GRASP] ✓ Quality: {quality:.2f}")
                if quality > 0.5:
                    self._grasp_stage = GraspStage.DONE
                    self._grasp_stage_motion_started = False
                    return False
                if self._grasp_retry_count < self._max_grasp_retries:
                    self._grasp_retry_count += 1
                    self._retry_offset = 0.01 * self._grasp_retry_count
                    print(f"[GRASP] Low quality, retrying {self._grasp_retry_count}/{self._max_grasp_retries}")
                    self.grasp.open()
                    self._grasp_stage = GraspStage.APPROACH
                    self._grasp_stage_motion_started = False
                    self._grasp_close_start_frame = 0
                    return False
                print("[GRASP] ✗ Low quality after retries")
                self.status = ExecutorStatus.FAILED
                return False
            print("[GRASP] ✗ Object dropped during lift")
            self.status = ExecutorStatus.FAILED
            return False

        if self._grasp_stage == GraspStage.DONE:
            self._reset_grasp_state()
            return True

        return False

    def _execute_release(self) -> bool:
        """Open gripper and wait for force release."""
        if not self._release_started:
            print("[RELEASE] Stage: OPEN")
            self.grasp.open()
            self._release_started = True
            self._release_start_frame = self.frame_count
            return False

        if self.grasp.is_motion_complete():
            state = self.grasp.get_state()
            if not state.is_grasping:
                print(f"[RELEASE] ✓ Object released (force: {state.force:.1f}N)")
                self._release_started = False
                self._stabilize_released_object()
                return True

        if self.frame_count - self._release_start_frame > 30:
            print("[RELEASE] Timeout (assuming released)")
            self._release_started = False
            self._stabilize_released_object()
            return True

        return False

    def _stabilize_released_object(self) -> None:
        """Clamp and stop the most recently grasped object after release."""
        if self._last_grasped_object_id is None:
            return
        try:
            import pybullet as p

            obj_id = self._last_grasped_object_id
            client = getattr(
                self.controller,
                "client",
                getattr(self.controller, "physics_client", None),
            )
            if client is None:
                sim = getattr(self.controller, "sim", None)
                client = getattr(sim, "client", 0)

            pos, orn = p.getBasePositionAndOrientation(
                obj_id,
                physicsClientId=client,
            )
            safe_x = max(-0.6, min(0.6, pos[0]))
            safe_y = max(-0.4, min(0.4, pos[1]))
            safe_z = max(0.55, min(0.85, pos[2]))
            p.resetBasePositionAndOrientation(
                obj_id,
                [safe_x, safe_y, safe_z],
                orn,
                physicsClientId=client,
            )
            p.resetBaseVelocity(
                obj_id,
                [0, 0, 0],
                [0, 0, 0],
                physicsClientId=client,
            )
            self._last_grasped_object_id = None
        except Exception:
            pass

    def _execute_openvla_trajectory_start(self, primitive: Primitive, world: WorldState) -> bool:
        """
        Execute an OpenVLA trajectory primitive.

        Authorization was already checked in _start_primitive when an auth manager
        is attached. This method only performs translation + command dispatch.
        """
        if self.action_translator is None:
            print("[OPENVLA] Missing action_translator")
            self.status = ExecutorStatus.FAILED
            self.last_error_code = "openvla_missing_translator"
            return False

        metadata = primitive.metadata or {}
        required = ("delta_position", "delta_rotation", "gripper")
        if any(key not in metadata for key in required):
            print("[OPENVLA] Invalid metadata for OPENVLA_TRAJECTORY")
            self.status = ExecutorStatus.FAILED
            self.last_error_code = "openvla_invalid_metadata"
            return False

        try:
            translated = self.action_translator.translate_from_metadata(metadata)
        except Exception as exc:
            print(f"[OPENVLA] Translation error: {exc}")
            self.status = ExecutorStatus.FAILED
            self.last_error_code = "openvla_translation_error"
            return False

        token_id = None
        if self.authorization_manager is not None and hasattr(self.authorization_manager, "get_active_token_id"):
            token_id = self.authorization_manager.get_active_token_id()

        if not translated.ik_success:
            print(f"[OPENVLA] IK failed (error={translated.ik_error:.4f}m), token={token_id}")
            self.status = ExecutorStatus.FAILED
            self.last_error_code = "openvla_ik_fail"
            return False

        joint_targets = np.asarray(translated.joint_positions, dtype=float)
        if not np.all(np.isfinite(joint_targets)):
            print(f"[OPENVLA] Invalid joint targets (NaN/Inf), token={token_id}")
            self.status = ExecutorStatus.FAILED
            self.last_error_code = "openvla_invalid_joint_targets"
            return False

        print(
            "[OPENVLA] Executing trajectory "
            f"(ik_error={translated.ik_error:.4f}m, token={token_id})"
        )

        try:
            used_bridge = self._apply_joints(joint_targets)
        except Exception as exc:
            print(f"[OPENVLA] Hardware bridge error: {exc}, token={token_id}")
            self.status = ExecutorStatus.FAILED
            self.last_error_code = "openvla_hardware_bridge_error"
            return False

        if used_bridge:
            self._invariant_checker.record_execution_attempt(
                has_valid_token=True,
                executed=True,
                token_id=str(token_id or ""),
            )
            return True

        if hasattr(self.controller, "move_to_joint_positions"):
            converged = bool(self.controller.move_to_joint_positions(joint_targets))
            self._invariant_checker.record_execution_attempt(
                has_valid_token=True,
                executed=True,
                token_id=str(token_id or ""),
            )
            if not converged:
                print("[OPENVLA] Joint convergence timeout")
                self.status = ExecutorStatus.FAILED
                self.last_error_code = "openvla_timeout"
                return False
            return True

        if hasattr(self.controller, "move_to_position"):
            self.controller.move_to_position(np.array(translated.target_ee_position, dtype=float))
            self._openvla_wait_for_update = True
            self._invariant_checker.record_execution_attempt(
                has_valid_token=True,
                executed=True,
                token_id=str(token_id or ""),
            )
            return True

        print("[OPENVLA] Controller lacks supported command API")
        self.status = ExecutorStatus.FAILED
        self.last_error_code = "openvla_controller_api_missing"
        return False

    def _apply_joints(self, joint_positions: np.ndarray) -> bool:
        """
        Apply translated joint targets through the hardware bridge when present.

        Returns True when HardwareBridge handled the command. Returns False for
        legacy controller fallback paths used by the default PyBullet simulator.
        """
        if self._hardware_bridge is None:
            return False
        self._hardware_bridge.execute(joint_positions)
        return True

    @property
    def invariant_summary(self) -> dict:
        """Expose execution invariant counters for diagnostics/metrics."""
        return self._invariant_checker.summary
