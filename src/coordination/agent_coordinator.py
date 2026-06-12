"""
AgentCoordinator - schedules and dispatches TaskGraph nodes to agents.

Responsibilities:
  - Resource conflict detection (named resources, spatial zones, envelopes)
  - Timing dependency enforcement (min_delay_after_s between nodes)
  - Parallel dispatch (different agents, no conflicts)
  - Deadlock detection and conservative resolution
  - Per-agent result collection

The coordinator dispatches work. It never issues authorization tokens.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from src.agents.agent_base import ActionResult, AgentAction
from src.agents.agent_registry import AgentRegistry
from src.task_graph.types import ResourceRegistry, TaskGraph, TaskNode, TaskStatus

logger = logging.getLogger(__name__)

DISPATCH_TICK_S = 0.1
DEADLOCK_TIMEOUT_S = 30.0


@dataclass
class CoordinatorConfig:
    max_parallel_agents: int = 4
    deadlock_timeout_s: float = DEADLOCK_TIMEOUT_S
    dispatch_tick_s: float = DISPATCH_TICK_S


@dataclass
class DispatchResult:
    """Result of executing one checkpoint segment."""

    segment_id: str
    node_results: dict[str, ActionResult]
    all_succeeded: bool
    failed_node_ids: list[str]
    total_duration_ms: float


class AgentCoordinator:
    """
    Schedules and dispatches nodes to agents within a checkpoint segment.
    Called by IntentOSOrchestrator after a token is issued for a segment.
    """

    def __init__(
        self,
        agent_registry: AgentRegistry,
        cfg: CoordinatorConfig,
    ):
        self._registry = agent_registry
        self._cfg = cfg
        self._resource_registry = ResourceRegistry()
        self._executor = ThreadPoolExecutor(
            max_workers=cfg.max_parallel_agents,
            thread_name_prefix="coord_agent",
        )

    def execute_segment(
        self,
        node_ids: list[str],
        token: Any,
        graph: TaskGraph,
    ) -> DispatchResult:
        """
        Execute all nodes in a segment, respecting resource and timing constraints.
        Token is passed to every agent.execute() call and never bypassed.
        """
        t0 = time.monotonic()
        segment_nodes = [graph.get_node(node_id) for node_id in node_ids]
        segment_nodes = [node for node in segment_nodes if node is not None]
        node_results: dict[str, ActionResult] = {}
        pending_futures: dict[Future, str] = {}
        completion_times: dict[str, float] = {}
        active_agents: set[str] = set()
        last_progress = time.monotonic()
        segment_failed = False

        while True:
            ready = self._ready_to_dispatch(
                segment_nodes=segment_nodes,
                graph=graph,
                pending_futures=pending_futures,
                completion_times=completion_times,
            )

            ready_to_dispatch = [] if segment_failed else ready
            for node in ready_to_dispatch:
                if node.agent_id in active_agents:
                    continue
                if not self._try_claim_resources(node):
                    continue

                agent = self._registry.get(node.agent_id)
                if agent is None:
                    node.status = TaskStatus.FAILED
                    node.error = f"Agent {node.agent_id!r} not registered"
                    node_results[node.node_id] = ActionResult(
                        node_id=node.node_id,
                        success=False,
                        failure_reason=node.error,
                        world_state_delta={},
                        duration_ms=0.0,
                    )
                    self._invalidate_downstream_in_segment(segment_nodes, node.node_id)
                    segment_failed = True
                    self._release_resources(node.node_id)
                    last_progress = time.monotonic()
                    continue

                action = AgentAction(
                    node_id=node.node_id,
                    action_type=node.action_type,
                    parameters=node.parameters,
                    agent_id=node.agent_id,
                )
                node.status = TaskStatus.RUNNING
                active_agents.add(node.agent_id)
                logger.info(
                    "Coordinator dispatching %s -> agent %s",
                    node.node_id,
                    node.agent_id,
                )
                future = self._executor.submit(agent.execute, action, token)
                pending_futures[future] = node.node_id
                last_progress = time.monotonic()

            done_futures = [future for future in list(pending_futures) if future.done()]
            for future in done_futures:
                node_id = pending_futures.pop(future)
                node = graph.get_node(node_id)
                try:
                    result: ActionResult = future.result()
                except Exception as exc:
                    result = ActionResult(
                        node_id=node_id,
                        success=False,
                        failure_reason=f"Exception: {exc}",
                        world_state_delta={},
                        duration_ms=0.0,
                    )

                node_results[node_id] = result
                completion_times[node_id] = time.monotonic()
                if node is not None:
                    node.status = TaskStatus.DONE if result.success else TaskStatus.FAILED
                    if not result.success:
                        node.error = result.failure_reason
                        self._invalidate_downstream_in_segment(segment_nodes, node_id)
                        segment_failed = True
                    active_agents.discard(node.agent_id)
                self._release_resources(node_id)
                last_progress = time.monotonic()

            if segment_failed and not pending_futures:
                break

            all_terminal = all(node.is_terminal for node in segment_nodes)
            if all_terminal and not pending_futures:
                break

            if time.monotonic() - last_progress > self._cfg.deadlock_timeout_s:
                logger.warning(
                    "Coordinator: potential deadlock detected (%.1fs without progress).",
                    self._cfg.deadlock_timeout_s,
                )
                self._break_deadlock(segment_nodes, graph, pending_futures)
                active_agents = {
                    graph.get_node(node_id).agent_id
                    for node_id in pending_futures.values()
                    if graph.get_node(node_id) is not None
                }
                last_progress = time.monotonic()

            time.sleep(self._cfg.dispatch_tick_s)

        total_ms = (time.monotonic() - t0) * 1000.0
        failed = [node_id for node_id, result in node_results.items() if not result.success]
        return DispatchResult(
            segment_id="",
            node_results=node_results,
            all_succeeded=len(failed) == 0,
            failed_node_ids=failed,
            total_duration_ms=total_ms,
        )

    def emergency_stop_all(self) -> None:
        """Fire-and-forget stop on all registered agents. Never raises."""
        for agent in self._registry.all_agents():
            try:
                agent.emergency_stop()
            except Exception:
                pass

    def shutdown(self) -> None:
        """Clean shutdown of thread pool."""
        self._executor.shutdown(wait=False)

    def _ready_to_dispatch(
        self,
        segment_nodes: list[TaskNode],
        graph: TaskGraph,
        pending_futures: dict[Future, str],
        completion_times: dict[str, float] | None = None,
    ) -> list[TaskNode]:
        """
        Nodes eligible for dispatch:
          - Status is PENDING
          - Not already running
          - All dependencies are DONE
          - Dependency min_delay_after_s windows have elapsed
        """
        completion_times = completion_times or {}
        pending_node_ids = set(pending_futures.values())
        done_ids = {node.node_id for node in graph.nodes if node.status == TaskStatus.DONE}
        now = time.monotonic()
        ready = []

        for node in segment_nodes:
            if node.status != TaskStatus.PENDING:
                continue
            if node.node_id in pending_node_ids:
                continue
            if not all(dep in done_ids for dep in node.depends_on):
                continue
            if not self._dependency_delays_elapsed(node, graph, completion_times, now):
                continue
            ready.append(node)

        return self._prioritize_object_chain_nodes(ready, segment_nodes)

    @classmethod
    def _prioritize_object_chain_nodes(
        cls,
        ready: list[TaskNode],
        segment_nodes: list[TaskNode],
    ) -> list[TaskNode]:
        """
        Prefer draining one reach/grasp/move/release object chain at a time.

        Clean-table graphs keep object chains dependency-independent so a failed
        object can be skipped without blocking siblings. Physically, though, the
        arm can hold only one object. This ordering policy continues an
        already-started object chain before starting another reach_N, without
        adding cross-object graph dependencies.
        """
        if len(ready) < 2:
            return ready

        parsed_ready = [cls._object_chain_key(node) for node in ready]
        if any(parsed is None for parsed in parsed_ready):
            return ready

        active_indices = cls._active_object_chain_indices(segment_nodes)
        target_index = min(active_indices) if active_indices else None
        original_order = {node.node_id: i for i, node in enumerate(ready)}

        def sort_key(node: TaskNode) -> tuple[int, int, int, int]:
            parsed = cls._object_chain_key(node)
            assert parsed is not None
            object_index, phase_rank = parsed
            if target_index is None:
                priority = 0
            else:
                priority = 0 if object_index == target_index else 1
            return (priority, object_index, phase_rank, original_order[node.node_id])

        return sorted(ready, key=sort_key)

    @classmethod
    def _active_object_chain_indices(cls, segment_nodes: list[TaskNode]) -> set[int]:
        chains: dict[int, list[TaskNode]] = {}
        for node in segment_nodes:
            parsed = cls._object_chain_key(node)
            if parsed is None:
                continue
            object_index, _ = parsed
            chains.setdefault(object_index, []).append(node)

        active = set()
        for object_index, nodes in chains.items():
            has_started = any(
                node.status in (TaskStatus.DONE, TaskStatus.RUNNING)
                for node in nodes
            )
            # Keep the chain active until every phase present in this segment,
            # including release_i, reaches a terminal state. A SKIPPED chain is
            # terminal and therefore releases the ordering lock.
            has_open_phase = any(not node.is_terminal for node in nodes)
            if has_started and has_open_phase:
                active.add(object_index)
        return active

    @staticmethod
    def _object_chain_key(node: TaskNode) -> tuple[int, int] | None:
        phase_ranks = {
            "reach": 0,
            "grasp": 1,
            "move": 2,
            "release": 3,
        }
        try:
            phase, suffix = node.node_id.rsplit("_", 1)
        except ValueError:
            return None
        if phase not in phase_ranks or not suffix.isdigit():
            return None
        return int(suffix), phase_ranks[phase]

    @staticmethod
    def _dependency_delays_elapsed(
        node: TaskNode,
        graph: TaskGraph,
        completion_times: dict[str, float],
        now: float,
    ) -> bool:
        for dep_id in node.depends_on:
            dep = graph.get_node(dep_id)
            if dep is None or dep.resource_claim is None:
                continue
            delay = dep.resource_claim.min_delay_after_s
            if delay <= 0.0:
                continue
            completed_at = completion_times.get(dep_id)
            if completed_at is None or now - completed_at < delay:
                return False
        return True

    def _try_claim_resources(self, node: TaskNode) -> bool:
        if node.resource_claim is None:
            return True
        return self._resource_registry.claim(node.resource_claim)

    def _release_resources(self, node_id: str) -> None:
        self._resource_registry.release(node_id)

    def _break_deadlock(
        self,
        segment_nodes: list[TaskNode],
        graph: TaskGraph,
        pending_futures: dict[Future, str],
    ) -> None:
        """
        Conservative deadlock resolution.
        De-prioritizes the running node with highest uncertainty if cancellation
        is still possible. Already-running threads may finish normally.
        """
        pending_node_ids = set(pending_futures.values())
        pending_nodes = [
            node for node in segment_nodes if node.node_id in pending_node_ids
        ]
        if not pending_nodes:
            return

        target = max(pending_nodes, key=lambda node: node.uncertainty.combined)
        target_future = next(
            (
                future
                for future, node_id in pending_futures.items()
                if node_id == target.node_id
            ),
            None,
        )

        if target_future and target_future.cancel():
            pending_futures.pop(target_future, None)
            target.status = TaskStatus.PENDING
            self._release_resources(target.node_id)
            logger.warning(
                "Deadlock broken: de-prioritized node %s (uncertainty=%.2f).",
                target.node_id,
                target.uncertainty.combined,
            )

    @staticmethod
    def _invalidate_downstream_in_segment(
        segment_nodes: list[TaskNode],
        failed_node_id: str,
    ) -> None:
        pending = {node.node_id: node for node in segment_nodes}

        def visit(node_id: str) -> None:
            for candidate in pending.values():
                if (
                    node_id in candidate.depends_on
                    and candidate.status == TaskStatus.PENDING
                ):
                    candidate.status = TaskStatus.INVALIDATED
                    candidate.error = f"Dependency {node_id!r} failed"
                    visit(candidate.node_id)

        visit(failed_node_id)
