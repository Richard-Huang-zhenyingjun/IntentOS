"""
Tests for OpenVLA proposer integration with the intent system.

Run: pytest tests/test_openvla_proposer.py -v
"""
from __future__ import annotations

import numpy as np
import pytest

from src.external.openvla.adapter_fake import FakeOpenVLAAdapter
from src.external.openvla.proposer_openvla import OpenVLAProposer
from src.interfaces.intent_proposal import ActionType, IntentProposal
from src.interfaces.scene_summary import ObjectInfo, SceneSummary


@pytest.fixture
def fake_adapter():
    adapter = FakeOpenVLAAdapter()
    adapter.load_model()
    return adapter


@pytest.fixture
def proposer(fake_adapter):
    return OpenVLAProposer(
        openvla_adapter=fake_adapter,
        camera_provider=None,
        priority=15,
        enabled=True,
    )


def _make_scene(objects: tuple[ObjectInfo, ...], frame: int = 1) -> SceneSummary:
    return SceneSummary(
        table_id=1,
        table_position=(0.0, 0.0, 0.3),
        bin_zone_center=(0.5, 0.4, 0.4),
        bin_zone_radius=0.1,
        objects=objects,
        objects_on_table=objects,
        clutter_score=0.8 if objects else 0.0,
        is_messy=bool(objects),
        timestamp_frame=frame,
        rgb_snapshot=None,
        eeg_quality=None,
    )


@pytest.fixture
def scene_with_objects():
    objs = (
        ObjectInfo(object_id=3, pos_xyz=(0.4, -0.1, 0.4), on_table=True, category="cube"),
        ObjectInfo(object_id=7, pos_xyz=(0.55, 0.05, 0.4), on_table=True, category="cube"),
    )
    return _make_scene(objs)


@pytest.fixture
def empty_scene():
    return _make_scene(tuple())


class TestProposerInterface:
    def test_has_name(self, proposer):
        assert proposer.name() == "openvla"

    def test_has_priority(self, proposer):
        assert proposer.priority == 15

    def test_priority_higher_than_gemini(self, proposer):
        assert proposer.priority > 10

    def test_is_available_when_loaded(self, proposer):
        assert proposer.is_available() is True

    def test_not_available_when_disabled(self, fake_adapter):
        p = OpenVLAProposer(fake_adapter, enabled=False)
        assert p.is_available() is False

    def test_not_available_when_model_not_loaded(self):
        adapter = FakeOpenVLAAdapter()
        p = OpenVLAProposer(adapter, enabled=True)
        assert p.is_available() is False

    def test_propose_returns_intent_proposal(self, proposer, scene_with_objects):
        result = proposer.propose(scene_with_objects)
        assert isinstance(result, IntentProposal)


class TestProposalGeneration:
    def test_proposes_for_scene_with_objects(self, proposer, scene_with_objects):
        proposal = proposer.propose(scene_with_objects)
        assert proposal.action == ActionType.CLEAN_TABLE
        assert proposal.confidence > 0.0

    def test_empty_scene_returns_fallback_signal(self, proposer, empty_scene):
        proposal = proposer.propose(empty_scene)
        assert proposal.action == ActionType.IDLE
        assert proposal.confidence == 0.0

    def test_proposal_has_description(self, proposer, scene_with_objects):
        proposal = proposer.propose(scene_with_objects)
        assert "OpenVLA" in proposal.description

    def test_proposal_metadata_contains_action(self, proposer, scene_with_objects):
        proposal = proposer.propose(scene_with_objects)
        meta = proposal.metadata
        assert "delta_position" in meta
        assert "gripper" in meta
        assert "raw_action" in meta
        assert meta["primitive_type"] == "openvla_trajectory"

    def test_proposal_metadata_action_is_list(self, proposer, scene_with_objects):
        proposal = proposer.propose(scene_with_objects)
        meta = proposal.metadata
        assert isinstance(meta["delta_position"], list)
        assert isinstance(meta["raw_action"], list)
        assert len(meta["raw_action"]) == 7

    def test_multiple_proposals_increment_count(self, proposer, scene_with_objects):
        assert proposer.proposal_count == 0
        proposer.propose(scene_with_objects)
        proposer.propose(scene_with_objects)
        assert proposer.proposal_count == 2


class TestFailureHandling:
    def test_adapter_failure_returns_fallback_signal(self, scene_with_objects):
        class CrashingAdapter:
            is_loaded = True

            def predict(self, instruction, image):
                raise RuntimeError("GPU out of memory")

        proposer = OpenVLAProposer(CrashingAdapter(), enabled=True)
        result = proposer.propose(scene_with_objects)
        assert result.action == ActionType.IDLE
        assert result.confidence == 0.0
        assert proposer.failure_count == 1

    def test_camera_failure_uses_blank_image(self, fake_adapter, scene_with_objects):
        class BrokenCamera:
            def render_camera(self, name=""):
                raise RuntimeError("Render failed")

        proposer = OpenVLAProposer(
            fake_adapter, camera_provider=BrokenCamera(), enabled=True
        )
        result = proposer.propose(scene_with_objects)
        assert result.action == ActionType.CLEAN_TABLE

    def test_stats_track_failures(self, scene_with_objects):
        class FailingAdapter:
            is_loaded = True

            def predict(self, instruction, image):
                raise ValueError("bad input")

        proposer = OpenVLAProposer(FailingAdapter(), enabled=True)
        proposer.propose(scene_with_objects)
        proposer.propose(scene_with_objects)
        stats = proposer.stats
        assert stats["failures"] == 2
        assert stats["proposals"] == 0
        assert stats["success_rate"] == 0.0


class TestCameraIntegration:
    def test_uses_provided_camera(self, fake_adapter, scene_with_objects):
        call_log = []

        class MockCamera:
            def render_camera(self, name=""):
                call_log.append(name)
                return np.zeros((480, 640, 3), dtype=np.uint8)

        proposer = OpenVLAProposer(
            fake_adapter,
            camera_provider=MockCamera(),
            camera_name="overhead",
            enabled=True,
        )
        proposer.propose(scene_with_objects)
        assert "overhead" in call_log

    def test_uses_scene_snapshot_before_camera(self, fake_adapter):
        call_log = []

        class MockCamera:
            def render_camera(self, name=""):
                call_log.append(name)
                return np.zeros((480, 640, 3), dtype=np.uint8)

        scene = _make_scene(
            (
                ObjectInfo(
                    object_id=11, pos_xyz=(0.4, 0.0, 0.4), on_table=True, category="cube"
                ),
            )
        )
        scene = SceneSummary(
            **{
                **scene.__dict__,
                "rgb_snapshot": np.ones((224, 224, 3), dtype=np.uint8) * 123,
            }
        )

        proposer = OpenVLAProposer(
            fake_adapter, camera_provider=MockCamera(), enabled=True
        )
        result = proposer.propose(scene)
        assert result.action == ActionType.CLEAN_TABLE
        assert call_log == []

    def test_no_camera_uses_blank(self, fake_adapter, scene_with_objects):
        proposer = OpenVLAProposer(fake_adapter, camera_provider=None, enabled=True)
        result = proposer.propose(scene_with_objects)
        assert result.action == ActionType.CLEAN_TABLE


class TestActionTracking:
    def test_last_action_initially_none(self, proposer):
        assert proposer.last_action is None

    def test_last_action_updated_after_proposal(self, proposer, scene_with_objects):
        proposer.propose(scene_with_objects)
        assert proposer.last_action is not None
        assert proposer.last_action.instruction != ""
