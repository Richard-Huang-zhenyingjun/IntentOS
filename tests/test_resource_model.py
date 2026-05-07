"""Tests for 3D resource model types."""

from src.task_graph import ResourceClaim, ResourceRegistry, SpatialEnvelope


def claim(
    node_id,
    named_resources=None,
    spatial_zone=None,
    envelope=None,
):
    return ResourceClaim(
        agent_id="arm",
        node_id=node_id,
        named_resources=frozenset(named_resources or []),
        spatial_zone=spatial_zone,
        spatial_envelope=envelope,
    )


def test_spatial_envelope_intersects_when_overlapping():
    a = SpatialEnvelope(0.0, 1.0, 0.0, 1.0, 0.0, 1.0)
    b = SpatialEnvelope(0.5, 1.5, 0.5, 1.5, 0.5, 1.5)

    assert a.intersects(b)
    assert b.intersects(a)


def test_spatial_envelope_does_not_intersect_when_separated():
    a = SpatialEnvelope(0.0, 1.0, 0.0, 1.0, 0.0, 1.0)
    b = SpatialEnvelope(1.1, 2.0, 0.0, 1.0, 0.0, 1.0)

    assert not a.intersects(b)
    assert not b.intersects(a)


def test_spatial_envelope_touching_edges_do_not_intersect():
    a = SpatialEnvelope(0.0, 1.0, 0.0, 1.0, 0.0, 1.0)
    b = SpatialEnvelope(1.0, 2.0, 0.0, 1.0, 0.0, 1.0)

    assert not a.intersects(b)


def test_resource_registry_rejects_named_resource_conflict():
    registry = ResourceRegistry()

    assert registry.claim(claim("n1", named_resources={"object:red_block"}))
    assert not registry.claim(claim("n2", named_resources={"object:red_block"}))


def test_resource_registry_rejects_spatial_zone_conflict():
    registry = ResourceRegistry()

    assert registry.claim(claim("n1", spatial_zone="zone_A"))
    assert not registry.claim(claim("n2", spatial_zone="zone_A"))


def test_resource_registry_rejects_spatial_envelope_conflict():
    registry = ResourceRegistry()
    envelope_a = SpatialEnvelope(0.0, 1.0, 0.0, 1.0, 0.0, 1.0)
    envelope_b = SpatialEnvelope(0.5, 1.5, 0.5, 1.5, 0.5, 1.5)

    assert registry.claim(claim("n1", envelope=envelope_a))
    assert not registry.claim(claim("n2", envelope=envelope_b))


def test_resource_registry_allows_non_conflicting_claims():
    registry = ResourceRegistry()

    assert registry.claim(
        claim(
            "n1",
            named_resources={"object:red_block"},
            spatial_zone="zone_A",
            envelope=SpatialEnvelope(0.0, 1.0, 0.0, 1.0, 0.0, 1.0),
        )
    )
    assert registry.claim(
        claim(
            "n2",
            named_resources={"object:blue_block"},
            spatial_zone="zone_B",
            envelope=SpatialEnvelope(2.0, 3.0, 2.0, 3.0, 0.0, 1.0),
        )
    )


def test_resource_registry_release_frees_claim():
    registry = ResourceRegistry()

    assert registry.claim(claim("n1", named_resources={"object:red_block"}))
    assert registry.is_claimed("object:red_block")

    registry.release("n1")

    assert not registry.is_claimed("object:red_block")
    assert registry.claim(claim("n2", named_resources={"object:red_block"}))


def test_resource_registry_active_node_ids_tracks_claims():
    registry = ResourceRegistry()

    registry.claim(claim("n1", named_resources={"object:red_block"}))
    registry.claim(claim("n2", named_resources={"object:blue_block"}))

    assert registry.active_node_ids() == ["n1", "n2"]
