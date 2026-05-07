"""
TaskGraph data types.

These are data containers for IntentOS planning. The planner produces them.
The validator checks them. The coordinator executes them. The world model
annotates them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional


class TaskStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    DONE = auto()
    FAILED = auto()
    INVALIDATED = auto()
    SKIPPED = auto()


class ConfirmationPolicy(Enum):
    NEVER = auto()
    CHECKPOINT = auto()
    ALWAYS = auto()


@dataclass(frozen=True)
class SpatialEnvelope:
    """
    3D bounding box representing physical space occupied during node execution.
    Units are meters, in world frame.
    """

    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float

    def intersects(self, other: "SpatialEnvelope") -> bool:
        """True if this envelope overlaps with another in all three dimensions."""
        return (
            self.x_min < other.x_max
            and self.x_max > other.x_min
            and self.y_min < other.y_max
            and self.y_max > other.y_min
            and self.z_min < other.z_max
            and self.z_max > other.z_min
        )


@dataclass(frozen=True)
class ResourceClaim:
    """
    Resources a node requires exclusively during execution.
    """

    agent_id: str
    node_id: str
    named_resources: frozenset[str]
    spatial_zone: Optional[str]
    spatial_envelope: Optional[SpatialEnvelope] = None
    estimated_duration_s: float = 2.0
    min_delay_after_s: float = 0.0


@dataclass
class ResourceRegistry:
    """
    Tracks resources currently claimed by running nodes.
    Used by AgentCoordinator during dispatch.
    """

    _active: Optional[dict[str, ResourceClaim]] = None

    def __post_init__(self) -> None:
        if self._active is None:
            self._active = {}

    def claim(self, claim: ResourceClaim) -> bool:
        """
        Attempt to claim resources. Returns True when no conflicts are active.
        """
        assert self._active is not None
        for active_claim in self._active.values():
            if claim.named_resources & active_claim.named_resources:
                return False
            if claim.spatial_zone and claim.spatial_zone == active_claim.spatial_zone:
                return False
            if (
                claim.spatial_envelope
                and active_claim.spatial_envelope
                and claim.spatial_envelope.intersects(active_claim.spatial_envelope)
            ):
                return False
        self._active[claim.node_id] = claim
        return True

    def release(self, node_id: str) -> None:
        assert self._active is not None
        self._active.pop(node_id, None)

    def is_claimed(self, resource_name: str) -> bool:
        assert self._active is not None
        return any(resource_name in claim.named_resources for claim in self._active.values())

    def active_node_ids(self) -> list[str]:
        assert self._active is not None
        return list(self._active.keys())


@dataclass(frozen=True)
class UncertaintySignals:
    """
    Three-signal uncertainty model.
    """

    perception_confidence: float
    execution_history_rate: float
    simulation_risk: float

    @property
    def combined(self) -> float:
        """
        Weighted uncertainty score. 1.0 is high uncertainty; 0.0 is certain.
        """
        return (
            0.35 * (1.0 - self.perception_confidence)
            + 0.35 * (1.0 - self.execution_history_rate)
            + 0.30 * self.simulation_risk
        )

    @classmethod
    def unknown(cls) -> "UncertaintySignals":
        """Conservative default when signals are not yet computed."""
        return cls(
            perception_confidence=0.5,
            execution_history_rate=0.5,
            simulation_risk=0.5,
        )


@dataclass
class TaskNode:
    """
    A single step in a TaskGraph.
    Mutable because status changes during execution.
    """

    node_id: str
    action_type: str
    agent_id: str
    parameters: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    confirmation_policy: ConfirmationPolicy = ConfirmationPolicy.CHECKPOINT
    uncertainty: UncertaintySignals = field(default_factory=UncertaintySignals.unknown)
    resource_claim: Optional[ResourceClaim] = None
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            TaskStatus.DONE,
            TaskStatus.FAILED,
            TaskStatus.INVALIDATED,
            TaskStatus.SKIPPED,
        )

    @property
    def params(self) -> dict[str, Any]:
        """Compatibility alias for earlier 3A code."""
        return self.parameters


@dataclass
class TaskGraph:
    """
    A complete plan for achieving a goal.
    Produced by the planner. Validated before reaching the kernel.
    """

    graph_id: str
    goal: str
    nodes: list[TaskNode]
    created_at: float
    plan_confidence: float = 1.0
    interpretation_note: Optional[str] = None

    @classmethod
    def from_nodes(
        cls,
        graph_id: str,
        nodes: list[TaskNode],
        goal: str = "",
        degraded: bool = False,
    ) -> "TaskGraph":
        graph = cls(
            graph_id=graph_id,
            goal=goal,
            nodes=nodes,
            created_at=0.0,
            interpretation_note="degraded" if degraded else None,
        )
        return graph

    def get_node(self, node_id: str) -> Optional[TaskNode]:
        return next((n for n in self.nodes if n.node_id == node_id), None)

    def ready_nodes(self) -> list[TaskNode]:
        """Nodes whose dependencies are all DONE and which are still PENDING."""
        done_ids = {n.node_id for n in self.nodes if n.status == TaskStatus.DONE}
        return [
            n
            for n in self.nodes
            if n.status == TaskStatus.PENDING
            and all(dep in done_ids for dep in n.depends_on)
        ]

    def is_complete(self) -> bool:
        return all(n.is_terminal for n in self.nodes)

    def has_failures(self) -> bool:
        return any(
            n.status in (TaskStatus.FAILED, TaskStatus.INVALIDATED)
            for n in self.nodes
        )

    def summary(self) -> str:
        total = len(self.nodes)
        done = sum(1 for n in self.nodes if n.status == TaskStatus.DONE)
        return f"Goal: {self.goal!r} - {done}/{total} steps complete"
