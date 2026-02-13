"""
End-to-end test: Scene -> OpenVLA proposes -> registry returns proposal.

Run: pytest tests/test_openvla_proposal_flow.py -v
"""
from __future__ import annotations

import json

from src.external.openvla.adapter_fake import FakeOpenVLAAdapter
from src.external.openvla.proposer_openvla import OpenVLAProposer
from src.intelligence.proposer_heuristic import HeuristicProposer
from src.intelligence.proposer_registry import ProposerRegistry
from src.interfaces.scene_summary import ObjectInfo, SceneSummary


def _make_scene(object_specs: list[tuple[int, str]]) -> SceneSummary:
    objects = tuple(
        ObjectInfo(
            object_id=obj_id,
            pos_xyz=(0.35 + i * 0.05, -0.1 + i * 0.05, 0.4),
            on_table=True,
            category=category,
            confidence=1.0,
        )
        for i, (obj_id, category) in enumerate(object_specs)
    )
    return SceneSummary(
        table_id=1,
        table_position=(0.0, 0.0, 0.3),
        bin_zone_center=(0.4, 0.0, 0.75),
        bin_zone_radius=0.12,
        objects=objects,
        objects_on_table=objects,
        clutter_score=0.8 if objects else 0.0,
        is_messy=bool(objects),
        timestamp_frame=1,
        rgb_snapshot=None,
        eeg_quality=None,
    )


class TestEndToEndProposalFlow:
    def _create_registry(self) -> ProposerRegistry:
        registry = ProposerRegistry()

        adapter = FakeOpenVLAAdapter()
        adapter.load_model()
        openvla = OpenVLAProposer(adapter, priority=15, enabled=True)
        registry.register("openvla", openvla, priority=15)

        heuristic = HeuristicProposer(config={})
        registry.register("heuristic", heuristic, priority=0, is_fallback=True)
        return registry

    def _create_scene(self) -> SceneSummary:
        return _make_scene([(4, "red_cube"), (5, "green_cube"), (6, "blue_cube")])

    def test_registry_produces_openvla_proposal(self):
        registry = self._create_registry()
        scene = self._create_scene()
        proposal = registry.propose(scene)

        assert proposal is not None
        assert proposal.source == "openvla"
        meta = proposal.metadata
        assert meta.get("primitive_type") == "openvla_trajectory"
        assert "delta_position" in meta
        assert "gripper" in meta
        assert len(meta["raw_action"]) == 7

    def test_proposal_contains_instruction(self):
        registry = self._create_registry()
        scene = self._create_scene()
        proposal = registry.propose(scene)

        instruction = proposal.metadata.get("instruction", "")
        assert len(instruction) > 0
        assert any(k in instruction.lower() for k in ["pick", "object", "bin"])

    def test_multiple_proposals_from_same_scene(self):
        registry = self._create_registry()
        scene = self._create_scene()
        proposals = [registry.propose(scene) for _ in range(5)]
        assert all(p is not None for p in proposals)
        assert all(p.source == "openvla" for p in proposals)

    def test_proposal_for_different_scenes(self):
        registry = self._create_registry()
        scenes = [
            _make_scene([(10, "cup")]),
            _make_scene([(11, "plate")]),
            _make_scene([(12, "bottle")]),
        ]
        for scene in scenes:
            proposal = registry.propose(scene)
            assert proposal is not None
            assert proposal.source == "openvla"

    def test_empty_scene_handled(self):
        registry = self._create_registry()
        scene = _make_scene([])
        proposal = registry.propose(scene)
        assert proposal is not None
        assert proposal.source == "heuristic"


class TestProposalDataIntegrity:
    def _get_proposal(self):
        registry = ProposerRegistry()
        adapter = FakeOpenVLAAdapter()
        adapter.load_model()
        openvla = OpenVLAProposer(adapter, priority=15, enabled=True)
        registry.register("openvla", openvla, priority=15)
        registry.register("heuristic", HeuristicProposer(config={}), priority=0, is_fallback=True)
        scene = _make_scene([(21, "red_cube")])
        return registry.propose(scene)

    def test_delta_position_is_3d(self):
        proposal = self._get_proposal()
        assert len(proposal.metadata["delta_position"]) == 3

    def test_delta_rotation_is_3d(self):
        proposal = self._get_proposal()
        assert len(proposal.metadata["delta_rotation"]) == 3

    def test_gripper_is_scalar(self):
        proposal = self._get_proposal()
        g = proposal.metadata["gripper"]
        assert isinstance(g, (int, float))
        assert 0.0 <= g <= 1.0

    def test_raw_action_is_7d(self):
        proposal = self._get_proposal()
        assert len(proposal.metadata["raw_action"]) == 7

    def test_no_numpy_in_metadata(self):
        proposal = self._get_proposal()
        json.dumps(proposal.metadata)
