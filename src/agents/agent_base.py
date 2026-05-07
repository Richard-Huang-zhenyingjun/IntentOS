"""
AgentBase - the contract every IntentOS agent must implement.

Key design decisions:
- execute() takes an AuthorizationToken. Agents never execute without one.
- can_execute() is a dry-run check. Fast. No side effects.
- get_state() is non-blocking. Reflects last known state.
- emergency_stop() is fire-and-forget. Never raises.

The token passed to execute() comes from Phase 2's AuthorizationManager.
Agents never issue their own tokens.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional


class AgentStatus(Enum):
    IDLE = auto()
    EXECUTING = auto()
    PAUSED = auto()
    ERROR = auto()
    UNAVAILABLE = auto()


@dataclass(frozen=True)
class AgentState:
    agent_id: str
    status: AgentStatus
    current_action: Optional[str]
    error_message: Optional[str]
    metadata: dict


@dataclass(frozen=True)
class AgentAction:
    """
    A single action request from IntentOS to an agent.
    Corresponds to one TaskNode in a TaskGraph.
    """

    node_id: str
    action_type: str
    parameters: dict
    agent_id: str


@dataclass(frozen=True)
class ActionResult:
    node_id: str
    success: bool
    failure_reason: Optional[str]
    world_state_delta: dict
    duration_ms: float

    @property
    def message(self) -> str:
        return self.failure_reason or ""

    @property
    def data(self) -> dict:
        return self.world_state_delta


@dataclass(frozen=True)
class AgentCapability:
    """Compatibility descriptor for early registries and UI surfaces."""

    action_type: str
    description: str = ""


class AgentBase(ABC):
    """
    Abstract base for all IntentOS agents.

    Implementing this contract is sufficient to plug any agent
    (arm, drone, conveyor, camera) into the IntentOS coordinator.
    """

    @property
    @abstractmethod
    def agent_id(self) -> str:
        """Unique identifier. Used by TaskGraph node routing."""
        ...

    @abstractmethod
    def can_execute(self, action: AgentAction) -> tuple[bool, Optional[str]]:
        """
        Dry-run check. Returns (can_do, reason_if_not).
        Must be fast and have no side effects.
        """
        ...

    @abstractmethod
    def execute(self, action: AgentAction, token: Any) -> ActionResult:
        """
        Execute action with authorization token.
        Token comes from Phase 2's AuthorizationManager.
        """
        ...

    @abstractmethod
    def get_state(self) -> AgentState:
        """Non-blocking. Returns last known state."""
        ...

    @abstractmethod
    def emergency_stop(self) -> None:
        """Fire-and-forget. Must never raise."""
        ...
