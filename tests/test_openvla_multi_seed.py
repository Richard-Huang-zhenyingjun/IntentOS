"""Multi-seed repeatability and safety tests for OpenVLA execution path."""

from __future__ import annotations

import numpy as np
import pytest

from src.core.system_factory import build_system, load_config
from src.input.filter import DecisionFilter
from src.input.pipeline import DecisionPipeline
from src.input.policies import DecisionPolicy
from src.input.router import DecisionRouter
from src.input.source_fake import FakeSource
from src.interfaces.intent_proposal import ActionType, IntentProposal
from src.interfaces.primitive import PrimitiveType

TEST_SEEDS = [42, 123, 456, 789, 1337]


def _config_for_seed(seed: int) -> dict:
    config = load_config("configs/default.yaml")
    config.setdefault("simulator", {})
    config["simulator"]["use_gui"] = False
    config.setdefault("gemini", {})
    config["gemini"]["enabled"] = False
    config.setdefault("eeg", {})
    config["eeg"]["enabled"] = False
    config.setdefault("logging", {})
    config["logging"]["events_enabled"] = False
    config.setdefault("openvla", {})
    config["openvla"]["enabled"] = True
    config["openvla"]["use_fake"] = True
    config.setdefault("world", {})
    config["world"].setdefault("messy_table", {})
    config["world"]["messy_table"]["seed"] = seed
    return config


def _install_auto_confirm_input(orch, config: dict):
    test_cfg = dict(config)
    test_cfg["input"] = dict(config.get("input", {}))
    test_cfg["input"]["mode"] = "KEYBOARD_ONLY"
    test_cfg["input"]["sources_enabled"] = ["keyboard"]
    test_cfg["input"]["debounce_frames"] = 0
    test_cfg["input"]["confirm_hold_frames"] = 1
    test_cfg["input"]["min_quality"] = 0.0

    policy = DecisionPolicy.from_config(test_cfg)
    router = DecisionRouter(policy)
    fake = FakeSource()
    for frame in range(2, 400, 8):
        fake.set_confirm_on_frame(frame)
    router.register_source("keyboard", fake)
    orch.decision_pipeline = DecisionPipeline(router, DecisionFilter(test_cfg))


def _openvla_proposal_for_scene(scene) -> IntentProposal:
    target = scene.objects_on_table[0] if scene.objects_on_table else scene.objects[0]
    return IntentProposal(
        action=ActionType.CLEAN_TABLE,
        description=f"OpenVLA trajectory for object {target.object_id}",
        source="openvla",
        confidence=0.95,
        metadata={
            "proposer": "openvla",
            "primitive_type": PrimitiveType.OPENVLA_TRAJECTORY.value,
            "instruction": "pick up the object",
            "target_object_id": target.object_id,
            "target_pos_xyz": list(target.pos_xyz),
            "delta_position": [0.01, 0.0, -0.02],
            "delta_rotation": [0.0, 0.0, 0.0],
            "gripper": 0.0,
            "raw_action": [0.01, 0.0, -0.02, 0.0, 0.0, 0.0, 0.0],
        },
        suggested_object_ids=[target.object_id],
    )


class TestMultiSeed:
    @pytest.mark.parametrize("seed", TEST_SEEDS)
    def test_seed_completes_without_crash(self, seed):
        orch = build_system(_config_for_seed(seed))
        try:
            _install_auto_confirm_input(orch, _config_for_seed(seed))
            if orch.world_artifacts and orch.world_artifacts.object_ids:
                orch.force_lock_target(orch.world_artifacts.object_ids[0])
            orch.proposer_registry.propose = lambda scene: _openvla_proposal_for_scene(scene)

            snapshot = None
            for _ in range(200):
                snapshot = orch.step()
            assert snapshot is not None
        finally:
            orch.close()

    @pytest.mark.parametrize("seed", TEST_SEEDS)
    def test_seed_invariant_holds(self, seed):
        orch = build_system(_config_for_seed(seed))
        try:
            _install_auto_confirm_input(orch, _config_for_seed(seed))
            if orch.world_artifacts and orch.world_artifacts.object_ids:
                orch.force_lock_target(orch.world_artifacts.object_ids[0])
            orch.proposer_registry.propose = lambda scene: _openvla_proposal_for_scene(scene)

            for _ in range(200):
                orch.step()
            assert orch.trust_metrics.false_executions == 0
            if hasattr(orch.executor, "invariant_summary"):
                assert orch.executor.invariant_summary["false_executions"] == 0
        finally:
            orch.close()

    @pytest.mark.parametrize("seed", TEST_SEEDS)
    def test_seed_no_nan(self, seed):
        orch = build_system(_config_for_seed(seed))
        try:
            _install_auto_confirm_input(orch, _config_for_seed(seed))
            if orch.world_artifacts and orch.world_artifacts.object_ids:
                orch.force_lock_target(orch.world_artifacts.object_ids[0])
            orch.proposer_registry.propose = lambda scene: _openvla_proposal_for_scene(scene)

            for frame in range(200):
                orch.step()
                arm = orch.sim.get_arm_state()
                joints = np.asarray(arm.joint_positions, dtype=float)
                assert np.all(np.isfinite(joints)), f"Non-finite joints at frame={frame}, seed={seed}"
        finally:
            orch.close()

