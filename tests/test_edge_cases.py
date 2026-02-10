import pybullet as p

from src.core.system_factory import build_system, load_config
from src.input.filter import DecisionFilter
from src.input.pipeline import DecisionPipeline
from src.input.policies import DecisionPolicy
from src.input.router import DecisionRouter
from src.input.source_fake import FakeSource


def _base_headless_config(seed: int, n_objects: int) -> dict:
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
    return config


def _inject_fake_confirms(orch, config: dict, max_frame: int = 200):
    policy = DecisionPolicy.from_config(config)
    router = DecisionRouter(policy)
    source = FakeSource()
    for frame in range(2, max_frame, 2):
        source.set_confirm_on_frame(frame)
    router.register_source("keyboard", source)
    orch.decision_pipeline = DecisionPipeline(router, DecisionFilter(config))


def _patch_deterministic_execution(orch):
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
            center = orch.world_artifacts.bin_zone_center
            p.resetBasePositionAndOrientation(
                held_id, [center[0], center[1], center[2]], [0, 0, 0, 1]
            )
        return ok

    controller.update = _update_fast
    grasp.detach = _detach_and_drop


def test_empty_table_does_not_execute():
    """Empty table should not crash or execute primitives."""
    config = _base_headless_config(seed=42, n_objects=0)
    orch = build_system(config)
    try:
        _inject_fake_confirms(orch, config)
        snapshot = None
        for _ in range(60):
            snapshot = orch.step()
        assert snapshot is not None
        assert snapshot.false_executions == 0
        assert orch.trust_metrics.confirmed_executions == 0
    finally:
        orch.close()


def test_single_object_completes_with_confirm():
    """Single object scenario should complete cleanly with deterministic execution."""
    config = _base_headless_config(seed=123, n_objects=1)
    config.setdefault("scene_understanding", {})
    config["scene_understanding"].setdefault("messy_detection", {})
    config["scene_understanding"]["messy_detection"]["min_objects"] = 1
    config["scene_understanding"]["messy_detection"]["spread_threshold"] = 0.0

    orch = build_system(config)
    try:
        _patch_deterministic_execution(orch)
        _inject_fake_confirms(orch, config)
        orch.force_lock_target(orch.world_artifacts.object_ids[0])

        done_seen = False
        for _ in range(200):
            snapshot = orch.step()
            if snapshot.state.value == "done":
                done_seen = True
                break

        assert done_seen
        assert orch.trust_metrics.false_executions == 0
        assert orch.trust_metrics.confirmed_executions >= 1
    finally:
        orch.close()


def test_all_unreachable_objects_rejected_by_compiler():
    """If workspace bounds reject all objects, system should reset safely."""
    config = _base_headless_config(seed=999, n_objects=1)
    config.setdefault("scene_understanding", {})
    config["scene_understanding"].setdefault("messy_detection", {})
    config["scene_understanding"]["messy_detection"]["min_objects"] = 1
    config["scene_understanding"]["messy_detection"]["spread_threshold"] = 0.0
    config["planning"]["clean_table"]["workspace_bounds"] = [
        -0.01, 0.01, -0.01, 0.01, 0.0, 1.0
    ]

    orch = build_system(config)
    try:
        _inject_fake_confirms(orch, config, max_frame=80)
        orch.force_lock_target(orch.world_artifacts.object_ids[0])

        snapshot = None
        for _ in range(80):
            snapshot = orch.step()

        assert snapshot is not None
        assert orch.trust_metrics.false_executions == 0
        assert orch.trust_metrics.confirmed_executions == 0
        assert snapshot.state.value in {"idle", "selecting", "confirming"}
    finally:
        orch.close()
