"""
IntentOSOrchestrator - main loop for the IntentOS layer.

This sits above Phase 2 and communicates with it exclusively through
ExecutionKernel. It does not import Phase 2 orchestrator or authorization
internals.
"""
from __future__ import annotations

import concurrent.futures as cf
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional

from src.agents import ActionResult, AgentAction, AgentRegistry
from src.coordination import AgentCoordinator, CoordinatorConfig
from src.intentos.attention_budget import AttentionBudget, InterruptClass, InterruptRequest
from src.intentos.recovery import FailureClass, RecoveryEngine
from src.kernel import ExecutionKernel, KernelEvent
from src.planning import (
    CheckpointPlanner,
    CheckpointSegment,
    IntentPlanner,
    PlannerConfig,
    PlanningResult,
    ProposalEngine,
    ScopedExecutionToken,
)
from src.planning.proposal_engine import ExecutionProposal
from src.task_graph.types import TaskGraph, TaskNode, TaskStatus
from src.world_model import WorldModel, WorldModelConfig
from src.world_model.execution_history import DEFAULT_HISTORY_PATH, ExecutionHistory


logger = logging.getLogger(__name__)


class IntentOSState(Enum):
    IDLE = auto()
    PLANNING = auto()
    AWAITING_CONFIRM = auto()
    EXECUTING = auto()
    COMPLETE = auto()
    ABORTED = auto()
    ERROR = auto()


class ObjectiveAuthorizationStatus(Enum):
    ACTIVE = auto()
    COMPLETED = auto()
    REVOKED = auto()


@dataclass
class ObjectiveAuthorization:
    """Record of the objective scope created by a real human confirmation."""

    objective_type: str
    source_goal: str
    phase2_token_id: Optional[str]
    proposal_id: Optional[str] = None
    status: ObjectiveAuthorizationStatus = ObjectiveAuthorizationStatus.ACTIVE
    reason: Optional[str] = None


@dataclass
class ObjectiveContinuationResult:
    """Result of one authorized objective-continuation cycle."""

    accepted: bool
    reason: str
    outcomes: dict[int, dict[str, Optional[str]]] = field(default_factory=dict)


@dataclass
class IntentOSConfig:
    planner: PlannerConfig = field(default_factory=PlannerConfig)
    execution_tick_rate_hz: float = 10.0
    log_execution_steps: bool = True
    execution_history_path: str = DEFAULT_HISTORY_PATH


@dataclass
class ExecutionContext:
    """Tracks the in-progress plan during execution."""

    plan_result: PlanningResult
    proposal: ExecutionProposal
    graph: TaskGraph
    started_at: float
    nodes_completed: int = 0
    last_error: Optional[str] = None


class IntentOSOrchestrator:
    """
    Main IntentOS orchestration loop.

    submit_goal() plans and submits a proposal to the kernel. tick() advances
    Phase 2, reacts to kernel confirmation/cancel events, and executes one
    ready TaskGraph node per execution tick.
    """

    def __init__(
        self,
        kernel: ExecutionKernel,
        agent_registry: AgentRegistry,
        planner: IntentPlanner,
        cfg: IntentOSConfig,
        coordinator: Optional[AgentCoordinator] = None,
    ):
        self._kernel = kernel
        self._registry = agent_registry
        self._planner = planner
        self._proposal_engine = ProposalEngine()
        self._cfg = cfg
        self._state = IntentOSState.IDLE
        self._context: Optional[ExecutionContext] = None
        self._pending_goal: Optional[tuple[str, str]] = None
        self._world_model = WorldModel(WorldModelConfig())
        self._exec_history = ExecutionHistory(self._cfg.execution_history_path)
        self._checkpoint_planner = CheckpointPlanner()
        self._attention = AttentionBudget()
        self._recovery = RecoveryEngine()
        self._segments: list[CheckpointSegment] = []
        self._current_segment_idx: int = 0
        self._current_token: Optional[ScopedExecutionToken] = None
        self._objective_authorization: Optional[ObjectiveAuthorization] = None
        self._planning_executor = cf.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="intentos_planner",
        )
        self._pending_plan_future: Optional[cf.Future] = None
        self._coordinator = coordinator or AgentCoordinator(
            agent_registry=agent_registry,
            cfg=CoordinatorConfig(),
        )

    @property
    def state(self) -> IntentOSState:
        return self._state

    def submit_goal(self, goal: str, scene_summary: str) -> bool:
        """Submit a goal for planning. Returns False if IntentOS is busy."""
        if self._state != IntentOSState.IDLE:
            logger.warning(
                "Goal rejected: IntentOS is in state %s.",
                self._state.name,
            )
            return False

        self._pending_goal = (goal, scene_summary)
        self._state = IntentOSState.PLANNING
        logger.info("Goal accepted: %r", goal)
        return True

    def cancel(self) -> None:
        """Cancel current IntentOS goal. Safe in any state."""
        logger.info("IntentOS cancel requested in state %s", self._state.name)
        self.revoke_objective_authorization("user_cancelled")
        self._state = IntentOSState.ABORTED
        self._context = None
        self._pending_goal = None

    def complete_objective_authorization(self, reason: str = "objective_satisfied") -> None:
        """Mark the active objective authorization complete."""
        auth = self._objective_authorization
        if auth is None or auth.status != ObjectiveAuthorizationStatus.ACTIVE:
            return
        auth.status = ObjectiveAuthorizationStatus.COMPLETED
        auth.reason = reason
        self._complete_phase2_authorization()

    def revoke_objective_authorization(self, reason: str) -> None:
        """Revoke the active objective authorization with an explicit reason."""
        auth = self._objective_authorization
        if auth is None or auth.status != ObjectiveAuthorizationStatus.ACTIVE:
            return
        auth.status = ObjectiveAuthorizationStatus.REVOKED
        auth.reason = reason
        self._invalidate_phase2_authorization(reason)

    def continue_confirmed_objective(
        self,
        live_scene: Any,
        abandoned_object_ids: set[int],
        timeout_s: float = 60.0,
    ) -> ObjectiveContinuationResult:
        """
        Continue a confirmed objective using a fresh graph and scoped token.

        The objective authorization is only a parent scope: this method still
        issues a normal ScopedExecutionToken for the concrete replanned segment,
        and the existing node/token gate remains unchanged.
        """
        refusal = self._validate_active_objective_authorization()
        if refusal is not None:
            return ObjectiveContinuationResult(False, refusal)

        remaining = self._remaining_live_table_objects(
            live_scene,
            abandoned_object_ids,
        )
        if not remaining:
            self.complete_objective_authorization("objective_satisfied")
            return ObjectiveContinuationResult(True, "objective_satisfied", {})

        try:
            graph = self._build_objective_continuation_graph(remaining)
        except RuntimeError as exc:
            return ObjectiveContinuationResult(False, str(exc))
        refusal = self._validate_objective_continuation_graph(
            graph,
            live_scene,
            abandoned_object_ids,
        )
        if refusal is not None:
            return ObjectiveContinuationResult(False, refusal)

        plan_result = PlanningResult(
            graph=graph,
            used_llm=False,
            used_fallback=True,
            repair_attempts=0,
            violations_found=[],
            planning_duration_ms=0.0,
            plan_source="objective_continuation",
        )
        proposal = self._proposal_engine.propose(
            graph,
            plan_result.plan_source,
            str(uuid.uuid4())[:8],
        )
        self._context = ExecutionContext(
            plan_result=plan_result,
            proposal=proposal,
            graph=graph,
            started_at=time.monotonic(),
        )
        self._segments = self._checkpoint_planner.segment(graph)
        self._current_segment_idx = 0
        self._current_token = None
        self._recovery.reset_plan()
        self._issue_current_segment_token()
        if self._current_token is None:
            return ObjectiveContinuationResult(False, "could not issue scoped token")

        self._state = IntentOSState.EXECUTING
        deadline = time.monotonic() + timeout_s
        while self._state == IntentOSState.EXECUTING and time.monotonic() < deadline:
            self.tick()

        if self._state == IntentOSState.EXECUTING:
            return ObjectiveContinuationResult(
                False,
                "objective continuation timed out",
                self._object_outcomes(graph),
            )

        return ObjectiveContinuationResult(
            self._state == IntentOSState.COMPLETE,
            self._state.name.lower(),
            self._object_outcomes(graph),
        )

    def tick(self) -> None:
        """
        Advance IntentOS one step.

        Order:
          1. Advance Phase 2 through ExecutionKernel
          2. Poll kernel events
          3. React and advance IntentOS state
          4. Assert false_executions == 0
        """
        self._kernel.step()
        events = self._kernel.poll_events()
        self._react_to_events(events)
        self._advance_state()
        self._kernel.assert_invariant()

    def get_status(self) -> dict:
        """Return UI/logging status without exposing Phase 2 internals."""
        status = {
            "intentos_state": self._state.name,
            "kernel_state": self._kernel.get_state().name,
            "false_executions": self._kernel.get_capabilities().false_executions,
            "task_graph": [],
            "uncertainty_max": 0.0,
        }
        if self._context is not None:
            graph = self._context.graph
            status.update(
                {
                    "goal": graph.goal,
                    "nodes_total": len(graph.nodes),
                    "nodes_complete": self._context.nodes_completed,
                    "plan_source": self._context.plan_result.plan_source,
                    "planning_ms": round(
                        self._context.plan_result.planning_duration_ms,
                        1,
                    ),
                    "segments_total": len(self._segments),
                    "current_segment_idx": self._current_segment_idx,
                    "task_graph": [
                        {
                            "node_id": n.node_id,
                            "action_type": n.action_type,
                            "parameters": n.parameters,
                            "status": n.status.name,
                            "error": n.error,
                            "uncertainty": round(n.uncertainty.combined, 2),
                        }
                        for n in graph.nodes
                    ],
                    "uncertainty_max": round(
                        max(
                            (n.uncertainty.combined for n in graph.nodes),
                            default=0.0,
                        ),
                        2,
                    ),
                }
            )
        return status

    def _advance_state(self) -> None:
        if self._state == IntentOSState.PLANNING:
            self._do_planning()
        elif self._state == IntentOSState.EXECUTING:
            self._do_execution_tick()

    def _react_to_events(self, events: list[KernelEvent]) -> None:
        for event in events:
            if event.kind == "confirmed" and self._state == IntentOSState.AWAITING_CONFIRM:
                logger.info("Human confirmed proposal - beginning execution")
                self._create_objective_authorization(event)
                self._issue_current_segment_token()
                self._state = IntentOSState.EXECUTING
            elif event.kind == "cancelled":
                logger.info("Human cancelled - aborting")
                self.revoke_objective_authorization("user_cancelled")
                self._state = IntentOSState.ABORTED
                self._context = None
                if self._objective_authorization is None:
                    self._invalidate_phase2_authorization("intentos_cancelled")
            elif event.kind == "failed":
                logger.error("Kernel reported failure: %s", event.details)
                self.revoke_objective_authorization("kernel_failed")
                self._state = IntentOSState.ERROR
                if self._objective_authorization is None:
                    self._invalidate_phase2_authorization("intentos_kernel_failed")

    def _do_planning(self) -> None:
        """
        Non-blocking planning. Submits planner work to a background thread.
        Phase 2 ticks continue while planning runs.
        """
        if self._pending_plan_future is not None:
            if not self._pending_plan_future.done():
                return
            try:
                plan_result = self._pending_plan_future.result()
                self._pending_plan_future = None
                self._on_plan_complete(plan_result)
            except Exception as exc:
                logger.error("Planning failed with exception: %s", exc)
                self._pending_plan_future = None
                self.revoke_objective_authorization("planning_failed")
                self._state = IntentOSState.ERROR
            return

        if self._pending_goal is None:
            self._state = IntentOSState.IDLE
            return

        goal, scene_summary = self._pending_goal
        self._pending_goal = None
        logger.info("Submitting planning for %r to background thread", goal)
        self._pending_plan_future = self._planning_executor.submit(
            self._planner.plan,
            goal,
            scene_summary,
        )

    def _on_plan_complete(self, plan_result: PlanningResult) -> None:
        """Called when background planning finishes. Annotates and submits."""
        world_state = self._get_world_state()
        self._world_model.annotate_graph(plan_result.graph, world_state)
        self._exec_history.annotate_graph(plan_result.graph)
        self._segments = self._checkpoint_planner.segment(plan_result.graph)
        self._current_segment_idx = 0
        self._current_token = None
        self._recovery.reset_plan()

        proposal_id = str(uuid.uuid4())[:8]
        proposal = self._proposal_engine.propose(
            plan_result.graph,
            plan_result.plan_source,
            proposal_id,
        )

        logger.info(
            "Plan complete: source=%s, steps=%d, uncertainty=%s, warning=%s",
            plan_result.plan_source,
            proposal.step_count,
            proposal.uncertainty_level,
            proposal.warning,
        )

        if proposal.uncertainty_level == "abort":
            logger.warning("Plan aborted: %s", proposal.warning)
            self.revoke_objective_authorization("proposal_aborted")
            self._state = IntentOSState.ABORTED
            return

        self._context = ExecutionContext(
            plan_result=plan_result,
            proposal=proposal,
            graph=plan_result.graph,
            started_at=time.monotonic(),
        )

        self._request_checkpoint_confirm(proposal_id)

    def _request_checkpoint_confirm(self, proposal_id: str) -> None:
        """Request confirmation for current checkpoint, respecting attention budget."""
        if self._context is None:
            self._state = IntentOSState.ERROR
            return

        if self._attention.can_interrupt(InterruptClass.CHECKPOINT):
            receipt = self._kernel.submit_proposal(self._context.proposal)
            if receipt.accepted:
                self._attention.record_interrupt()
                self._state = IntentOSState.AWAITING_CONFIRM
            else:
                logger.warning("Kernel rejected proposal: %s", receipt.rejection_reason)
                self._state = IntentOSState.ERROR
        else:
            # Defer - queue and wait for natural pause
            self._attention.defer(InterruptRequest(
                request_id=proposal_id,
                interrupt_class=InterruptClass.CHECKPOINT,
                message=self._context.proposal.summary,
                created_at=time.monotonic(),
            ))
            # Try again after current segment
            self._state = IntentOSState.AWAITING_CONFIRM

    def _do_execution_tick(self) -> None:
        """Execute the current checkpoint segment via coordinator."""
        if self._context is None:
            self._state = IntentOSState.IDLE
            return

        graph = self._context.graph
        if graph.is_complete():
            self._normalize_terminal_recoverable_failures(graph)
            if self._graph_has_unresolved_failures(graph):
                logger.warning("Graph complete with failures")
                self._state = IntentOSState.ERROR
            else:
                logger.info(
                    "Goal achieved: %r (%d steps, %.1fs)",
                    graph.goal,
                    len(graph.nodes),
                    time.monotonic() - self._context.started_at,
                )
                self._state = IntentOSState.COMPLETE
            return

        if self._current_segment_idx >= len(self._segments):
            self._state = IntentOSState.COMPLETE
            return

        segment = self._segments[self._current_segment_idx]

        if self._current_token is None or not self._current_token.is_valid():
            self._state = IntentOSState.AWAITING_CONFIRM
            self._request_checkpoint_confirm(str(uuid.uuid4())[:8])
            return

        uncovered = [
            node_id
            for node_id in segment.node_ids
            if not self._current_token.covers(node_id)
        ]
        if uncovered:
            logger.error(
                "Scoped token does not cover segment nodes %s - HALT.",
                uncovered,
            )
            for node_id in uncovered:
                node = graph.get_node(node_id)
                if node is not None:
                    node.status = TaskStatus.FAILED
                    node.error = "No valid scoped token"
            self.revoke_objective_authorization("unauthorized_scoped_token")
            self._state = IntentOSState.ERROR
            return

        dispatch_result = self._coordinator.execute_segment(
            node_ids=segment.node_ids,
            token=self._current_token,
            graph=graph,
        )
        dispatch_result.segment_id = segment.segment_id

        for node_id, result in dispatch_result.node_results.items():
            node = graph.get_node(node_id)
            if node is not None:
                self._exec_history.record(
                    node.agent_id,
                    node.action_type,
                    result.success,
                )

        if not dispatch_result.all_succeeded:
            for failed_node_id in dispatch_result.failed_node_ids:
                node = graph.get_node(failed_node_id)
                if node is None:
                    continue
                result = dispatch_result.node_results.get(failed_node_id)
                decision = self._recovery.classify(
                    node,
                    graph,
                    result.failure_reason if result else "unknown",
                )
                self._handle_recovery(decision, node, graph)
            return

        self._context.nodes_completed = sum(
            1 for node in graph.nodes if node.status == TaskStatus.DONE
        )
        self._current_segment_idx += 1
        self._current_token = None

        if self._current_segment_idx < len(self._segments):
            next_segment = self._segments[self._current_segment_idx]
            if next_segment.requires_confirmation:
                self._state = IntentOSState.AWAITING_CONFIRM
                self._request_checkpoint_confirm(str(uuid.uuid4())[:8])
            else:
                self._current_token = ScopedExecutionToken.issue(
                    next_segment,
                    self._node_definitions(next_segment),
                )
        elif graph.is_complete() and not graph.has_failures():
            logger.info(
                "Goal achieved: %r (%d steps, %.1fs)",
                graph.goal,
                len(graph.nodes),
                time.monotonic() - self._context.started_at,
            )
            self._state = IntentOSState.COMPLETE
            if not self._has_active_table_clear_authorization():
                if self._objective_authorization is not None:
                    self.complete_objective_authorization("objective_satisfied")
                else:
                    self._complete_phase2_authorization()

    def _execute_node(self, node: TaskNode) -> None:
        agent = self._registry.get(node.agent_id)
        if agent is None:
            node.status = TaskStatus.FAILED
            node.error = f"Agent {node.agent_id!r} not registered"
            return

        # Verify scoped token covers this node
        if self._current_token is None or not self._current_token.covers(node.node_id):
            logger.error(
                "Node %s has no valid scoped token - HALT. "
                "false_executions invariant: this node must NOT execute.",
                node.node_id,
            )
            node.status = TaskStatus.FAILED
            node.error = "No valid scoped token"
            return

        if not self._current_token.is_valid():
            logger.warning("Scoped token expired for node %s", node.node_id)
            node.status = TaskStatus.FAILED
            node.error = "Token expired"
            return

        action = AgentAction(
            node_id=node.node_id,
            action_type=node.action_type,
            parameters=node.parameters,
            agent_id=node.agent_id,
        )

        node.status = TaskStatus.RUNNING
        result: ActionResult = agent.execute(action, self._current_token)

        # Record outcome in execution history
        self._exec_history.record(node.agent_id, node.action_type, result.success)

        if result.success:
            node.status = TaskStatus.DONE
            self._context.nodes_completed += 1
            logger.info("Node %s: DONE (%.0fms)", node.node_id, result.duration_ms)
        else:
            # Recovery
            decision = self._recovery.classify(
                node, self._context.graph, result.failure_reason
            )
            logger.warning(
                "Node %s failed: %s -> %s",
                node.node_id, result.failure_reason, decision.failure_class.name,
            )

            if decision.failure_class == FailureClass.TRANSIENT:
                node.status = TaskStatus.PENDING  # Reset for retry
            elif decision.failure_class == FailureClass.REPLANNING:
                node.status = TaskStatus.FAILED
                self._invalidate_downstream(self._context.graph, node.node_id)
                self._state = IntentOSState.PLANNING
                self._pending_goal = (decision.replan_goal, "")
            else:  # ESCALATION
                node.status = TaskStatus.FAILED
                self._invalidate_downstream(self._context.graph, node.node_id)
                self._state = IntentOSState.ERROR

    def _handle_node_failure(self, node: TaskNode, result: ActionResult) -> None:
        if self._context is None:
            return

        graph = self._context.graph
        decision = self._recovery.classify(node, graph, result.failure_reason)
        self._context.last_error = decision.message

        if decision.failure_class == FailureClass.TRANSIENT:
            node.status = TaskStatus.PENDING
            node.error = decision.message
            logger.info("Node %s transient failure - retrying", node.node_id)
            return

        node.status = TaskStatus.FAILED
        node.error = result.failure_reason
        logger.warning("Node %s: FAILED - %s", node.node_id, result.failure_reason)

        if decision.failure_class == FailureClass.REPLANNING:
            self._state = IntentOSState.ABORTED
            self._current_token = None
            self.revoke_objective_authorization("replanning_required")
            logger.info("Local replan requested: %s", decision.replan_goal)
        else:
            self.revoke_objective_authorization("recovery_error")
            self._state = IntentOSState.ERROR

        self._invalidate_downstream(graph, node.node_id)

    def _handle_recovery(self, decision, node: TaskNode, graph: TaskGraph) -> None:
        """Route recovery decision to appropriate action."""
        from src.intentos.recovery import FailureClass

        if self._context is not None:
            self._context.last_error = decision.message

        if decision.failure_class == FailureClass.TRANSIENT:
            self._reset_agent_error(node.agent_id)
            node.status = TaskStatus.PENDING
            node.error = None
            self._restore_downstream_pending(graph, node.node_id)
            logger.info("Recovery: retry node %s", node.node_id)
        elif decision.failure_class == FailureClass.SKIP:
            self._restore_downstream_pending(graph, node.node_id)
            self._skip_downstream_chain(graph, node.node_id, decision.message)
            self._reset_agent_error(node.agent_id)
            self._record_phase2_object_skipped(node.node_id)
            if self._context is not None:
                self._context.nodes_completed = sum(
                    1 for graph_node in graph.nodes if graph_node.status == TaskStatus.DONE
                )
            logger.info("Recovery: skipped node chain from %s", node.node_id)
        elif decision.failure_class == FailureClass.REPLANNING:
            self._invalidate_downstream(graph, node.node_id)
            self._pending_goal = (decision.replan_goal, "")
            self._state = IntentOSState.PLANNING
            self.revoke_objective_authorization("replanning_required")
            if self._objective_authorization is None:
                self._invalidate_phase2_authorization("intentos_replanning")
            logger.info("Recovery: replan from %s", decision.replan_goal)
        else:
            self._invalidate_downstream(graph, node.node_id)
            self._coordinator.emergency_stop_all()
            self._state = IntentOSState.ERROR
            self.revoke_objective_authorization("safety_escalation")
            if self._objective_authorization is None:
                self._invalidate_phase2_authorization("intentos_escalation")
            logger.error(
                "Recovery: escalation - %s. All agents stopped.",
                decision.escalation_reason,
            )

    def _complete_phase2_authorization(self) -> None:
        complete_authorization = getattr(self._kernel, "complete_authorization", None)
        if callable(complete_authorization):
            complete_authorization()

    def _invalidate_phase2_authorization(self, reason: str) -> None:
        invalidate_authorization = getattr(self._kernel, "invalidate_authorization", None)
        if callable(invalidate_authorization):
            invalidate_authorization(reason)

    def _record_phase2_object_skipped(self, node_id: str) -> None:
        record_object_skipped = getattr(self._kernel, "record_object_skipped", None)
        if not callable(record_object_skipped):
            return
        object_index = 0
        try:
            object_index = int(node_id.rsplit("_", 1)[1])
        except (IndexError, ValueError):
            pass
        record_object_skipped("unreachable_skip", object_index=object_index)

    def _reset_agent_error(self, agent_id: str) -> None:
        """Clear a recoverable agent error so sibling task chains can continue."""
        agent = self._registry.get(agent_id)
        reset_error = getattr(agent, "reset_error", None)
        if callable(reset_error):
            reset_error()

    def _validate_active_objective_authorization(self) -> Optional[str]:
        auth = self._objective_authorization
        if auth is None:
            return "no active objective authorization"
        if auth.status != ObjectiveAuthorizationStatus.ACTIVE:
            return "objective authorization is not active"
        if auth.objective_type != "table_clear":
            return "objective authorization is not for table_clear"
        if not auth.source_goal:
            return "objective authorization has no source goal"
        if not auth.proposal_id:
            return "objective authorization is not tied to a proposal"
        if not auth.phase2_token_id:
            return "objective authorization has no Phase 2 token"

        get_snapshot = getattr(self._kernel, "get_snapshot", None)
        if not callable(get_snapshot):
            return "could not verify Phase 2 token"
        snapshot = get_snapshot()
        if getattr(snapshot, "active_token_id", None) != auth.phase2_token_id:
            return "Phase 2 token is not active for objective"
        return None

    def _has_active_table_clear_authorization(self) -> bool:
        auth = self._objective_authorization
        return (
            auth is not None
            and auth.status == ObjectiveAuthorizationStatus.ACTIVE
            and auth.objective_type == "table_clear"
        )

    @staticmethod
    def _remaining_live_table_objects(
        live_scene: Any,
        abandoned_object_ids: set[int],
    ) -> list[dict]:
        remaining = []
        for obj in getattr(live_scene, "objects_on_table", ()) or ():
            object_id = getattr(obj, "object_id", None)
            pos = getattr(obj, "pos_xyz", None)
            if object_id is None or pos is None:
                continue
            if object_id in abandoned_object_ids:
                continue
            remaining.append(
                {
                    "target": f"object_{object_id}",
                    "target_xyz": list(pos),
                    "object_id": object_id,
                }
            )
        return remaining

    def _build_objective_continuation_graph(
        self,
        remaining_objects: list[dict],
    ) -> TaskGraph:
        heuristic = getattr(self._planner, "_heuristic", None)
        build_nodes = getattr(heuristic, "clean_table_nodes_for_objects", None)
        if not callable(build_nodes):
            raise RuntimeError("planner does not support clean-table continuation")
        auth = self._objective_authorization
        goal = auth.source_goal if auth is not None else "clean the table"
        return TaskGraph(
            graph_id=str(uuid.uuid4())[:8],
            goal=goal,
            nodes=build_nodes(remaining_objects),
            created_at=time.time(),
            plan_confidence=0.6,
            interpretation_note="Objective continuation",
        )

    def _validate_objective_continuation_graph(
        self,
        graph: TaskGraph,
        live_scene: Any,
        abandoned_object_ids: set[int],
    ) -> Optional[str]:
        auth = self._objective_authorization
        if auth is None or auth.objective_type != "table_clear":
            return "objective scope is not table_clear"
        if graph.goal != auth.source_goal:
            return "continuation graph goal differs from confirmed objective"

        allowed_actions = {"reach", "grasp", "move", "release"}
        live_table_ids = {
            getattr(obj, "object_id", None)
            for obj in getattr(live_scene, "objects_on_table", ()) or ()
        }
        live_table_ids.discard(None)

        for node in graph.nodes:
            if node.action_type not in allowed_actions:
                return f"action {node.action_type!r} is outside objective scope"

            params = node.parameters or {}
            object_id = params.get("object_id")
            if object_id is not None:
                if object_id not in live_table_ids:
                    return f"object {object_id!r} is not a live table object"
                if object_id in abandoned_object_ids:
                    return f"object {object_id!r} was abandoned"

            if node.action_type in {"reach", "grasp"} and object_id is None:
                return f"{node.action_type} node {node.node_id!r} has no object_id"

            if node.action_type == "move":
                destination = params.get("target")
                if destination not in {"bin", "tray"}:
                    return f"move destination {destination!r} is outside objective scope"

            for key in ("target_xyz", "destination_xyz"):
                pos = params.get(key)
                if pos is not None and not self._position_in_workspace(pos):
                    return f"{node.node_id}.{key} is outside workspace"

        return None

    @staticmethod
    def _position_in_workspace(pos: Any) -> bool:
        try:
            if len(pos) < 3:
                return False
            x, y, z = (float(pos[0]), float(pos[1]), float(pos[2]))
            return abs(x) <= 1.0 and abs(y) <= 1.0 and 0.0 <= z <= 1.5
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _object_outcomes(graph: TaskGraph) -> dict[int, dict[str, Optional[str]]]:
        chains: dict[str, list[TaskNode]] = {}
        for node in graph.nodes:
            try:
                chain_id = node.node_id.rsplit("_", 1)[1]
            except IndexError:
                continue
            chains.setdefault(chain_id, []).append(node)

        outcomes: dict[int, dict[str, Optional[str]]] = {}
        for nodes in chains.values():
            object_id = None
            for node in nodes:
                object_id = (node.parameters or {}).get("object_id")
                if object_id is not None:
                    break
            if object_id is None:
                continue

            reason = next((node.error for node in nodes if node.error), None)
            statuses = [node.status for node in nodes]
            if any(status == TaskStatus.SKIPPED for status in statuses):
                outcome = "SKIPPED"
            elif any(status in (TaskStatus.FAILED, TaskStatus.INVALIDATED) for status in statuses):
                outcome = "FAILED"
            elif all(status == TaskStatus.DONE for status in statuses):
                outcome = "DONE"
            else:
                outcome = "PENDING"
            outcomes[int(object_id)] = {
                "status": outcome,
                "reason": reason,
            }
        return outcomes

    def _current_segment(self) -> Optional[CheckpointSegment]:
        if 0 <= self._current_segment_idx < len(self._segments):
            return self._segments[self._current_segment_idx]
        return None

    @staticmethod
    def _normalize_terminal_recoverable_failures(graph: TaskGraph) -> None:
        """
        Treat terminal recoverable object failures as skipped outcomes.

        Recovery usually marks the failed object's chain as SKIPPED immediately.
        In physics-timing edge cases a recoverable FAILED/INVALIDATED terminal
        node can survive until graph completion. That is still an honest
        skip-and-continue outcome, not an unresolved safety failure.
        """
        recoverable_error_codes = {
            "grasp_failed",
            "grasp_no_object_id",
            "grasp_no_object_position",
            "unreachable",
            "timeout",
            "move_invalid_pose",
            "move_not_arrived",
            "ik_out_of_limits",
        }
        recoverable_chain_ids = set()
        for node in graph.nodes:
            if node.status not in (TaskStatus.FAILED, TaskStatus.INVALIDATED):
                continue
            error_code = str(node.error or "").strip().lower()
            if error_code not in recoverable_error_codes:
                continue
            chain_id = IntentOSOrchestrator._object_chain_id(node.node_id)
            if chain_id is None:
                continue
            recoverable_chain_ids.add(chain_id)

        for node in graph.nodes:
            chain_id = IntentOSOrchestrator._object_chain_id(node.node_id)
            if chain_id is None:
                continue
            if (
                chain_id in recoverable_chain_ids
                and node.status in (TaskStatus.FAILED, TaskStatus.INVALIDATED)
            ):
                node.status = TaskStatus.SKIPPED
                if not node.error:
                    node.error = "recoverable failure skipped"

    @staticmethod
    def _object_chain_id(node_id: str) -> Optional[str]:
        """
        Return the numeric suffix for clean-table object-chain nodes only.

        Infrastructure failures such as missing agents must remain FAILED and
        surface as ERROR. Only reach_i/grasp_i/move_i/release_i chains can be
        normalized into object-level SKIPPED outcomes.
        """
        try:
            phase, chain_id = node_id.rsplit("_", 1)
        except ValueError:
            return None
        if phase not in {"reach", "grasp", "move", "release"}:
            return None
        if not chain_id.isdigit():
            return None
        return chain_id

    @staticmethod
    def _graph_has_unresolved_failures(graph: TaskGraph) -> bool:
        """True when a terminal graph contains failures not resolved by SKIP."""
        skipped_chain_ids = set()
        for node in graph.nodes:
            if node.status != TaskStatus.SKIPPED:
                continue
            chain_id = IntentOSOrchestrator._object_chain_id(node.node_id)
            if chain_id is None:
                continue
            skipped_chain_ids.add(chain_id)

        for node in graph.nodes:
            if node.status not in (TaskStatus.FAILED, TaskStatus.INVALIDATED):
                continue
            chain_id = IntentOSOrchestrator._object_chain_id(node.node_id)
            if chain_id is None:
                return True
            if chain_id not in skipped_chain_ids:
                return True
        return False

    def _create_objective_authorization(self, event: KernelEvent) -> None:
        """Record the confirmed objective scope tied to this human confirmation."""
        if self._context is None:
            return
        goal = self._context.graph.goal
        self._objective_authorization = ObjectiveAuthorization(
            objective_type=self._objective_type_for_goal(goal),
            source_goal=goal,
            phase2_token_id=event.details.get("phase2_token_id"),
            proposal_id=self._context.proposal.proposal_id,
        )

    @staticmethod
    def _objective_type_for_goal(goal: str) -> str:
        goal_lower = goal.lower()
        if any(word in goal_lower for word in ("clean", "clear", "tidy")):
            return "table_clear"
        return "goal_execution"

    def _current_segment_done(self) -> bool:
        if self._context is None:
            return False
        segment = self._current_segment()
        if segment is None:
            return False
        for node_id in segment.node_ids:
            node = self._context.graph.get_node(node_id)
            if node is not None and node.status == TaskStatus.PENDING:
                return False
        return True

    def _advance_to_next_segment(self) -> None:
        self._current_segment_idx += 1
        self._current_token = None
        if self._current_segment_idx >= len(self._segments):
            return
        self._request_checkpoint_confirm(str(uuid.uuid4())[:8])

    def _issue_current_segment_token(self) -> None:
        if self._context is None:
            return
        segment = self._current_segment()
        if segment is None:
            return
        self._current_token = ScopedExecutionToken.issue(
            segment=segment,
            node_definitions=self._node_definitions(segment),
        )

    def _node_definitions(self, segment: CheckpointSegment) -> list[dict]:
        if self._context is None:
            return []
        definitions = []
        for node_id in segment.node_ids:
            node = self._context.graph.get_node(node_id)
            if node is None:
                continue
            definitions.append(
                {
                    "node_id": node.node_id,
                    "action_type": node.action_type,
                    "agent_id": node.agent_id,
                    "parameters": node.parameters,
                    "depends_on": node.depends_on,
                }
            )
        return definitions

    def _get_world_state(self) -> Optional[dict]:
        """
        Get current world state from Phase 2's vision system.
        Returns None if unavailable - WorldModel degrades gracefully.
        """
        try:
            if hasattr(self._kernel, "_orch"):
                orch = self._kernel._orch
                if hasattr(orch, "get_world_state"):
                    return orch.get_world_state()
                if hasattr(orch, "world_state"):
                    ws = orch.world_state
                    return ws.__dict__ if hasattr(ws, "__dict__") else None
        except Exception as e:
            logger.debug("Could not get world state: %s", e)
        return None

    @staticmethod
    def _invalidate_downstream(graph: TaskGraph, failed_node_id: str) -> None:
        """Mark pending nodes downstream of a failed node as invalidated."""

        def downstream(node_id: str, visited: set[str]) -> set[str]:
            visited.add(node_id)
            for candidate in graph.nodes:
                if node_id in candidate.depends_on and candidate.node_id not in visited:
                    downstream(candidate.node_id, visited)
            return visited

        affected = downstream(failed_node_id, set()) - {failed_node_id}
        for node in graph.nodes:
            if node.node_id in affected and node.status == TaskStatus.PENDING:
                node.status = TaskStatus.INVALIDATED

    @staticmethod
    def _skip_downstream_chain(
        graph: TaskGraph,
        failed_node_id: str,
        reason: str,
    ) -> None:
        """Mark a failed node and its downstream object chain as skipped."""

        def downstream(node_id: str, visited: set[str]) -> set[str]:
            visited.add(node_id)
            for candidate in graph.nodes:
                if node_id in candidate.depends_on and candidate.node_id not in visited:
                    downstream(candidate.node_id, visited)
            return visited

        affected = downstream(failed_node_id, set())
        for node in graph.nodes:
            if node.node_id in affected and node.status != TaskStatus.DONE:
                node.status = TaskStatus.SKIPPED
                if node.node_id != failed_node_id or not node.error:
                    node.error = reason

    @staticmethod
    def _restore_downstream_pending(graph: TaskGraph, node_id: str) -> None:
        """Restore transiently invalidated downstream nodes for retry."""

        def downstream(current_id: str, visited: set[str]) -> set[str]:
            visited.add(current_id)
            for candidate in graph.nodes:
                if current_id in candidate.depends_on and candidate.node_id not in visited:
                    downstream(candidate.node_id, visited)
            return visited

        affected = downstream(node_id, set()) - {node_id}
        failed_ids = {node.node_id for node in graph.nodes if node.status == TaskStatus.FAILED}
        for candidate in graph.nodes:
            if (
                candidate.node_id in affected
                and candidate.status == TaskStatus.INVALIDATED
                and not any(dep in failed_ids for dep in candidate.depends_on)
            ):
                candidate.status = TaskStatus.PENDING
                candidate.error = None
