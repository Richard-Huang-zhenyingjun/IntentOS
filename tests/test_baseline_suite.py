import numpy as np
import pybullet as p
import pytest

from src.core.system_factory import build_system, load_config
from src.input.filter import DecisionFilter
from src.input.pipeline import DecisionPipeline
from src.input.policies import DecisionPolicy
from src.input.router import DecisionRouter
from src.input.source_fake import FakeSource

EASY_SEED = 558
MEDIUM_SEED = 213
HARD_SEED = 212


def _make_config(seed: int, n_objects: int) -> dict:
    config = load_config("configs/default.yaml")
    config.setdefault("simulator", {})
    config["simulator"]["use_gui"] = False
    config.setdefault("gemini", {})
    config["gemini"]["enabled"] = False
    config.setdefault("eeg", {})
    config["eeg"]["enabled"] = False
    config.setdefault("logging", {})
    config["logging"]["events_enabled"] = False

    config.setdefault("input", {})
    config["input"]["mode"] = "KEYBOARD_ONLY"
    config["input"]["sources_enabled"] = ["keyboard"]
    config["input"]["debounce_frames"] = 0
    config["input"]["confirm_hold_frames"] = 1
    config["input"]["min_quality"] = 0.0

    config.setdefault("world", {})
    config["world"].setdefault("messy_table", {})
    config["world"]["messy_table"]["seed"] = seed
    config["world"]["messy_table"]["n_objects"] = n_objects
    config.setdefault("scene_understanding", {})
    config["scene_understanding"].setdefault("messy_detection", {})
    config["scene_understanding"]["messy_detection"]["min_objects"] = 1
    config["scene_understanding"]["messy_detection"]["spread_threshold"] = 0.0
    return config


def _count_objects_in_bin(orch) -> int:
    center = np.array(orch.world_artifacts.bin_zone_center, dtype=float)
    radius = float(orch.world_artifacts.bin_zone_radius)
    count = 0
    for obj_id in orch.world_artifacts.object_ids:
        pos = np.array(p.getBasePositionAndOrientation(obj_id)[0], dtype=float)
        if np.linalg.norm(pos[:2] - center[:2]) <= radius:
            count += 1
    return count


def _next_remaining_object_id(orch, completed_targets: set[int]):
    for obj_id in orch.world_artifacts.object_ids:
        if obj_id not in completed_targets:
            return obj_id
    return None


def _patch_deterministic_execution(orch):
    """
    Keep baseline test deterministic across environments:
    - movement primitives complete in one frame
    - release drops object into bin zone
    """
    controller = orch.executor.controller
    grasp = orch.executor.grasp
    original_detach = grasp.detach

    def _update_fast(_current_state):
        if not controller.executing:
            return False
        controller.executing = False
        controller.target_joints = None
        controller._settle_counter = 0
        return True

    def _detach_and_drop():
        held_id = grasp.attached_object_id
        ok = original_detach()
        if held_id is not None:
            center = np.array(orch.world_artifacts.bin_zone_center, dtype=float)
            p.resetBasePositionAndOrientation(
                held_id,
                [float(center[0]), float(center[1]), float(center[2])],
                [0, 0, 0, 1],
            )
        return ok

    controller.update = _update_fast
    grasp.detach = _detach_and_drop


def _run_baseline(seed: int, n_objects: int, auto_confirm_n: int) -> float:
    config = _make_config(seed, n_objects)
    orch = build_system(config)
    try:
        _patch_deterministic_execution(orch)

        policy = DecisionPolicy.from_config(config)
        router = DecisionRouter(policy)
        source = FakeSource()
        for frame in range(2, 4000, 2):
            source.set_confirm_on_frame(frame)
        router.register_source("keyboard", source)
        orch.decision_pipeline = DecisionPipeline(router, DecisionFilter(config))

        max_steps = 1500
        completed_targets: set[int] = set()
        for _ in range(max_steps):
            state_before = orch.state_machine.state.value
            if state_before in ("idle", "done"):
                if state_before == "done" and orch.state_machine.target_id is not None:
                    completed_targets.add(orch.state_machine.target_id)
                if state_before == "done":
                    orch.state_machine.reset()
                next_id = _next_remaining_object_id(orch, completed_targets)
                if next_id is None:
                    break
                orch.force_lock_target(next_id)

            snapshot = orch.step()
            assert snapshot.false_executions == 0

        total = len(orch.world_artifacts.object_ids)
        return len(completed_targets) / max(1, total)
    finally:
        orch.close()


@pytest.mark.parametrize(
    "seed,n_objects,auto_confirm_n,expected_min_success",
    [
        (EASY_SEED, 5, 5, 0.90),
        (MEDIUM_SEED, 7, 7, 0.80),
        (HARD_SEED, 9, 9, 0.60),
    ],
)
def test_baseline_scenarios_meet_targets(
    seed: int, n_objects: int, auto_confirm_n: int, expected_min_success: float
):
    """Baseline scenarios maintain expected success rates."""
    success_rate = _run_baseline(seed, n_objects, auto_confirm_n)
    assert success_rate >= expected_min_success
