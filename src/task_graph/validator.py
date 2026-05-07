"""
TaskGraph structural validator.

Validates graph structure only: no LLM calls, no world model, no execution.
Runs fast and returns violations before any plan reaches the kernel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol

from .types import TaskGraph


class AgentLookup(Protocol):
    def __contains__(self, agent_id: str) -> bool:
        ...

    def all_ids(self) -> list[str]:
        ...


@dataclass(frozen=True)
class Violation:
    rule: str
    node_id: Optional[str]
    message: str


@dataclass(frozen=True)
class ValidationResult:
    """Compatibility result for earlier 3A call sites."""

    ok: bool
    issues: tuple[Violation, ...] = field(default_factory=tuple)
    topological_order: tuple[str, ...] = field(default_factory=tuple)


ValidationIssue = Violation


def validate(graph: TaskGraph, registered_agent_ids: set[str]) -> list[Violation]:
    """
    Run all structural validation rules.
    Returns list of Violations. Empty means valid.
    """
    violations: list[Violation] = []

    violations.extend(_check_no_empty_graph(graph))
    violations.extend(_check_node_ids_unique(graph))
    violations.extend(_check_all_deps_exist(graph))
    violations.extend(_check_no_cycles(graph))
    violations.extend(_check_all_agents_registered(graph, registered_agent_ids))

    return violations


def validate_task_graph(
    graph: TaskGraph,
    agent_registry: AgentLookup | None = None,
) -> ValidationResult:
    """Compatibility wrapper around validate()."""
    registered_agent_ids = _registered_agent_ids(graph, agent_registry)
    violations = [_legacy_violation(v) for v in validate(graph, registered_agent_ids)]
    order = _topological_order(graph) if not any(v.rule == "cycle" for v in violations) else []

    return ValidationResult(
        ok=not violations,
        issues=tuple(violations),
        topological_order=tuple(order),
    )


def _check_no_cycles(graph: TaskGraph) -> list[Violation]:
    """Topological sort. A graph has a cycle if not all nodes are reachable."""
    node_ids = {n.node_id for n in graph.nodes}
    in_deg: dict[str, int] = {
        n.node_id: sum(1 for dep in n.depends_on if dep in node_ids)
        for n in graph.nodes
    }
    adj: dict[str, list[str]] = {n.node_id: [] for n in graph.nodes}

    for node in graph.nodes:
        for dep in node.depends_on:
            if dep in adj:
                adj[dep].append(node.node_id)

    queue = [nid for nid, deg in in_deg.items() if deg == 0]
    count = 0

    while queue:
        nid = queue.pop(0)
        count += 1
        for neighbor in adj.get(nid, []):
            in_deg[neighbor] -= 1
            if in_deg[neighbor] == 0:
                queue.append(neighbor)

    if count != len(graph.nodes):
        return [
            Violation(
                rule="no_cycles",
                node_id=None,
                message=(
                    f"Cycle detected in task graph - {len(graph.nodes) - count} "
                    "node(s) unreachable due to circular dependencies"
                ),
            )
        ]
    return []


def _check_all_deps_exist(graph: TaskGraph) -> list[Violation]:
    """All dependency node_ids must exist in the graph."""
    node_ids = {n.node_id for n in graph.nodes}
    violations: list[Violation] = []

    for node in graph.nodes:
        for dep in node.depends_on:
            if dep not in node_ids:
                violations.append(
                    Violation(
                        rule="deps_exist",
                        node_id=node.node_id,
                        message=f"Dependency {dep!r} not found in graph",
                    )
                )
    return violations


def _check_all_agents_registered(
    graph: TaskGraph,
    registered_agent_ids: set[str],
) -> list[Violation]:
    """All agent_ids in graph must be registered."""
    violations: list[Violation] = []

    for node in graph.nodes:
        if node.agent_id not in registered_agent_ids:
            violations.append(
                Violation(
                    rule="agents_registered",
                    node_id=node.node_id,
                    message=(
                        f"Agent {node.agent_id!r} not in registry. "
                        f"Registered: {sorted(registered_agent_ids)}"
                    ),
                )
            )
    return violations


def _check_no_empty_graph(graph: TaskGraph) -> list[Violation]:
    if not graph.nodes:
        return [
            Violation(
                rule="no_empty_graph",
                node_id=None,
                message="TaskGraph has no nodes",
            )
        ]
    return []


def _check_node_ids_unique(graph: TaskGraph) -> list[Violation]:
    seen: set[str] = set()
    violations: list[Violation] = []

    for node in graph.nodes:
        if node.node_id in seen:
            violations.append(
                Violation(
                    rule="unique_node_ids",
                    node_id=node.node_id,
                    message=f"Duplicate node_id: {node.node_id!r}",
                )
            )
        seen.add(node.node_id)
    return violations


def _topological_order(graph: TaskGraph) -> list[str]:
    node_ids = {n.node_id for n in graph.nodes}
    in_deg: dict[str, int] = {
        n.node_id: sum(1 for dep in n.depends_on if dep in node_ids)
        for n in graph.nodes
    }
    adj: dict[str, list[str]] = {n.node_id: [] for n in graph.nodes}

    for node in graph.nodes:
        for dep in node.depends_on:
            if dep in adj:
                adj[dep].append(node.node_id)

    queue = sorted(nid for nid, deg in in_deg.items() if deg == 0)
    order: list[str] = []

    while queue:
        nid = queue.pop(0)
        order.append(nid)
        for neighbor in sorted(adj.get(nid, [])):
            in_deg[neighbor] -= 1
            if in_deg[neighbor] == 0:
                queue.append(neighbor)
                queue.sort()

    return order


def _registered_agent_ids(graph: TaskGraph, agent_registry: AgentLookup | None) -> set[str]:
    if agent_registry is None:
        return {node.agent_id for node in graph.nodes}
    if hasattr(agent_registry, "all_ids"):
        return set(agent_registry.all_ids())
    return set()


def _legacy_violation(violation: Violation) -> Violation:
    rule_map = {
        "no_cycles": "cycle",
        "deps_exist": "missing_dependency",
        "agents_registered": "unknown_agent_id",
        "no_empty_graph": "empty_graph",
        "unique_node_ids": "duplicate_node_id",
    }
    mapped = rule_map.get(violation.rule, violation.rule)
    return Violation(
        rule=mapped,
        node_id=violation.node_id,
        message=violation.message,
    )
