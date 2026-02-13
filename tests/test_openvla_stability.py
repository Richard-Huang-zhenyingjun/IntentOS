"""Long-running stability tests for OpenVLA proposal/execution path."""

from __future__ import annotations

import random
import tracemalloc

import numpy as np

from src.core.system_factory import build_system, load_config
from src.input.filter import DecisionFilter
from src.input.pipeline import DecisionPipeline
from src.input.policies import DecisionPolicy
from src.input.router import DecisionRouter
from src.input.source_fake import FakeSource
from src.interfaces.intent_proposal import ActionType, IntentProposal
from src.interfaces.primitive import PrimitiveType


def _base_config() -> dict:
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
    return config


def _install_input(orch, config: dict, confirm_frames=(), cancel_frames=()):
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
    for frame in confirm_frames:
        fake.set_confirm_on_frame(frame)
    for frame in cancel_frames:
        fake.set_cancel_on_frame(frame)
    router.register_source("keyboard", fake)
    orch.decision_pipeline = DecisionPipeline(router, DecisionFilter(test_cfg))


def _openvla_proposal(scene) -> IntentProposal:
    target = scene.objects_on_table[0] if scene.objects_on_table else scene.objects[0]
    return IntentProposal(
        action=ActionType.CLEAN_TABLE,
        description=f"OpenVLA trajectory for object {target.object_id}",
        source="openvla",
        confidence=0.95,
        metadata={
            "proposer": "openvla",
            "primitive_type": PrimitiveType.OPENVLA_TRAJECTORY.value,
            "instruction": "pick up the object and place it in the bin",
            "target_object_id": target.object_id,
            "target_pos_xyz": list(target.pos_xyz),
            "delta_position": [0.01, 0.0, -0.02],
            "delta_rotation": [0.0, 0.0, 0.0],
            "gripper": 0.0,
            "raw_action": [0.01, 0.0, -0.02, 0.0, 0.0, 0.0, 0.0],
        },
        suggested_object_ids=[target.object_id],
    )


class TestLongRunningStability:
    def test_1000_frames_with_openvla(self):
        config = _base_config()
        orch = build_system(config)
        try:
            # Auto-confirm regularly.
            _install_input(orch, config, confirm_frames=tuple(range(2, 1000, 10)))
            if orch.world_artifacts and orch.world_artifacts.object_ids:
                orch.force_lock_target(orch.world_artifacts.object_ids[0])
            orch.proposer_registry.propose = lambda scene: _openvla_proposal(scene)

            tracemalloc.start()
            start_current, _ = tracemalloc.get_traced_memory()

            for frame in range(1000):
                orch.step()

                arm = orch.sim.get_arm_state()
                joints = np.asarray(arm.joint_positions, dtype=float)
                assert np.all(np.isfinite(joints)), f"Non-finite joints at frame {frame}"

                trust = float(orch.trust_engine.task_trust)
                assert 0.0 <= trust <= 1.0, f"Trust out of bounds at frame {frame}: {trust}"

            end_current, _ = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            growth_mb = max(0, end_current - start_current) / (1024 * 1024)
            assert growth_mb < 60.0
            assert orch.trust_metrics.false_executions == 0
            assert orch.executor.invariant_summary["false_executions"] == 0
        finally:
            orch.close()

    def test_500_frames_with_random_decisions(self):
        seed = 42
        rng = random.Random(seed)

        confirm_frames = []
        cancel_frames = []
        for frame in range(2, 502):
            if rng.random() > 0.5:
                confirm_frames.append(frame)
            else:
                cancel_frames.append(frame)

        config = _base_config()
        orch = build_system(config)
        try:
            _install_input(orch, config, confirm_frames=tuple(confirm_frames), cancel_frames=tuple(cancel_frames))
            if orch.world_artifacts and orch.world_artifacts.object_ids:
                orch.force_lock_target(orch.world_artifacts.object_ids[0])
            orch.proposer_registry.propose = lambda scene: _openvla_proposal(scene)

            for frame in range(500):
                orch.step()
                arm = orch.sim.get_arm_state()
                joints = np.asarray(arm.joint_positions, dtype=float)
                assert np.all(np.isfinite(joints)), f"Non-finite joints at frame {frame}"

            assert orch.trust_metrics.false_executions == 0
            assert orch.executor.invariant_summary["false_executions"] == 0
        finally:
            orch.close()

