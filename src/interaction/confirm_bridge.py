"""
ConfirmBridge — the hinge between typed "yes" and Phase 2 authorization.

This bridge synchronizes a human confirmation across:
  - Phase 2 AuthorizationManager, via the existing keyboard DecisionPipeline
  - IntentOS, via its kernel confirmation event

It does not call Phase 2 _handle_confirm() directly and does not issue
authorization tokens directly.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

AUTH_TOKEN_TIMEOUT_S = 3.0
TICK_SLEEP_S = 0.05
MAX_TICKS = int(AUTH_TOKEN_TIMEOUT_S / TICK_SLEEP_S)


@dataclass
class BridgeResult:
    success: bool
    reason: str
    phase2_token_id: Optional[str]
    intentos_token_id: Optional[str]
    ticks_taken: int
    false_executions_at_exit: int


class ConfirmBridge:
    """Synchronizes typed confirmation across Phase 2 and IntentOS."""

    def __init__(
        self,
        keyboard_source,
        phase2_orchestrator,
        auth_manager,
        intentos_orchestrator,
        invariant_checker,
    ):
        self._keyboard = keyboard_source
        self._phase2 = phase2_orchestrator
        self._auth = auth_manager
        self._intentos = intentos_orchestrator
        self._inv = invariant_checker
        self._last_tick_count = 0

    def confirm(self) -> BridgeResult:
        """Execute the full confirm bridge sequence."""
        ticks_taken = 0

        intentos_state = self._intentos.get_status().get("intentos_state", "")
        if intentos_state != "AWAITING_CONFIRM":
            return BridgeResult(
                success=False,
                reason=(
                    f"Cannot confirm — IntentOS is in state {intentos_state!r}, "
                    "not AWAITING_CONFIRM. Nothing was executed."
                ),
                phase2_token_id=None,
                intentos_token_id=None,
                ticks_taken=0,
                false_executions_at_exit=self._false_executions(),
            )

        phase2_state = self._get_phase2_state()
        safe_phase2_states = {
            "IDLE",
            "idle",
            "SELECTING",
            "selecting",
            "DONE",
            "done",
            "COMPLETE",
            "complete",
            "EXECUTING",
            "executing",
        }
        if phase2_state not in safe_phase2_states:
            logger.warning(
                "ConfirmBridge: Phase 2 is in state %r; not safe to inject confirm.",
                phase2_state,
            )
            return BridgeResult(
                success=False,
                reason=(
                    "The system is busy with something else right now. "
                    "Wait a moment and try again."
                ),
                phase2_token_id=None,
                intentos_token_id=None,
                ticks_taken=0,
                false_executions_at_exit=self._false_executions(),
            )

        if self._false_executions() > 0:
            return BridgeResult(
                success=False,
                reason="A safety issue was detected. Please restart the system.",
                phase2_token_id=None,
                intentos_token_id=None,
                ticks_taken=0,
                false_executions_at_exit=self._false_executions(),
            )

        logger.info("ConfirmBridge: all guards passed. Beginning confirmation sequence.")

        intentos_target, intentos_action = self._get_intentos_target_and_action()
        if not self._drive_phase2_to_confirming(intentos_target, intentos_action):
            return BridgeResult(
                success=False,
                reason=(
                    "The authorization system could not prepare the matching "
                    "Phase 2 proposal. Nothing was executed."
                ),
                phase2_token_id=None,
                intentos_token_id=None,
                ticks_taken=self._last_tick_count,
                false_executions_at_exit=self._false_executions(),
            )

        self._keyboard.set_key_state(confirm=True, cancel=False)
        try:
            token_id = self._tick_until_auth_token(MAX_TICKS, TICK_SLEEP_S)
            ticks_taken = self._last_tick_count
        finally:
            self._keyboard.set_key_state(confirm=False, cancel=False)

        if token_id is None:
            return BridgeResult(
                success=False,
                reason=(
                    "The authorization system didn't respond in time. "
                    "Try again, or say 'stop' to cancel."
                ),
                phase2_token_id=None,
                intentos_token_id=None,
                ticks_taken=ticks_taken,
                false_executions_at_exit=self._false_executions(),
            )

        from src.kernel.types import KernelEvent

        event = KernelEvent(
            kind="confirmed",
            proposal_id=self._intentos.get_status().get("proposal_id"),
            agent_id=None,
            timestamp_ms=time.time() * 1000.0,
            details={"phase2_token_id": token_id},
        )
        self._intentos._react_to_events([event])
        self._intentos.tick()

        intentos_state_after = self._intentos.get_status().get("intentos_state", "")
        if intentos_state_after not in ("EXECUTING", "COMPLETE"):
            return BridgeResult(
                success=False,
                reason="Something went wrong during confirmation. Try again.",
                phase2_token_id=token_id,
                intentos_token_id=None,
                ticks_taken=ticks_taken,
                false_executions_at_exit=self._false_executions(),
            )

        false_exec = self._false_executions()
        if false_exec > 0:
            return BridgeResult(
                success=False,
                reason="A safety issue occurred during confirmation. System halted.",
                phase2_token_id=token_id,
                intentos_token_id=None,
                ticks_taken=ticks_taken,
                false_executions_at_exit=false_exec,
            )

        return BridgeResult(
            success=True,
            reason="Confirmed.",
            phase2_token_id=token_id,
            intentos_token_id=self._intentos.get_status().get("current_token"),
            ticks_taken=ticks_taken,
            false_executions_at_exit=false_exec,
        )

    def cancel(self) -> BridgeResult:
        """Cancel the current IntentOS proposal."""
        self._keyboard.set_key_state(confirm=False, cancel=True)
        time.sleep(TICK_SLEEP_S * 2)
        self._phase2.step()
        self._keyboard.set_key_state(confirm=False, cancel=False)
        self._intentos.cancel()

        return BridgeResult(
            success=True,
            reason="Cancelled.",
            phase2_token_id=None,
            intentos_token_id=None,
            ticks_taken=1,
            false_executions_at_exit=self._false_executions(),
        )

    def _tick_until_auth_token(self, max_ticks: int, sleep_s: float) -> Optional[str]:
        """Tick Phase 2 until AuthorizationManager has an active token."""
        self._last_tick_count = 0
        for i in range(max_ticks):
            self._phase2.step()
            self._last_tick_count = i + 1

            token_id = self._get_active_token_id()
            if token_id is not None:
                return token_id

            time.sleep(sleep_s)

        return None

    def _drive_phase2_to_confirming(
        self,
        intentos_target: Optional[str],
        intentos_action: Optional[str],
    ) -> bool:
        """
        Drive Phase 2 to CONFIRMING by directly injecting a proposal.

        This bypasses the Phase 2 proposer/compiler selection path, which can
        return IDLE when the scene appears clear even though IntentOS has an
        already-confirmed task ready to authorize.
        """
        del intentos_action
        from src.core.schema import ArmActionType

        current_state = self._get_phase2_state()
        if current_state.upper() == "DONE":
            self._phase2.state_machine.reset()
            self._phase2.step()
            time.sleep(0.3)

        if self._get_phase2_state() in ("CONFIRMING", "confirming"):
            return True

        object_id = self._resolve_phase2_object_id(intentos_target)
        if object_id is None:
            logger.warning(
                "Could not resolve object_id for target %r",
                intentos_target,
            )
            artifacts = getattr(self._phase2, "world_artifacts", None)
            object_ids = list(getattr(artifacts, "object_ids", []) or [])
            if not object_ids:
                self._last_tick_count = 0
                return False
            object_id = int(object_ids[0])

        self._phase2.force_lock_target(object_id)
        self._phase2.step()

        try:
            from src.interfaces.intent_proposal import IntentProposal, ActionType

            self._phase2.current_proposal = IntentProposal(
                action=ActionType.CLEAN_TABLE,
                description="IntentOS authorized action",
                source="intentos_bridge",
                confidence=1.0,
                suggested_object_ids=[object_id],
                metadata={
                    "target_object_id": object_id,
                    "intentos_target": intentos_target,
                },
            )
            self._phase2.state_machine.propose_action(
                ArmActionType.CLEAN_TABLE,
                "IntentOS authorized action",
            )
        except Exception as exc:
            logger.warning("Direct proposal injection failed: %s", exc)
            self._last_tick_count = 0
            for i in range(20):
                self._phase2.step()
                self._last_tick_count = i + 1
                if self._get_phase2_state() in ("CONFIRMING", "confirming"):
                    return True
                time.sleep(TICK_SLEEP_S)
            return False

        self._last_tick_count = 0
        for i in range(10):
            self._phase2.step()
            self._last_tick_count = i + 1
            if self._get_phase2_state() in ("CONFIRMING", "confirming"):
                return True
            time.sleep(TICK_SLEEP_S)

        logger.error(
            "Could not reach CONFIRMING after direct injection. Final state: %r",
            self._get_phase2_state(),
        )
        return False

    def _get_intentos_target_and_action(self) -> tuple[Optional[str], Optional[str]]:
        """Read first actionable node from the current IntentOS TaskGraph."""
        context = getattr(self._intentos, "_context", None)
        graph = getattr(context, "graph", None)
        nodes = getattr(graph, "nodes", []) or []
        for node in nodes:
            action = getattr(node, "action_type", None)
            params = getattr(node, "parameters", {}) or {}
            target = params.get("target")
            if action in ("reach", "move", "grasp", "release", "home"):
                return target, action
        return None, None

    def _resolve_phase2_object_id(
        self, intentos_target: Optional[str]
    ) -> Optional[int]:
        """Map an IntentOS target label to a concrete Phase 2 body ID."""
        artifacts = getattr(self._phase2, "world_artifacts", None)
        object_ids = list(getattr(artifacts, "object_ids", []) or [])
        if not object_ids:
            return None

        # Generic targets: use first available object.
        if intentos_target in (
            None,
            "",
            "nearest_object",
            "object",
            "bin",
            "tray",
            "table",
        ):
            return int(object_ids[0])

        # "object_N" format: extract body ID directly.
        if intentos_target and intentos_target.startswith("object_"):
            try:
                body_id = int(intentos_target.split("_")[1])
                if body_id in object_ids:
                    return body_id
            except (IndexError, ValueError):
                pass

        return int(object_ids[0])

    def _get_active_token_id(self) -> Optional[str]:
        """Get the active Phase 2 authorization token ID."""
        return self._auth.get_active_token_id()

    def _get_phase2_state(self) -> str:
        """Get current Phase 2 orchestrator FSM state as a string."""
        state_machine = getattr(self._phase2, "state_machine", None)
        if state_machine is None:
            return "UNKNOWN"

        state = getattr(state_machine, "state", None)
        return str(getattr(state, "value", state or "UNKNOWN"))

    def _false_executions(self) -> int:
        """Get current false_executions count from InvariantChecker."""
        return int(getattr(self._inv, "false_executions", 0))


def run_spike_test(system, intentos):
    """One-shot test of the confirm bridge."""
    print("\n" + "=" * 60)
    print("  ConfirmBridge Spike Test")
    print("=" * 60)

    try:
        keyboard_source = system.decision_pipeline.router.get_source("keyboard")
        phase2_orch = system
        auth_manager = system.auth_manager
        inv_checker = system.executor._invariant_checker
    except AttributeError as e:
        print(f"\n[SPIKE] FAIL — Could not extract components: {e}")
        print("  Adapt the attribute paths in run_spike_test() to match")
        print("  your actual system_factory output structure.")
        return False

    if keyboard_source is None:
        print("[SPIKE] FAIL — keyboard source not found in decision pipeline")
        return False

    if auth_manager is None:
        print("[SPIKE] FAIL — auth_manager not found on system object")
        return False

    bridge = ConfirmBridge(
        keyboard_source=keyboard_source,
        phase2_orchestrator=phase2_orch,
        auth_manager=auth_manager,
        intentos_orchestrator=intentos,
        invariant_checker=inv_checker,
    )

    print("\n[SPIKE] Step 1: Submit goal to IntentOS...")
    accepted = intentos.submit_goal(
        "move the nearest object to the bin",
        "3 objects on table",
    )
    if not accepted:
        print("[SPIKE] FAIL — goal not accepted (IntentOS not in IDLE state?)")
        return False
    print("[SPIKE] Goal accepted")

    print("[SPIKE] Step 2: Waiting for AWAITING_CONFIRM...")
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        intentos.tick()
        state = intentos.get_status().get("intentos_state", "")
        if state == "AWAITING_CONFIRM":
            break
        time.sleep(0.05)
    else:
        print(
            f"[SPIKE] FAIL — IntentOS never reached AWAITING_CONFIRM "
            f"(current state: {intentos.get_status().get('intentos_state')})"
        )
        return False
    print("[SPIKE] IntentOS is AWAITING_CONFIRM ✓")

    print("[SPIKE] Step 3: Running confirm bridge (simulating typed 'yes')...")
    result = bridge.confirm()

    print(f"\n[SPIKE] Bridge result: success={result.success}")
    print(f"[SPIKE] Reason: {result.reason}")
    print(f"[SPIKE] Phase 2 token: {result.phase2_token_id}")
    print(f"[SPIKE] IntentOS token: {result.intentos_token_id}")
    print(f"[SPIKE] Ticks taken: {result.ticks_taken}")
    print(f"[SPIKE] false_executions: {result.false_executions_at_exit}")

    if not result.success:
        print("\n[SPIKE] FAIL — Bridge did not succeed.")
        print("  See reason above. Fix the bridge before wiring into CommandLoop.")
        return False

    if result.phase2_token_id is None:
        print("\n[SPIKE] FAIL — Phase 2 auth token was not issued.")
        print("  PrimitiveExecutor will block execution.")
        print("  Check: does auth_manager.is_authorized() return True right now?")
        return False

    if result.false_executions_at_exit > 0:
        print(f"\n[SPIKE] FAIL — false_executions={result.false_executions_at_exit}")
        print("  SAFETY VIOLATION. Do not proceed.")
        return False

    print("\n[SPIKE] ✓ BRIDGE WORKS")
    print("  Phase 2 and IntentOS are both confirmed.")
    print("  false_executions == 0")
    print("  Safe to wire ConfirmBridge into CommandLoop._handle_confirm()")
    print("=" * 60 + "\n")
    return True
