"""Tests for TaskGraph types and validator."""
import time
import uuid

from src.task_graph import (
    ResourceClaim,
    ResourceRegistry,
    SpatialEnvelope,
    TaskGraph,
    TaskNode,
    TaskStatus,
    UncertaintySignals,
    validate,
)


def make_node(node_id, agent_id="arm", depends_on=None, action="reach"):
    return TaskNode(
        node_id=node_id,
        action_type=action,
        agent_id=agent_id,
        parameters={},
        depends_on=depends_on or [],
    )


def make_graph(nodes, goal="test goal"):
    return TaskGraph(
        graph_id=str(uuid.uuid4())[:8],
        goal=goal,
        nodes=nodes,
        created_at=time.time(),
    )


REGISTERED = {"arm"}


class TestValidator:
    def test_valid_linear_graph_passes(self):
        nodes = [
            make_node("n1"),
            make_node("n2", depends_on=["n1"]),
            make_node("n3", depends_on=["n2"]),
        ]
        assert validate(make_graph(nodes), REGISTERED) == []

    def test_cycle_detected(self):
        nodes = [
            make_node("n1", depends_on=["n2"]),
            make_node("n2", depends_on=["n1"]),
        ]
        violations = validate(make_graph(nodes), REGISTERED)
        assert any(v.rule == "no_cycles" for v in violations)

    def test_missing_dependency_detected(self):
        nodes = [make_node("n1", depends_on=["ghost_node"])]
        violations = validate(make_graph(nodes), REGISTERED)
        assert any(v.rule == "deps_exist" for v in violations)

    def test_unknown_agent_detected(self):
        nodes = [make_node("n1", agent_id="drone")]
        violations = validate(make_graph(nodes), REGISTERED)
        assert any(v.rule == "agents_registered" for v in violations)

    def test_empty_graph_rejected(self):
        violations = validate(make_graph([]), REGISTERED)
        assert any(v.rule == "no_empty_graph" for v in violations)

    def test_duplicate_node_ids_rejected(self):
        nodes = [make_node("n1"), make_node("n1")]
        violations = validate(make_graph(nodes), REGISTERED)
        assert any(v.rule == "unique_node_ids" for v in violations)


class TestTaskGraphMethods:
    def test_ready_nodes_returns_pending_with_satisfied_deps(self):
        n1 = make_node("n1")
        n2 = make_node("n2", depends_on=["n1"])
        n1.status = TaskStatus.DONE
        graph = make_graph([n1, n2])

        ready = graph.ready_nodes()

        assert len(ready) == 1
        assert ready[0].node_id == "n2"

    def test_ready_nodes_excludes_nodes_with_pending_deps(self):
        n1 = make_node("n1")
        n2 = make_node("n2", depends_on=["n1"])
        graph = make_graph([n1, n2])

        assert graph.ready_nodes() == [n1]

    def test_is_complete_when_all_terminal(self):
        n1 = make_node("n1")
        n1.status = TaskStatus.DONE
        assert make_graph([n1]).is_complete()

    def test_has_failures_detects_failed_node(self):
        n1 = make_node("n1")
        n1.status = TaskStatus.FAILED
        assert make_graph([n1]).has_failures()


class TestUncertaintySignals:
    def test_combined_is_between_zero_and_one(self):
        u = UncertaintySignals(
            perception_confidence=0.8,
            execution_history_rate=0.9,
            simulation_risk=0.1,
        )
        assert 0.0 <= u.combined <= 1.0

    def test_high_uncertainty_when_all_low(self):
        u = UncertaintySignals(
            perception_confidence=0.0,
            execution_history_rate=0.0,
            simulation_risk=1.0,
        )
        assert u.combined > 0.8

    def test_low_uncertainty_when_all_high_confidence(self):
        u = UncertaintySignals(
            perception_confidence=1.0,
            execution_history_rate=1.0,
            simulation_risk=0.0,
        )
        assert u.combined < 0.1


class TestSpatialEnvelope:
    def test_overlapping_envelopes_intersect(self):
        a = SpatialEnvelope(0, 1, 0, 1, 0, 1)
        b = SpatialEnvelope(0.5, 1.5, 0.5, 1.5, 0.5, 1.5)
        assert a.intersects(b)
        assert b.intersects(a)

    def test_non_overlapping_envelopes_do_not_intersect(self):
        a = SpatialEnvelope(0, 1, 0, 1, 0, 1)
        b = SpatialEnvelope(2, 3, 2, 3, 2, 3)
        assert not a.intersects(b)

    def test_touching_envelopes_do_not_intersect(self):
        a = SpatialEnvelope(0, 1, 0, 1, 0, 1)
        b = SpatialEnvelope(1, 2, 0, 1, 0, 1)
        assert not a.intersects(b)


class TestResourceRegistry:
    def test_first_claim_succeeds(self):
        reg = ResourceRegistry()
        claim = ResourceClaim(
            "arm",
            "n1",
            frozenset({"object:red_block"}),
            spatial_zone=None,
        )
        assert reg.claim(claim)

    def test_conflicting_named_resource_rejected(self):
        reg = ResourceRegistry()
        c1 = ResourceClaim(
            "arm",
            "n1",
            frozenset({"object:red_block"}),
            spatial_zone=None,
        )
        c2 = ResourceClaim(
            "sim",
            "n2",
            frozenset({"object:red_block"}),
            spatial_zone=None,
        )
        assert reg.claim(c1)
        assert not reg.claim(c2)

    def test_release_frees_resource(self):
        reg = ResourceRegistry()
        c1 = ResourceClaim(
            "arm",
            "n1",
            frozenset({"object:red_block"}),
            spatial_zone=None,
        )
        c2 = ResourceClaim(
            "sim",
            "n2",
            frozenset({"object:red_block"}),
            spatial_zone=None,
        )
        reg.claim(c1)
        reg.release("n1")
        assert reg.claim(c2)

    def test_zone_conflict_rejected(self):
        reg = ResourceRegistry()
        c1 = ResourceClaim("arm", "n1", frozenset(), spatial_zone="zone_A")
        c2 = ResourceClaim("sim", "n2", frozenset(), spatial_zone="zone_A")
        assert reg.claim(c1)
        assert not reg.claim(c2)
