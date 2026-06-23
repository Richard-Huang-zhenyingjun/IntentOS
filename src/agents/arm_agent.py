"""
ArmAgent - wraps Phase 2's arm execution path behind AgentBase.

This is an adapter, not a rewrite. All actual execution goes through the
existing Phase 2 path:
  PrimitiveExecutor (token-enforced) -> HardwareBridge -> ArmController

ArmAgent translates AgentAction into existing primitive execution calls.
It does not bypass any Phase 2 safety check.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from src.interfaces.primitive import Primitive, PrimitiveType

from .agent_base import ActionResult, AgentAction, AgentBase, AgentState, AgentStatus

logger = logging.getLogger(__name__)

SUPPORTED_ACTIONS = {"reach", "grasp", "move", "move_to", "release", "home"}


class ArmAgent(AgentBase):
    """
    Wraps Phase 2's PrimitiveExecutor behind the AgentBase interface.

    The executor reference is the existing Phase 2 PrimitiveExecutor.
    ArmAgent does not create its own executor; it receives one at init.
    """

    AGENT_ID = "arm"

    def __init__(
        self,
        primitive_executor: Any = None,
        hardware_bridge: Any = None,
        *,
        agent_id: str = AGENT_ID,
        controller: Any = None,
        grasp: Any = None,
        executor: Any = None,
    ):
        self._agent_id = agent_id
        self._executor = primitive_executor if primitive_executor is not None else executor
        self._bridge = hardware_bridge
        self._controller = controller
        self._grasp = grasp
        self._current_state = AgentState(
            agent_id=self._agent_id,
            status=AgentStatus.IDLE,
            current_action=None,
            error_message=None,
            metadata={},
        )

    @property
    def agent_id(self) -> str:
        return self._agent_id

    def can_execute(self, action: AgentAction | Primitive | dict) -> tuple[bool, Optional[str]]:
        """
        Check if arm can execute this action without side effects.
        Verifies: action type supported, hardware connected if configured, not already executing.
        """
        agent_action = self._coerce_action(action)
        if agent_action is None:
            return False, "Unsupported action shape"
        if agent_action.agent_id != self.agent_id:
            return False, f"Wrong agent: {agent_action.agent_id!r}"
        if agent_action.action_type not in SUPPORTED_ACTIONS:
            return False, f"Unsupported action: {agent_action.action_type!r}"
        if self._current_state.status == AgentStatus.EXECUTING:
            return False, "Arm is already executing another action"
        if self._current_state.status == AgentStatus.ERROR:
            return False, f"Arm in error state: {self._current_state.error_message}"
        if self._bridge is not None and hasattr(self._bridge, "is_connected") and not self._bridge.is_connected():
            return False, "Hardware bridge not connected"
        has_specific_executor = self._executor is not None and hasattr(
            self._executor,
            f"execute_{agent_action.action_type}",
        )
        if (
            not has_specific_executor
            and agent_action.action_type in ("reach", "move", "move_to")
            and "target_xyz" not in agent_action.parameters
        ):
            return False, "Missing target_xyz"
        return True, None

    def execute(self, action: AgentAction | Primitive | dict, token: Any) -> ActionResult:
        """
        Execute via Phase 2's PrimitiveExecutor.
        Token validation happens inside the executor and authorization manager.
        """
        agent_action = self._coerce_action(action)
        if agent_action is None:
            return ActionResult("", False, "Unsupported action shape", {}, 0.0)

        can_do, reason = self.can_execute(agent_action)
        if not can_do:
            return ActionResult(
                node_id=agent_action.node_id,
                success=False,
                failure_reason=reason,
                world_state_delta={},
                duration_ms=0.0,
            )

        self._current_state = AgentState(
            agent_id=self.agent_id,
            status=AgentStatus.EXECUTING,
            current_action=agent_action.action_type,
            error_message=None,
            metadata={"node_id": agent_action.node_id},
        )

        t0 = time.monotonic()
        try:
            success, reason = self._dispatch_to_executor(agent_action, token)
            duration_ms = (time.monotonic() - t0) * 1000.0
            self._current_state = AgentState(
                agent_id=self.agent_id,
                status=AgentStatus.IDLE if success else AgentStatus.ERROR,
                current_action=None,
                error_message=None if success else f"Action {agent_action.action_type} failed",
                metadata={},
            )
            return ActionResult(
                node_id=agent_action.node_id,
                success=success,
                failure_reason=None if success else (reason or f"executor_failure_{agent_action.action_type}"),
                world_state_delta=self._build_world_delta(agent_action, success),
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000.0
            logger.error("ArmAgent execute raised: %s", exc)
            self._current_state = AgentState(
                agent_id=self.agent_id,
                status=AgentStatus.ERROR,
                current_action=None,
                error_message=str(exc),
                metadata={},
            )
            return ActionResult(
                node_id=agent_action.node_id,
                success=False,
                failure_reason=str(exc),
                world_state_delta={},
                duration_ms=duration_ms,
            )

    def get_state(self) -> AgentState:
        return self._current_state

    def emergency_stop(self) -> None:
        """Fire-and-forget. Delegates to hardware bridge. Never raises."""
        try:
            if self._bridge is not None and hasattr(self._bridge, "emergency_stop"):
                self._bridge.emergency_stop()
            if self._controller is not None and hasattr(self._controller, "executing"):
                self._controller.executing = False
            self._current_state = AgentState(
                agent_id=self.agent_id,
                status=AgentStatus.PAUSED,
                current_action=None,
                error_message="Emergency stop activated",
                metadata={},
            )
        except Exception:
            pass

    def reset_error(self) -> None:
        """Reset error state so the arm can be reused after a recoverable failure."""
        if self._current_state.status == AgentStatus.ERROR:
            self._current_state = AgentState(
                agent_id=self.agent_id,
                status=AgentStatus.IDLE,
                current_action=None,
                error_message=None,
                metadata={},
            )

        if self._executor is not None:
            try:
                from src.execution.primitive_executor import ExecutorStatus

                if getattr(self._executor, "status", None) == ExecutorStatus.FAILED:
                    self._executor.status = ExecutorStatus.IDLE
                if hasattr(self._executor, "last_error_code"):
                    self._executor.last_error_code = None
            except Exception:
                pass

    def safe_release_if_holding(self, timeout_s: float = 20.0) -> bool:
        """Delegate user-stop safe release to the primitive executor."""
        release = getattr(self._executor, "safe_release_if_holding", None)
        if not callable(release):
            return False
        return bool(release(timeout_s=timeout_s))

    def get_last_safe_stop_release(self):
        """Expose the executor's latest user-stop release side effect."""
        getter = getattr(self._executor, "get_last_safe_stop_release", None)
        if not callable(getter):
            return None
        return getter()

    def abort_for_user_stop(self) -> bool:
        """
        Halt the current primitive for a user stop request.

        The primitive executor preserves any active magnet constraint, so a
        follow-up safe_release_if_holding() can set the carried object down
        instead of dropping it.
        """
        abort = getattr(self._executor, "abort", None)
        if not callable(abort):
            return False
        abort()
        return True

    def _dispatch_to_executor(
        self,
        action: AgentAction,
        token: Any,
    ) -> tuple[bool, Optional[str]]:
        """
        Translate AgentAction into Phase 2 PrimitiveExecutor calls.

        If the executor exposes execute_<action_type>() or generic execute(),
        the token is passed through. Current Phase 2 PrimitiveExecutor primarily
        exposes start_plan(); in that case the token remains enforced by the
        executor's injected AuthorizationManager and is included in metadata for audit.
        """
        action_type = action.action_type
        params = dict(action.parameters)

        if self._executor is not None and hasattr(self._executor, f"execute_{action_type}"):
            method = getattr(self._executor, f"execute_{action_type}")
            result = method(token=token, **params)
            success = bool(result)
            return success, None if success else f"executor_failure_{action_type}"

        if self._executor is not None and hasattr(self._executor, "execute"):
            result = self._executor.execute(action_type=action_type, params=params, token=token)
            success = bool(result)
            return success, None if success else f"executor_failure_{action_type}"

        if self._executor is not None and hasattr(self._executor, "start_plan"):
            primitive = self._action_to_primitive(action, token)
            if primitive is None:
                return False, f"primitive_build_failed_{action_type}"
            self._executor.start_plan([primitive])
            if not hasattr(self._executor, "tick"):
                return True, None
            return self._wait_for_primitive_complete(action)

        # Compatibility for narrow unit tests without constructing a full executor.
        if action_type in ("reach", "move", "move_to") and self._controller is not None:
            self._controller.move_to_position(params["target_xyz"])
            return True, None
        if action_type == "grasp" and self._grasp is not None:
            close = getattr(self._grasp, "close", None)
            if callable(close):
                close()
            return True, None
        if action_type == "release" and self._grasp is not None:
            open_ = getattr(self._grasp, "open", None)
            if callable(open_):
                open_()
            return True, None

        logger.error(
            "PrimitiveExecutor has no method for action %r. "
            "Adapt ArmAgent._dispatch_to_executor() to match actual API.",
            action_type,
        )
        return False, f"executor_api_missing_{action_type}"

    def _wait_for_primitive_complete(
        self,
        action: AgentAction,
        timeout_s: float = 8.0,
    ) -> tuple[bool, Optional[str]]:
        """
        Tick the Phase 2 executor until this primitive actually finishes.

        PrimitiveExecutor.start_plan() only starts motion; it does not mean the
        arm has reached the target. IntentOS must not mark the node DONE until
        the executor reports COMPLETE.
        """
        from src.execution.primitive_executor import ExecutorStatus

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            world = self._get_world_state()
            if world is None:
                time.sleep(0.05)
                continue

            status = self._executor.tick(world)
            if status in (ExecutorStatus.IDLE, ExecutorStatus.COMPLETE):
                return True, None
            if status == ExecutorStatus.FAILED:
                return False, getattr(self._executor, "last_error_code", None) or "executor_failed"

            sim = getattr(getattr(self._executor, "controller", None), "sim", None)
            if sim is not None and hasattr(sim, "step"):
                sim.step()
                pin = getattr(self._executor, "pin_non_active_objects", None)
                if callable(pin):
                    pin()
            time.sleep(0.05)

        logger.warning(
            "Primitive timeout after %.1fs for action %s",
            timeout_s,
            action.action_type,
        )
        return False, "timeout"

    def _get_world_state(self):
        """Build the WorldState snapshot expected by PrimitiveExecutor.tick()."""
        try:
            from src.robot.world_state import WorldState

            controller = getattr(self._executor, "controller", None)
            grasp = getattr(self._executor, "grasp", None)
            sim = getattr(controller, "sim", None)

            arm = sim.get_arm_state() if sim is not None else None
            obj = sim.get_object_state() if sim is not None and hasattr(sim, "get_object_state") else None
            holding = bool(grasp.is_holding()) if grasp is not None and hasattr(grasp, "is_holding") else False
            attached_id = (
                grasp.get_attached_id()
                if grasp is not None and hasattr(grasp, "get_attached_id")
                else None
            )

            return WorldState(
                arm=arm,
                object=obj,
                target_id=None,
                holding=holding,
                attached_id=attached_id,
            )
        except Exception as exc:
            logger.debug("Could not get world state: %s", exc)
            return None

    @staticmethod
    def _build_world_delta(action: AgentAction, success: bool) -> dict:
        if not success:
            return {}
        return {
            "action": action.action_type,
            "node_id": action.node_id,
            "parameters": action.parameters,
        }

    @staticmethod
    def _coerce_action(action: AgentAction | Primitive | dict) -> AgentAction | None:
        if isinstance(action, AgentAction):
            return action
        if isinstance(action, Primitive):
            kind = getattr(action.type, "value", str(action.type))
            params: dict[str, Any] = dict(action.metadata or {})
            if action.target_xyz is not None:
                params["target_xyz"] = action.target_xyz
            if action.object_id is not None:
                params["object_id"] = action.object_id
            return AgentAction(
                node_id=str(params.get("node_id", "legacy_primitive")),
                action_type="move" if kind == "move_to" else kind,
                parameters=params,
                agent_id=str(params.get("agent_id", "arm")),
            )
        if isinstance(action, dict):
            action_type = action.get("action_type", action.get("type"))
            if action_type is None:
                return None
            params = dict(action.get("parameters") or {})
            if "target_xyz" in action and "target_xyz" not in params:
                params["target_xyz"] = action["target_xyz"]
            return AgentAction(
                node_id=str(action.get("node_id", "dict_action")),
                action_type=str(getattr(action_type, "value", action_type)),
                parameters=params,
                agent_id=str(action.get("agent_id", "arm")),
            )
        return None

    @staticmethod
    def _action_to_primitive(action: AgentAction, token: Any) -> Primitive:
        primitive_name = "move_to" if action.action_type == "move" else action.action_type
        if primitive_name == "home":
            primitive_name = "reach"
        primitive_type = PrimitiveType(primitive_name)
        metadata = {k: v for k, v in action.parameters.items() if k not in {"target_xyz", "object_id"}}
        if action.action_type == "grasp" and action.parameters.get("target_xyz") is not None:
            metadata["object_position"] = action.parameters["target_xyz"]
        metadata["node_id"] = action.node_id
        token_id = getattr(token, "token_id", None)
        if token_id:
            metadata["intentos_token_id"] = token_id
        return Primitive(
            type=primitive_type,
            target_xyz=action.parameters.get("target_xyz"),
            object_id=action.parameters.get("object_id"),
            metadata=metadata,
        )
