"""
Tests for OpenVLA adapter (using fake adapter for CI).

Run: pytest tests/test_openvla_adapter.py -v
"""
import numpy as np
import pytest

from src.external.openvla.adapter import OpenVLAAction
from src.external.openvla.adapter_fake import FakeOpenVLAAdapter


@pytest.fixture
def adapter():
    a = FakeOpenVLAAdapter()
    a.load_model()
    return a


@pytest.fixture
def test_image():
    return np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)


class TestOpenVLAAction:
    def test_action_fields(self):
        action = OpenVLAAction(
            delta_position=np.array([0.01, 0.0, -0.02]),
            delta_rotation=np.array([0.0, 0.0, 0.0]),
            gripper=0.0,
            raw_action=np.array([0.01, 0.0, -0.02, 0.0, 0.0, 0.0, 0.0]),
            instruction="pick up the cup",
        )
        assert action.delta_position.shape == (3,)
        assert action.delta_rotation.shape == (3,)
        assert action.raw_action.shape == (7,)
        assert action.gripper == 0.0
        assert action.instruction == "pick up the cup"


class TestFakeAdapter:
    def test_loads(self, adapter):
        assert adapter.is_loaded

    def test_not_loaded_raises(self):
        a = FakeOpenVLAAdapter()
        with pytest.raises(AssertionError):
            a.predict("pick up", np.zeros((224, 224, 3), dtype=np.uint8))

    def test_predict_returns_action(self, adapter, test_image):
        action = adapter.predict("pick up the red block", test_image)
        assert isinstance(action, OpenVLAAction)
        assert action.raw_action.shape == (7,)

    def test_pick_instruction_closes_gripper(self, adapter, test_image):
        action = adapter.predict("pick up the block", test_image)
        assert action.gripper < 0.5, "Pick should close gripper"

    def test_place_instruction_opens_gripper(self, adapter, test_image):
        action = adapter.predict("place the block in the bin", test_image)
        assert action.gripper > 0.5, "Place should open gripper"

    def test_action_dimensions(self, adapter, test_image):
        action = adapter.predict("move forward", test_image)
        assert adapter.action_dim == 7
        assert len(action.raw_action) == 7

    def test_no_nan_in_output(self, adapter, test_image):
        for instruction in ["pick up", "place down", "move left", "wipe table"]:
            action = adapter.predict(instruction, test_image)
            assert not np.any(np.isnan(action.raw_action))

    def test_batch_predict(self, adapter, test_image):
        images = [test_image] * 5
        actions = adapter.predict_batch("pick up the block", images)
        assert len(actions) == 5
        assert all(isinstance(a, OpenVLAAction) for a in actions)

    def test_call_count_tracks(self, adapter, test_image):
        assert adapter.call_count == 0
        adapter.predict("test", test_image)
        adapter.predict("test", test_image)
        assert adapter.call_count == 2

    def test_close_resets_state(self, adapter):
        adapter.close()
        assert not adapter.is_loaded
