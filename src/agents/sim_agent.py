"""
SimAgent - simulated second agent for multi-agent testing.

Implements AgentBase fully. Simulates execution with:
  - Configurable success rate per action type
  - Realistic timing (configurable per action)
  - Optional random failure injection for recovery testing

SimAgent is not a stub. It exercises the full coordinator -> token -> execute
-> result path without moving physical hardware.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Any, Optional

from .agent_base import (
    ActionResult,
    AgentAction,
    AgentBase,
    AgentState,
    AgentStatus,
)

logger = logging.getLogger(__name__)

DEFAULT_TIMING_S: dict[str, float] = {
    "reach": 1.5,
    "grasp": 1.0,
    "move": 2.0,
    "release": 0.5,
    "home": 2.0,
}

DEFAULT_SUCCESS_RATES: dict[str, float] = {
    "reach": 0.90,
    "grasp": 0.80,
    "move": 0.95,
    "release": 0.99,
    "home": 0.99,
}

SUPPORTED_ACTIONS = set(DEFAULT_TIMING_S.keys())


class SimAgentConfig:
    def __init__(
        self,
        success_rates: Optional[dict] = None,
        timing_s: Optional[dict] = None,
        seed: int = 42,
        simulate_delays: bool = True,
    ):
        self.success_rates = success_rates or DEFAULT_SUCCESS_RATES
        self.timing_s = timing_s or DEFAULT_TIMING_S
        self.seed = seed
        self.simulate_delays = simulate_delays


class SimAgent(AgentBase):
    """
    Simulated second agent. Implements AgentBase fully.
    Uses configurable success rates and timing.
    """

    def __init__(
        self,
        agent_id: str = "sim_agent",
        cfg: Optional[SimAgentConfig] = None,
    ):
        self._agent_id = agent_id
        self._cfg = cfg or SimAgentConfig()
        self._rng = random.Random(self._cfg.seed)
        self._state = AgentState(
            agent_id=agent_id,
            status=AgentStatus.IDLE,
            current_action=None,
            error_message=None,
            metadata={},
        )
        self._actions_executed = 0

    @property
    def agent_id(self) -> str:
        return self._agent_id

    def can_execute(self, action: AgentAction) -> tuple[bool, Optional[str]]:
        if action.action_type not in SUPPORTED_ACTIONS:
            return False, f"Unsupported: {action.action_type!r}"
        if self._state.status == AgentStatus.EXECUTING:
            return False, "Already executing"
        if self._state.status == AgentStatus.ERROR:
            return False, f"In error state: {self._state.error_message}"
        return True, None

    def execute(self, action: AgentAction, token: Any) -> ActionResult:
        """
        Simulate execution with realistic timing and configurable success rate.
        Token is accepted here; orchestrator/coordinator validates scope.
        """
        can_do, reason = self.can_execute(action)
        if not can_do:
            return ActionResult(
                node_id=action.node_id,
                success=False,
                failure_reason=reason,
                world_state_delta={},
                duration_ms=0.0,
            )

        self._state = AgentState(
            agent_id=self._agent_id,
            status=AgentStatus.EXECUTING,
            current_action=action.action_type,
            error_message=None,
            metadata={"node_id": action.node_id},
        )

        t0 = time.monotonic()

        if self._cfg.simulate_delays:
            delay = self._cfg.timing_s.get(action.action_type, 2.0)
            time.sleep(delay)

        rate = self._cfg.success_rates.get(action.action_type, 0.9)
        success = self._rng.random() < rate
        self._actions_executed += 1

        duration_ms = (time.monotonic() - t0) * 1000.0

        failure_reason = None
        if not success:
            failure_reason = self._generate_failure_reason(action.action_type)
            logger.info(
                "SimAgent %s: %s FAILED (%s)",
                self._agent_id,
                action.action_type,
                failure_reason,
            )

        self._state = AgentState(
            agent_id=self._agent_id,
            status=AgentStatus.IDLE if success else AgentStatus.ERROR,
            current_action=None,
            error_message=failure_reason,
            metadata={"actions_executed": self._actions_executed},
        )

        return ActionResult(
            node_id=action.node_id,
            success=success,
            failure_reason=failure_reason,
            world_state_delta={
                "action": action.action_type,
                "agent": self._agent_id,
                "success": success,
            },
            duration_ms=duration_ms,
        )

    def get_state(self) -> AgentState:
        return self._state

    def emergency_stop(self) -> None:
        """SimAgent: update state to PAUSED. Never raises."""
        try:
            self._state = AgentState(
                agent_id=self._agent_id,
                status=AgentStatus.PAUSED,
                current_action=None,
                error_message="Emergency stop",
                metadata={},
            )
        except Exception:
            pass

    def reset_error(self) -> None:
        """Reset error state so the agent can be reused after failure."""
        if self._state.status == AgentStatus.ERROR:
            self._state = AgentState(
                agent_id=self._agent_id,
                status=AgentStatus.IDLE,
                current_action=None,
                error_message=None,
                metadata={},
            )

    def _generate_failure_reason(self, action_type: str) -> str:
        reasons = {
            "reach": ["object not found", "IK timeout", "path blocked"],
            "grasp": ["grasp slip", "object moved", "gripper malfunction"],
            "move": ["path collision", "joint limit reached"],
            "release": ["gripper stuck"],
            "home": ["joint limit reached"],
        }
        options = reasons.get(action_type, ["unknown failure"])
        return self._rng.choice(options)
