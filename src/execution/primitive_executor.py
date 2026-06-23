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
        self._last_move_target_xyz = None
        self._grasp_constraint_id = None
        self._force_grasp_failure = None
        self._last_safe_stop_release: Optional[dict[str, Any]] = None
        self._world_object_ids: set[int] = set()
        self._object_rest_poses: dict[int, tuple[list[float], list[float]]] = {}
        self._grasp_legacy_fast = False
        self._release_legacy_fast = False
        self._openvla_wait_for_update = False
        self.last_error_code: Optional[str] = None
        self._invariant_checker = InvariantChecker()

    def set_authorization_manager(self, authorization_manager: Any):
        """Inject authorization manager after construction."""
        self.authorization_manager = authorization_manager

    def set_world_objects(self, object_ids: List[int] | tuple[int, ...]) -> None:
        """Register movable world objects so non-targets can be pinned stable."""
        self._world_object_ids = {int(obj_id) for obj_id in object_ids or []}
        self._object_rest_poses.clear()
        self._capture_rest_poses(self._world_object_ids, stop=True)

    def force_grasp_failure(self, target: Any = True) -> None:
        """
        Test/debug hook: force magnet grasp failure.

        Args:
            target: True for all grasps, an object_id, an iterable of object_ids,
                or a callable taking (object_id, primitive, executor).
        """
        self._force_grasp_failure = target

    def clear_forced_grasp_failure(self) -> None:
        """Disable forced magnet grasp failures."""
        self._force_grasp_failure = None

    def _should_force_grasp_failure(self, object_id: Optional[int], primitive: Primitive) -> bool:
        target = self._force_grasp_failure
        if target is None or target is False:
            return False
        if target is True:
            return True
        if callable(target):
            return bool(target(object_id, primitive, self))
        if isinstance(target, int):
            return object_id == target
        try:
            return object_id in target
        except TypeError:
            return False

    def _capture_rest_poses(self, object_ids: set[int], stop: bool = False) -> None:
        if not object_ids:
            return
        try:
            import pybullet as p

            client = self._physics_client()
            for obj_id in object_ids:
                pos, orn = p.getBasePositionAndOrientation(
                    obj_id,
                    physicsClientId=client,
                )
                self._object_rest_poses[int(obj_id)] = (list(pos), list(orn))
                if stop:
                    p.resetBaseVelocity(
                        obj_id,
                        [0, 0, 0],
                        [0, 0, 0],
                        physicsClientId=client,
                    )
        except Exception:
            return

    def _physics_client(self):
        sim = getattr(self.controller, "sim", None)
        return getattr(sim, "client", 0)

    def _current_active_object_id(self) -> Optional[int]:
        if self.active_plan and self.plan_index < len(self.active_plan):
            primitive = self.active_plan[self.plan_index]
            if primitive.object_id is not None:
                return int(primitive.object_id)
            metadata = primitive.metadata or {}
            for key in ("object_id", "target_object_id", "target_object"):
                value = metadata.get(key)
                if isinstance(value, int):
                    return int(value)
        if self._grasp_constraint_id is not None and self._last_grasped_object_id is not None:
            return int(self._last_grasped_object_id)
        return None

    def pin_non_active_objects(self) -> None:
        """
        Freeze all non-active objects at their last resting pose.

        This prevents unconstrained table/bin objects from accumulating residual
        velocity or being launched by unrelated arm motion. The active target or
        carried object is never pinned, so pinning does not fight the magnet.
        """
        if not self._world_object_ids:
            return
        active_id = self._current_active_object_id()
        try:
            import pybullet as p

            client = self._physics_client()
            for obj_id in self._world_object_ids:
                if active_id is not None and obj_id == active_id:
                    continue
                rest = self._object_rest_poses.get(obj_id)
                if rest is None:
                    pos, orn = p.getBasePositionAndOrientation(
                        obj_id,
                        physicsClientId=client,
                    )
                    rest = (list(pos), list(orn))
                    self._object_rest_poses[obj_id] = rest
                pos, orn = rest
                p.resetBasePositionAndOrientation(
                    obj_id,
                    pos,
                    orn,
                    physicsClientId=client,
                )
                p.resetBaseVelocity(
                    obj_id,
                    [0, 0, 0],
                    [0, 0, 0],
                    physicsClientId=client,
                )
        except Exception:
            return

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
                self.last_error_code = "move_no_target"
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
            if getattr(self.controller, "last_motion_error", None) == "ik_out_of_limits":
                self.last_error_code = "ik_out_of_limits"
                self.status = ExecutorStatus.FAILED
                return False
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
            done = self.controller.update(world.arm)
            if not done:
                return False

            target = primitive.target_xyz
            if target is None:
                return True

            try:
                import pybullet as p

                ee_idx = 7  # gripper_base / magnet link; target_xyz is link7-space.
                robot_id = self.controller.sim.robot_id
                client = self.controller.sim.client
                ee_pos = p.getLinkState(
                    robot_id,
                    ee_idx,
                    physicsClientId=client,
                )[0]
            except Exception:
                # If pose verification is unavailable, preserve legacy success.
                return True

            dist = (
                (ee_pos[0] - target[0]) ** 2
                + (ee_pos[1] - target[1]) ** 2
                + (ee_pos[2] - target[2]) ** 2
            ) ** 0.5
            table_top_z = 0.6
            if ee_pos[2] < table_top_z:
                print(f"[MOVE] Invalid pose: EE below table (z={ee_pos[2]:.3f})")
                self.last_error_code = "move_invalid_pose"
                self.status = ExecutorStatus.FAILED
                return False

            arrival_tol = 0.10
            if dist > arrival_tol:
                print(f"[MOVE] Not arrived: dist={dist:.3f} to target {target}")
                self.last_error_code = "move_not_arrived"
                self.status = ExecutorStatus.FAILED
                return False

            if kind == "move_to":
                self._last_move_target_xyz = list(target)
            return True
        
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

    def is_holding_object(self) -> bool:
        """True when the magnet constraint currently holds an object."""
        return self._grasp_constraint_id is not None and self._last_grasped_object_id is not None

    def safe_release_if_holding(self, timeout_s: float = 20.0) -> bool:
        """
        If an object is attached, set it down safely on the table.

        This is used for user-requested mid-task stop. It intentionally reuses
        safe_pause metadata so the executor's auth gate allows this cleanup
        sequence without authorizing new task work.
        """
        if not self.is_holding_object():
            return False

        from src.interfaces.primitive import Primitive, PrimitiveType

        object_id = self._last_grasped_object_id
        self._last_safe_stop_release = None
        setdown_xy = self._find_safe_table_setdown_xy(object_id)
        if setdown_xy is None:
            print("[SAFE_STOP] No clear table set-down spot; falling back to bin release")
            return self._safe_release_to_bin(timeout_s=timeout_s)

        x, y = setdown_xy
        table_hover = np.array([x, y, 0.66], dtype=float)
        table_drop = np.array([x, y, 0.63], dtype=float)
        plan = [
            Primitive(
                type=PrimitiveType.MOVE_TO,
                target_xyz=table_hover,
                object_id=object_id,
                metadata={"description": "safe_pause: user stop table hover"},
            ),
            Primitive(
                type=PrimitiveType.MOVE_TO,
                target_xyz=table_drop,
                object_id=object_id,
                metadata={"description": "safe_pause: user stop table drop"},
            ),
            Primitive(
                type=PrimitiveType.RELEASE,
                target_xyz=table_drop,
                object_id=object_id,
                metadata={"description": "safe_pause: user stop release"},
            ),
        ]
        success = self._run_safe_release_plan(plan, timeout_s)
        if success:
            self._last_safe_stop_release = {
                "object_id": object_id,
                "status": "SET_DOWN",
                "reason": "user_stopped",
                "destination": "table",
            }
        return success

    def _safe_release_to_bin(self, timeout_s: float = 20.0) -> bool:
        import numpy as np

        from src.interfaces.primitive import Primitive, PrimitiveType

        object_id = self._last_grasped_object_id
        bin_hover = np.array([0.4, 0.0, 0.87], dtype=float)
        bin_drop = np.array([0.4, 0.0, 0.78], dtype=float)
        plan = [
            Primitive(
                type=PrimitiveType.MOVE_TO,
                target_xyz=bin_hover,
                object_id=object_id,
                metadata={"description": "safe_pause: user stop fallback bin hover"},
            ),
            Primitive(
                type=PrimitiveType.MOVE_TO,
                target_xyz=bin_drop,
                object_id=object_id,
                metadata={"description": "safe_pause: user stop fallback bin drop"},
            ),
            Primitive(
                type=PrimitiveType.RELEASE,
                target_xyz=bin_drop,
                object_id=object_id,
                metadata={"description": "safe_pause: user stop fallback release"},
            ),
        ]
        success = self._run_safe_release_plan(plan, timeout_s)
        if success:
            self._last_safe_stop_release = {
                "object_id": object_id,
                "status": "DONE",
                "reason": "user_stopped_safe_fallback",
                "destination": "bin",
            }
        return success

    def get_last_safe_stop_release(self) -> Optional[dict[str, Any]]:
        """Return the most recent user-stop release side effect, if any."""
        return dict(self._last_safe_stop_release) if self._last_safe_stop_release else None

    def _run_safe_release_plan(self, plan: List[Primitive], timeout_s: float) -> bool:
        import time

        self.start_plan(plan)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            world = self._build_world_state_for_safe_release()
            status = self.tick(world)
            if status in (ExecutorStatus.IDLE, ExecutorStatus.COMPLETE):
                return True
            if status == ExecutorStatus.FAILED:
                return False
            sim = getattr(self.controller, "sim", None)
            if sim is not None and hasattr(sim, "step"):
                sim.step()
                self.pin_non_active_objects()
            time.sleep(0.02)
        self.last_error_code = "safe_release_timeout"
        return False

    def _find_safe_table_setdown_xy(self, active_object_id: Optional[int]) -> Optional[tuple[float, float]]:
        """Find a deterministic clear table spot for user-stop set-down."""
        x_min, x_max, y_min, y_max = (-0.35, 0.35, -0.25, 0.25)
        margin = 0.04
        min_clearance = 0.10
        candidates: list[tuple[float, float]] = []

        try:
            import pybullet as p

            client = self._physics_client()
            if active_object_id is not None:
                pos, _orn = p.getBasePositionAndOrientation(
                    active_object_id,
                    physicsClientId=client,
                )
                candidates.append((float(pos[0]), float(pos[1])))
        except Exception:
            client = self._physics_client()

        candidates.extend(
            [
                (0.20, -0.15),
                (0.00, -0.18),
                (-0.20, -0.15),
                (0.25, 0.15),
                (-0.25, 0.15),
                (0.00, 0.00),
            ]
        )

        occupied: list[tuple[float, float]] = []
        try:
            import pybullet as p

            for obj_id in self._world_object_ids:
                if active_object_id is not None and int(obj_id) == int(active_object_id):
                    continue
                pos, _orn = p.getBasePositionAndOrientation(
                    obj_id,
                    physicsClientId=client,
                )
                x, y, z = float(pos[0]), float(pos[1]), float(pos[2])
                if x_min - margin <= x <= x_max + margin and y_min - margin <= y <= y_max + margin and 0.50 <= z <= 0.80:
                    occupied.append((x, y))
        except Exception:
            return None

        seen = set()
        for x, y in candidates:
            key = (round(x, 3), round(y, 3))
            if key in seen:
                continue
            seen.add(key)
            if not (x_min + margin <= x <= x_max - margin and y_min + margin <= y <= y_max - margin):
                continue
            if all(((x - ox) ** 2 + (y - oy) ** 2) ** 0.5 >= min_clearance for ox, oy in occupied):
                return (x, y)
        return None

    def _build_world_state_for_safe_release(self) -> WorldState:
        sim = getattr(self.controller, "sim", None)
        arm = sim.get_arm_state() if sim is not None and hasattr(sim, "get_arm_state") else None
        obj = sim.get_object_state() if sim is not None and hasattr(sim, "get_object_state") else None
        return WorldState(
            arm=arm,
            object=obj,
            target_id=self._last_grasped_object_id,
            holding=self.is_holding_object(),
            attached_id=self._last_grasped_object_id,
        )

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
            self.last_error_code = "grasp_no_object_position"
            self.status = ExecutorStatus.FAILED
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
                if getattr(self.controller, "last_motion_error", None) == "ik_out_of_limits":
                    self.last_error_code = "ik_out_of_limits"
                    self.status = ExecutorStatus.FAILED
                    return False
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
                if getattr(self.controller, "last_motion_error", None) == "ik_out_of_limits":
                    self.last_error_code = "ik_out_of_limits"
                    self.status = ExecutorStatus.FAILED
                    return False
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
            import pybullet as p
            object_id = primitive.object_id if primitive.object_id is not None else self._last_grasped_object_id
            if object_id is None:
                print("[GRASP] No object_id to attach")
                self.last_error_code = "grasp_no_object_id"
                self.status = ExecutorStatus.FAILED
                return False
            if self._should_force_grasp_failure(object_id, primitive):
                print(f"[GRASP] Forced magnet failure for object {object_id}")
                self.last_error_code = "grasp_failed"
                self.status = ExecutorStatus.FAILED
                return False

            GRIPPER_LINK = 7  # gripper_base
            robot_id = self.controller.sim.robot_id
            client = self.controller.sim.client

            self.grasp.close(force=30.0)  # visual finger animation only

            obj_pos, obj_orn = p.getBasePositionAndOrientation(object_id, physicsClientId=client)
            link_state = p.getLinkState(robot_id, GRIPPER_LINK, physicsClientId=client)
            link_pos, link_orn = link_state[0], link_state[1]
            inv_link_pos, inv_link_orn = p.invertTransform(link_pos, link_orn)
            rel_pos, rel_orn = p.multiplyTransforms(inv_link_pos, inv_link_orn, obj_pos, obj_orn)

            try:
                self._grasp_constraint_id = p.createConstraint(
                    parentBodyUniqueId=robot_id,
                    parentLinkIndex=GRIPPER_LINK,
                    childBodyUniqueId=object_id,
                    childLinkIndex=-1,
                    jointType=p.JOINT_FIXED,
                    jointAxis=[0, 0, 0],
                    parentFramePosition=rel_pos,
                    childFramePosition=[0, 0, 0],
                    parentFrameOrientation=rel_orn,
                    physicsClientId=client,
                )
            except Exception:
                self.last_error_code = "grasp_failed"
                self.status = ExecutorStatus.FAILED
                return False
            if self._grasp_constraint_id is None or self._grasp_constraint_id < 0:
                self.last_error_code = "grasp_failed"
                self.status = ExecutorStatus.FAILED
                return False
            print(f"[GRASP] ✓ Magnet attached (constraint {self._grasp_constraint_id})")
            self._last_grasped_object_id = object_id
            self._grasp_stage = GraspStage.DONE
            return False

        if self._grasp_stage == GraspStage.DONE:
            self._reset_grasp_state()
            return True

        return False

    def _execute_release(self) -> bool:
        import pybullet as p
        if not self._release_started:
            print("[RELEASE] Detaching magnet")
            if self._grasp_constraint_id is not None:
                p.removeConstraint(
                    self._grasp_constraint_id,
                    physicsClientId=self.controller.sim.client,
                )
                self._grasp_constraint_id = None
            self.grasp.open()  # visual
            self._release_started = True
            self._release_start_frame = self.frame_count
            return False
        if self.frame_count - self._release_start_frame > 30:
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
            if self._last_move_target_xyz is not None:
                safe_x, safe_y, safe_z = self._last_move_target_xyz
            else:
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
            if obj_id in self._world_object_ids:
                self._object_rest_poses[obj_id] = (
                    [safe_x, safe_y, safe_z],
                    list(orn),
                )
            self._last_grasped_object_id = None
            self._last_move_target_xyz = None
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
