"""
Kernel-level types. IntentOS reads these. Phase 2 internals produce them.
No Phase 2 internal types leak past this boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional


class KernelState(Enum):
    """Coarse-grained view of Phase 2 FSM state, as seen by IntentOS."""

    IDLE = auto()
    AWAITING_CONFIRM = auto()
    EXECUTING = auto()
    PAUSED = auto()
    ERROR = auto()


@dataclass(frozen=True)
class KernelCapabilities:
    """What the kernel can currently do. Queried before submitting proposals."""

    can_accept_proposal: bool
    active_agent_ids: frozenset[str]
    false_executions: int


@dataclass(frozen=True)
class ProposalReceipt:
    """Returned when a proposal is submitted to the kernel."""

    proposal_id: str
    accepted: bool
    rejection_reason: Optional[str] = None


@dataclass(frozen=True)
class KernelEvent:
    """An event emitted by the kernel that IntentOS may react to."""

    kind: str
    proposal_id: Optional[str]
    agent_id: Optional[str]
    timestamp_ms: float
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KernelSnapshot:
    """Diagnostic snapshot for tests and UI glue; uses only kernel-level types."""

    frame: int
    state: KernelState
    capabilities: KernelCapabilities
    executor_status: Optional[str] = None
    active_token_id: Optional[str] = None
