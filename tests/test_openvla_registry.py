"""
Tests for OpenVLA integration with ProposerRegistry.

Run: pytest tests/test_openvla_registry.py -v
"""
from __future__ import annotations

import pytest

from src.external.openvla.adapter_fake import FakeOpenVLAAdapter
from src.external.openvla.proposer_openvla import OpenVLAProposer
from src.intelligence.proposer_heuristic import HeuristicProposer
from src.intelligence.proposer_registry import ProposerRegistry
from src.interfaces.intent_proposal import ActionType
from src.interfaces.scene_summary import ObjectInfo, SceneSummary


def _make_scene() -> SceneSummary:
    obj = ObjectInfo(
        object_id=4,
        pos_xyz=(0.4, -0.1, 0.4),
        on_table=True,
        category="cube",
        confidence=1.0,
    )
    return SceneSummary(
        table_id=1,
        table_position=(0.0, 0.0, 0.3),
        bin_zone_center=(0.4, 0.0, 0.75),
        bin_zone_radius=0.12,
        objects=(obj,),
        objects_on_table=(obj,),
        clutter_score=0.8,
        is_messy=True,
        timestamp_frame=1,
        rgb_snapshot=None,
        eeg_quality=None,
    )


@pytest.fixture
def test_scene():
    return _make_scene()


@pytest.fixture
def registry_with_openvla():
    registry = ProposerRegistry()

    adapter = FakeOpenVLAAdapter()
    adapter.load_model()
    openvla = OpenVLAProposer(adapter, priority=15, enabled=True, camera_provider=None)
    registry.register("openvla", openvla, priority=15)

    heuristic = HeuristicProposer(config={})
    registry.register("heuristic", heuristic, priority=0, is_fallback=True)

    return registry


class TestRegistryIntegration:
    def test_openvla_registered(self, registry_with_openvla):
        stats = registry_with_openvla.get_stats()
        assert "openvla" in stats["registered_proposers"]

    def test_openvla_highest_priority(self, registry_with_openvla):
        assert registry_with_openvla.get_active_proposer_name() == "openvla"

    def test_registry_returns_openvla_proposal(self, registry_with_openvla, test_scene):
        proposal = registry_with_openvla.propose(test_scene)
        assert proposal is not None
        assert proposal.source == "openvla"
        assert proposal.metadata.get("primitive_type") == "openvla_trajectory"

    def test_fallback_to_heuristic_when_openvla_disabled(self, test_scene):
        registry = ProposerRegistry()

        adapter = FakeOpenVLAAdapter()
        adapter.load_model()
        openvla = OpenVLAProposer(adapter, priority=15, enabled=False, camera_provider=None)
        registry.register("openvla", openvla, priority=15)

        heuristic = HeuristicProposer(config={})
        registry.register("heuristic", heuristic, priority=0, is_fallback=True)

        proposal = registry.propose(test_scene)
        assert proposal is not None
        assert proposal.source == "heuristic"
        assert proposal.action == ActionType.CLEAN_TABLE

    def test_fallback_to_heuristic_when_openvla_crashes(self, test_scene):
        class CrashingAdapter:
            is_loaded = True

            def predict(self, instruction, image):
                raise RuntimeError("CUDA error")

        registry = ProposerRegistry()
        openvla = OpenVLAProposer(CrashingAdapter(), priority=15, enabled=True, camera_provider=None)
        registry.register("openvla", openvla, priority=15)

        heuristic = HeuristicProposer(config={})
        registry.register("heuristic", heuristic, priority=0, is_fallback=True)

        proposal = registry.propose(test_scene)
        assert proposal is not None
        assert proposal.source == "heuristic"


class TestRegistryOrdering:
    def test_three_proposer_priority_chain(self, test_scene):
        registry = ProposerRegistry()

        adapter = FakeOpenVLAAdapter()
        adapter.load_model()
        openvla = OpenVLAProposer(adapter, priority=15, enabled=True, camera_provider=None)
        registry.register("openvla", openvla, priority=15)

        # Placeholder for Gemini at priority 10 (not instantiated here).
        heuristic = HeuristicProposer(config={})
        registry.register("heuristic", heuristic, priority=0, is_fallback=True)

        proposal = registry.propose(test_scene)
        assert proposal is not None
        assert proposal.source == "openvla"
