"""Stress/repeatability tests across seeds."""

import numpy as np
import pytest
import pybullet as p

from src.core.system_factory import build_system, load_config
from src.input.filter import DecisionFilter
from src.input.pipeline import DecisionPipeline
from src.input.policies import DecisionPolicy
from src.input.router import DecisionRouter
from src.input.source_fake import FakeSource
from src.robot.simulator import RobotSimulator
from src.worlds.messy_table_world import build_messy_table


def _make_headless_config(seed: int) -> dict:
    config = load_config("configs/default.yaml")
    config.setdefault("simulator", {})
    config["simulator"]["use_gui"] = False
    config.setdefault("gemini", {})
    config["gemini"]["enabled"] = False
    config.setdefault("eeg", {})
    config["eeg"]["enabled"] = False
    config.setdefault("logging", {})
    config["logging"]["events_enabled"] = False
    config.setdefault("world", {})
    config["world"].setdefault("messy_table", {})
    config["world"]["messy_table"]["seed"] = seed
    return config


def _inject_fake_confirms(orch, config: dict):
    test_cfg = dict(config)
    test_cfg["input"] = dict(config.get("input", {}))
    test_cfg["input"]["mode"] = "KEYBOARD_ONLY"
    test_cfg["input"]["sources_enabled"] = ["keyboard"]
    test_cfg["input"]["debounce_frames"] = 0
    test_cfg["input"]["confirm_hold_frames"] = 1
    test_cfg["input"]["min_quality"] = 0.0

    policy = DecisionPolicy.from_config(test_cfg)
    router = DecisionRouter(policy)
    source = FakeSource()
    source.set_confirm_on_frame(5)
    source.set_confirm_on_frame(15)
    router.register_source("keyboard", source)
    orch.decision_pipeline = DecisionPipeline(router, DecisionFilter(test_cfg))


@pytest.mark.parametrize("seed", [42, 123, 999, 7777, 31337])
def test_multiple_seeds_complete_without_crash(seed):
    """System handles varied seeds without crashes and without false execution."""
    config = _make_headless_config(seed)
    orch = build_system(config)
    try:
        _inject_fake_confirms(orch, config)
        snapshot = None
        for _ in range(350):
            snapshot = orch.step()
        assert snapshot is not None
        assert snapshot.false_executions == 0
    finally:
        orch.close()


def _object_positions_for_seed(seed: int):
    config = _make_headless_config(seed)
    sim = RobotSimulator(config, use_gui=False)
    try:
        artifacts = build_messy_table(sim, config)
        positions = []
        for obj_id in artifacts.object_ids:
            pos = p.getBasePositionAndOrientation(obj_id)[0]
            positions.append(np.array(pos, dtype=float))
        return positions
    finally:
        sim.close()


def test_same_seed_produces_identical_object_positions():
    """Same seed should produce deterministic world object positions."""
    world1_positions = _object_positions_for_seed(42)
    world2_positions = _object_positions_for_seed(42)

    assert len(world1_positions) == len(world2_positions)
    for pos1, pos2 in zip(world1_positions, world2_positions):
        assert np.allclose(pos1, pos2, atol=1e-6)
