"""
ExecutionKernel - the single interface between IntentOS and Phase 2.

IntentOS never imports from src/core/orchestrator.py directly.
All access to Phase 2 goes through this class.

Design principles:
- This class is a facade, not a reimplementation.
- It translates between IntentOS concepts and Phase 2 concepts.
- It never bypasses Phase 2's authorization or safety checks.
- If Phase 2 rejects a proposal, ExecutionKernel surfaces that rejection cleanly.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Callable, Optional

from .types import KernelCapabilities, KernelEvent, KernelSnapshot, KernelState, ProposalReceipt

logger = logging.getLogger(__name__)


class ExecutionKernel:
    """
    Facade over Phase 2's orchestrator and authorization system.

    IntentOS uses this class to query kernel state, submit proposals, receive
    events, and advance the wrapped Phase 2 runtime without directly importing
    Phase 2 internals.
    """

    def __init__(
        self,
        phase2_orchestrator: Any,
        phase2_auth_manager: Any = None,
        invariant_checker: Any = None,
        active_agent_ids: frozenset[str] | None = None,
    ):
        self._orch = phase2_orchestrator
        self._auth = phase2_auth_manager or getattr(phase2_orchestrator, "auth_manager", None)
        self._inv = invariant_checker or self._discover_invariant_checker(phase2_orchestrator)
        self._active_agent_ids = active_agent_ids or frozenset({"arm"})
        self._event_callbacks: list[Callable[[KernelEvent], None]] = []
        self._event_queue: list[KernelEvent] = []
        self._last_snapshot: Optional[Any] = None
        self._pending_proposals: dict[str, Any] = {}
        self._last_state = self.get_state()

    @property
    def orchestrator(self) -> Any:
        """Transitional access for adapters. IntentOS should not depend on it."""
        return self._orch

    def get_state(self) -> KernelState:
        """Map Phase 2 FSM state to coarse KernelState."""
        fsm_state = self._phase2_state_value().upper()
        mapping = {
            "IDLE": KernelState.IDLE,
            "SELECTING": KernelState.IDLE,
            "CONFIRMING": KernelState.AWAITING_CONFIRM,
            "AWAITING_CONFIRM": KernelState.AWAITING_CONFIRM,
            "EXECUTING": KernelState.EXECUTING,
            "PAUSED": KernelState.PAUSED,
            "DONE": KernelState.IDLE,
            "ERROR": KernelState.ERROR,
        }
        return mapping.get(fsm_state, KernelState.IDLE)

    def get_capabilities(self) -> KernelCapabilities:
        """Query what the kernel can currently accept."""
        state = self.get_state()
        false_exec = self._false_executions()
        return KernelCapabilities(
            can_accept_proposal=state == KernelState.IDLE and false_exec == 0,
            active_agent_ids=self._active_agent_ids,
            false_executions=false_exec,
        )

    def get_snapshot(self) -> KernelSnapshot:
        """Return a kernel-level diagnostic snapshot."""
        executor = getattr(self._orch, "executor", None)
        executor_status = getattr(getattr(executor, "status", None), "value", None)
        active_token_id = None
        if self._auth is not None and hasattr(self._auth, "get_active_token_id"):
            active_token_id = self._auth.get_active_token_id()

        return KernelSnapshot(
            frame=int(getattr(self._orch, "global_frame_counter", 0)),
            state=self.get_state(),
            capabilities=self.get_capabilities(),
            executor_status=executor_status,
            active_token_id=active_token_id,
        )

    def submit_proposal(self, proposal: Any, maybe_proposal: Any = None) -> ProposalReceipt:
        """
        Submit an IntentProposal to the kernel for human confirmation.

        New 3A.1 usage is submit_proposal(proposal). During the 3A transition,
        submit_proposal(proposal_id, proposal) is also accepted for compatibility.
        """
        provided_id: Optional[str] = None
        if maybe_proposal is not None:
            provided_id = str(proposal)
            proposal = maybe_proposal

        caps = self.get_capabilities()
        proposal_id = provided_id or str(uuid.uuid4())[:8]
        if not proposal_id:
            return ProposalReceipt("", accepted=False, rejection_reason="missing_proposal_id")

        if not caps.can_accept_proposal:
            reason = f"Kernel not ready: state={self.get_state().name}"
            logger.warning("Proposal rejected: %s", reason)
            return ProposalReceipt(
                proposal_id=proposal_id,
                accepted=False,
                rejection_reason=reason,
            )

        try:
            if hasattr(self._orch, "set_proposal"):
                self._orch.set_proposal(proposal)
            elif hasattr(self._orch, "submit_proposal"):
                self._orch.submit_proposal(proposal)
            else:
                # Current Phase 2 does not expose a stable external proposal
                # injection point. For 3A, record the proposal at the facade and
                # keep execution gated by the existing orchestrator.
                self._pending_proposals[proposal_id] = proposal

            event = KernelEvent(
                kind="proposal_submitted",
                proposal_id=proposal_id,
                agent_id=None,
                timestamp_ms=time.time() * 1000.0,
                details={},
            )
            self._emit(event)
            logger.info("Proposal %s submitted to kernel", proposal_id)
            return ProposalReceipt(proposal_id=proposal_id, accepted=True)
        except Exception as exc:
            logger.error("Proposal submission failed: %s", exc)
            return ProposalReceipt(
                proposal_id=proposal_id,
                accepted=False,
                rejection_reason=str(exc),
            )

    def register_event_callback(self, callback: Callable[[KernelEvent], None]) -> None:
        """Register a callback that IntentOS uses to react to kernel events."""
        self._event_callbacks.append(callback)

    def poll_events(self) -> list[KernelEvent]:
        """
        Called each orchestration tick to collect kernel events.
        Detects state transitions and surfaces them as events.
        """
        events = list(self._event_queue)
        self._event_queue.clear()

        current_state = self.get_state()
        if current_state != self._last_state:
            event = KernelEvent(
                kind=self._state_transition_kind(self._last_state, current_state),
                proposal_id=None,
                agent_id=None,
                timestamp_ms=time.time() * 1000.0,
                details={
                    "from": self._last_state.name,
                    "to": current_state.name,
                },
            )
            self._last_state = current_state
            self._notify_callbacks(event)
            events.append(event)

        return events

    def drain_events(self) -> tuple[KernelEvent, ...]:
        """Compatibility alias: return queued events and clear them."""
        return tuple(self.poll_events())

    def step(self) -> KernelSnapshot:
        """
        Advance Phase 2 one tick. Called by the IntentOS main loop.
        Returns a KernelSnapshot for convenience.
        """
        if hasattr(self._orch, "step"):
            self._last_snapshot = self._orch.step()
        self.assert_invariant()
        return self.get_snapshot()

    def assert_invariant(self) -> None:
        """Assert false_executions == 0. This cannot be bypassed."""
        if self._inv is not None and hasattr(self._inv, "assert_invariant"):
            self._inv.assert_invariant()

        false_exec = self._false_executions()
        if false_exec != 0:
            raise RuntimeError(
                f"SAFETY VIOLATION: false_executions == {false_exec}. "
                "System must halt immediately."
            )

    def assert_safety_invariant(self) -> None:
        """Compatibility alias for earlier 3A tests."""
        self.assert_invariant()

    def close(self) -> None:
        """Close the wrapped runtime if it exposes cleanup."""
        close = getattr(self._orch, "close", None)
        if callable(close):
            close()

    @staticmethod
    def _state_transition_kind(from_state: KernelState, to_state: KernelState) -> str:
        if to_state == KernelState.AWAITING_CONFIRM:
            return "awaiting_confirm"
        if from_state == KernelState.AWAITING_CONFIRM and to_state == KernelState.EXECUTING:
            return "confirmed"
        if from_state == KernelState.AWAITING_CONFIRM and to_state == KernelState.IDLE:
            return "cancelled"
        if from_state == KernelState.EXECUTING and to_state == KernelState.IDLE:
            return "executed"
        if to_state == KernelState.ERROR:
            return "failed"
        if to_state == KernelState.PAUSED:
            return "paused"
        return "state_changed"

    def _phase2_state_value(self) -> str:
        phase2_state = getattr(self._last_snapshot, "state", None)
        if phase2_state is None:
            phase2_state = getattr(self._orch, "state", None)
        if phase2_state is None:
            state_machine = getattr(self._orch, "state_machine", None)
            phase2_state = getattr(state_machine, "state", None)
        return str(getattr(phase2_state, "value", phase2_state or "IDLE"))

    def _false_executions(self) -> int:
        if self._inv is not None and hasattr(self._inv, "false_executions"):
            return int(getattr(self._inv, "false_executions", 0))
        trust_metrics = getattr(self._orch, "trust_metrics", None)
        return int(getattr(trust_metrics, "false_executions", 0))

    def _emit(self, event: KernelEvent) -> None:
        self._event_queue.append(event)
        self._notify_callbacks(event)

    def _notify_callbacks(self, event: KernelEvent) -> None:
        for callback in self._event_callbacks:
            try:
                callback(event)
            except Exception as exc:
                logger.error("Event callback raised: %s", exc)

    @staticmethod
    def _discover_invariant_checker(orchestrator: Any) -> Any:
        executor = getattr(orchestrator, "executor", None)
        return getattr(executor, "_invariant_checker", None)


class KernelAPI(ExecutionKernel):
    """Backward-compatible name from the first 3A foundation pass."""
