"""Tests for heuristic WorldModel."""
from src.task_graph import ResourceClaim, TaskGraph, TaskNode, UncertaintySignals
from src.world_model import WorldAssessment, WorldModel, WorldModelConfig


def make_graph(nodes):
    return TaskGraph(
        graph_id="g1",
        goal="test",
        nodes=nodes,
        created_at=0.0,
    )


def make_node(node_id="n1", target="red", action_type="reach", zone=None):
    claim = None
    if zone is not None:
        claim = ResourceClaim(
            agent_id="arm",
            node_id=node_id,
            named_resources=frozenset({f"zone:{zone}"}),
            spatial_zone=zone,
            estimated_duration_s=1.0,
        )
    return TaskNode(
        node_id=node_id,
        action_type=action_type,
        agent_id="arm",
        parameters={"target": target} if target is not None else {},
        resource_claim=claim,
        uncertainty=UncertaintySignals(
            perception_confidence=0.9,
            execution_history_rate=0.8,
            simulation_risk=0.1,
        ),
    )


def world_state(*objects):
    return {"objects": list(objects), "arm_base_position": [0, 0, 0]}


def obj(id_, position, visible=True):
    return {"id": id_, "position": position, "visible": visible}


def test_reachable_visible_node_has_low_world_risk():
    model = WorldModel(WorldModelConfig())
    graph = make_graph([make_node(target="red")])

    assessment = model.assess(
        graph,
        world_state(obj("red", [0.2, 0.1, 0.3], visible=True)),
    )

    risk = assessment.per_node["n1"]
    assert risk.simulation_risk == 0.0
    assert risk.reachable
    assert risk.object_visible
    assert assessment.overall_risk == 0.0


def test_unreachable_object_adds_risk_and_unreachable_node():
    cfg = WorldModelConfig(workspace_radius_m=0.5, unreachable_penalty=0.6)
    model = WorldModel(cfg)
    graph = make_graph([make_node(target="far")])

    assessment = model.assess(
        graph,
        world_state(obj("far", [1.0, 0.0, 0.3])),
    )

    risk = assessment.per_node["n1"]
    assert not risk.reachable
    assert risk.simulation_risk == 0.6
    assert assessment.unreachable_nodes == ["n1"]
    assert any("outside workspace" in note for note in risk.notes)


def test_invisible_object_adds_visibility_risk():
    model = WorldModel(WorldModelConfig(invisible_penalty=0.5))
    graph = make_graph([make_node(target="red")])

    assessment = model.assess(
        graph,
        world_state(obj("red", [0.2, 0.0, 0.3], visible=False)),
    )

    risk = assessment.per_node["n1"]
    assert not risk.object_visible
    assert risk.simulation_risk == 0.5
    assert any("not visible" in note for note in risk.notes)


def test_unreachable_and_invisible_risk_caps_at_one():
    model = WorldModel(
        WorldModelConfig(
            workspace_radius_m=0.2,
            unreachable_penalty=0.8,
            invisible_penalty=0.8,
        )
    )
    graph = make_graph([make_node(target="red")])

    assessment = model.assess(
        graph,
        world_state(obj("red", [1.0, 0.0, 0.3], visible=False)),
    )

    assert assessment.per_node["n1"].simulation_risk == 1.0


def test_spatial_zone_conflict_adds_warning_to_later_node():
    model = WorldModel(WorldModelConfig(spatial_conflict_penalty=0.4))
    graph = make_graph(
        [
            make_node("n1", zone="zone_A"),
            make_node("n2", zone="zone_A"),
        ]
    )

    assessment = model.assess(graph, world_state())

    assert not assessment.per_node["n1"].spatial_conflict
    assert assessment.per_node["n2"].spatial_conflict
    assert assessment.per_node["n2"].simulation_risk == 0.4
    assert assessment.collision_warnings == ["Nodes n1, n2 share zone zone_A"]


def test_irreversible_action_marked_not_reversible_without_extra_risk():
    model = WorldModel(WorldModelConfig())
    graph = make_graph([make_node(action_type="release")])

    assessment = model.assess(graph, world_state())

    risk = assessment.per_node["n1"]
    assert not risk.reversible
    assert risk.simulation_risk == 0.0
    assert any("irreversible" in note for note in risk.notes)


def test_missing_world_state_degrades_gracefully():
    model = WorldModel(WorldModelConfig())
    graph = make_graph([make_node(target="unknown")])

    assessment = model.assess(graph, None)

    assert isinstance(assessment, WorldAssessment)
    risk = assessment.per_node["n1"]
    assert risk.reachable
    assert risk.object_visible
    assert risk.simulation_risk == 0.0


def test_annotate_graph_replaces_simulation_risk_only():
    model = WorldModel(WorldModelConfig(workspace_radius_m=0.5, unreachable_penalty=0.6))
    node = make_node(target="far")
    graph = make_graph([node])

    model.annotate_graph(
        graph,
        world_state(obj("far", [1.0, 0.0, 0.3])),
    )

    assert node.uncertainty.perception_confidence == 0.9
    assert node.uncertainty.execution_history_rate == 0.8
    assert node.uncertainty.simulation_risk == 0.6


def test_overall_risk_is_max_of_nodes():
    model = WorldModel(WorldModelConfig(workspace_radius_m=0.5, unreachable_penalty=0.6))
    graph = make_graph(
        [
            make_node("n1", target="red"),
            make_node("n2", target="far"),
        ]
    )

    assessment = model.assess(
        graph,
        world_state(
            obj("red", [0.2, 0.0, 0.3]),
            obj("far", [1.0, 0.0, 0.3]),
        ),
    )

    expected_max = max(
        assessment.per_node["n1"].simulation_risk,
        assessment.per_node["n2"].simulation_risk,
    )
    assert abs(assessment.overall_risk - expected_max) < 0.01
