"""
Tests for camera -> OpenVLA proposer pipeline.

Run: pytest tests/test_openvla_camera_pipeline.py -v
"""
from __future__ import annotations

import os

import numpy as np
import pytest

from src.external.openvla.adapter_fake import FakeOpenVLAAdapter
from src.external.openvla.proposer_openvla import OpenVLAProposer
from src.interfaces.scene_summary import ObjectInfo, SceneSummary


class MockCamera:
    """Mock camera that returns a known image."""

    def __init__(self, color=(128, 64, 32)):
        self._color = color
        self.render_count = 0
        self.last_camera_name = None

    def render_camera(self, camera_name=""):
        self.render_count += 1
        self.last_camera_name = camera_name
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        img[:, :] = self._color
        return img


def _make_scene() -> SceneSummary:
    objects = (
        ObjectInfo(
            object_id=4,
            pos_xyz=(0.4, -0.1, 0.4),
            on_table=True,
            category="red_cube",
            confidence=1.0,
        ),
    )
    return SceneSummary(
        table_id=1,
        table_position=(0.0, 0.0, 0.3),
        bin_zone_center=(0.4, 0.0, 0.75),
        bin_zone_radius=0.12,
        objects=objects,
        objects_on_table=objects,
        clutter_score=0.8,
        is_messy=True,
        timestamp_frame=1,
        rgb_snapshot=None,
        eeg_quality=None,
    )


class TestCameraPipeline:
    def test_proposer_calls_camera(self):
        camera = MockCamera()
        adapter = FakeOpenVLAAdapter()
        adapter.load_model()
        proposer = OpenVLAProposer(
            adapter, camera_provider=camera, camera_name="overhead"
        )

        proposer.propose(_make_scene())
        assert camera.render_count == 1
        assert camera.last_camera_name == "overhead"

    def test_proposer_uses_configured_camera_name(self):
        camera = MockCamera()
        adapter = FakeOpenVLAAdapter()
        adapter.load_model()
        proposer = OpenVLAProposer(
            adapter, camera_provider=camera, camera_name="wrist"
        )

        proposer.propose(_make_scene())
        assert camera.last_camera_name == "wrist"

    def test_multiple_proposals_render_each_time(self):
        camera = MockCamera()
        adapter = FakeOpenVLAAdapter()
        adapter.load_model()
        proposer = OpenVLAProposer(adapter, camera_provider=camera)

        for _ in range(5):
            proposer.propose(_make_scene())
        assert camera.render_count == 5

    def test_camera_failure_doesnt_crash(self):
        class BrokenCamera:
            def render_camera(self, name=""):
                raise RuntimeError("GPU crash")

        adapter = FakeOpenVLAAdapter()
        adapter.load_model()
        proposer = OpenVLAProposer(
            adapter, camera_provider=BrokenCamera()
        )

        result = proposer.propose(_make_scene())
        assert result is not None

    def test_no_camera_uses_blank(self):
        adapter = FakeOpenVLAAdapter()
        adapter.load_model()
        proposer = OpenVLAProposer(adapter, camera_provider=None)

        result = proposer.propose(_make_scene())
        assert result is not None


class TestMuJoCoCameraIntegration:
    """
    Integration tests with real MuJoCo simulator.
    Skipped if MuJoCo/renderer/model are unavailable.
    """

    @pytest.fixture
    def mujoco_sim(self):
        try:
            from src.robot.mujoco.mujoco_simulator import MuJoCoSimulator, MuJoCoConfig
        except ImportError:
            pytest.skip("MuJoCo simulator not available")

        model_path = os.path.join("models", "kuka_iiwa", "messy_table.xml")
        if not os.path.exists(model_path):
            pytest.skip(f"Model not found: {model_path}")

        config = MuJoCoConfig(model_path=model_path, use_gui=False)
        sim = MuJoCoSimulator(config)
        sim.load_robot()
        try:
            _ = sim.render_camera("overhead")
        except Exception as exc:
            sim.close()
            pytest.skip(f"Renderer unavailable: {exc}")
        yield sim
        sim.close()

    def test_mujoco_renders_for_proposer(self, mujoco_sim):
        adapter = FakeOpenVLAAdapter()
        adapter.load_model()
        proposer = OpenVLAProposer(
            adapter, camera_provider=mujoco_sim, camera_name="overhead"
        )

        result = proposer.propose(_make_scene())
        assert result is not None

    def test_different_cameras_different_images(self, mujoco_sim):
        img1 = mujoco_sim.render_camera("overhead")
        img2 = mujoco_sim.render_camera("front")
        assert not np.array_equal(img1, img2)
