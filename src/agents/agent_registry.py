"""
AgentRegistry - lookup agents by agent_id.
Used by TaskGraph validator and AgentCoordinator (added in 3B/3D).
"""
from __future__ import annotations

from typing import Optional

from .agent_base import AgentBase


class AgentRegistry:
    """
    Simple registry. Agents register at system startup via system_factory.
    Task graph nodes reference agents by agent_id string.
    """

    def __init__(self):
        self._agents: dict[str, AgentBase] = {}

    def register(self, agent: AgentBase) -> None:
        if agent.agent_id in self._agents:
            raise ValueError(f"Agent {agent.agent_id!r} already registered")
        self._agents[agent.agent_id] = agent

    def get(self, agent_id: str) -> Optional[AgentBase]:
        return self._agents.get(agent_id)

    def all_ids(self) -> list[str]:
        return list(self._agents.keys())

    def all_agents(self) -> list[AgentBase]:
        return list(self._agents.values())

    def __contains__(self, agent_id: str) -> bool:
        return agent_id in self._agents
