"""Fault injection tests for runtime robustness."""

import random
import numpy as np

from src.core.system_factory import build_system, load_config
from src.execution.primitive_executor import ExecutorStatus
from src.input.filter import DecisionFilter
from src.input.pipeline import DecisionPipeline
from src.input.policies import DecisionPolicy
from src.input.router import DecisionRouter
from src.input.source_fake import FakeSource
from src.planning.primitive import Primitive, PrimitiveType


def _build_system_with_scheduled_confirms():
    config = load_config("configs/default.yaml")
    config.setdefault("simulator", {})
    config["simulator"]["use_gui"] = False
    config.setdefault("gemini", {})
    config["gemini"]["enabled"] = False
    config.setdefault("eeg", {})
    config["eeg"]["enabled"] = False
    config.setdefault("logging", {})
    config["logging"]["events_enabled"] = False

    orch = build_system(config)

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
    for frame in (5, 15, 80, 90, 140, 150, 220, 230):
        fake.set_confirm_on_frame(frame)
    router.register_source("keyboard", fake)
    orch.decision_pipeline = DecisionPipeline(router, DecisionFilter(test_cfg))

    if orch.world_artifacts and orch.world_artifacts.object_ids:
        orch.force_lock_target(orch.world_artifacts.object_ids[0])

    # Test-local patch: emit executor-compatible primitives.
    def _compile_stub(_proposal, scene):
        target = scene.objects_on_table[0]
        target_xyz = np.array(target.pos_xyz, dtype=float)
        return [
            Primitive(PrimitiveType.REACH, target_xyz=target_xyz + np.array([0.0, 0.0, 0.10])),
            Primitive(PrimitiveType.GRASP, object_id=target.object_id),
            Primitive(PrimitiveType.MOVE_TO, target_xyz=target_xyz + np.array([0.0, 0.0, 0.20])),
            Primitive(PrimitiveType.RELEASE, object_id=target.object_id),
        ]

    orch.compiler.compile = _compile_stub
    def _ptype(primitive) -> str:
        ptype = getattr(primitive, "type", None)
        return ptype.value if hasattr(ptype, "value") else str(ptype)

    def _start_stub(primitive, _world):
        ptype = _ptype(primitive)
        if ptype in ("reach", "move_to"):
            return True
        if ptype == "grasp":
            if primitive.object_id is None:
                return False
            return orch.grasp.attach(primitive.object_id)
        if ptype == "release":
            orch.grasp.detach()
            return True
        return False

    def _check_stub(_primitive, _world):
        return True

    # Test-local shim: avoid pybullet IK differences from blocking progression.
    orch.executor._start_primitive = _start_stub
    orch.executor._check_primitive_complete = _check_stub

    return orch


def test_random_grasp_failure_recovers():
    """System recovers from injected random grasp start failures without crash."""
    orch = _build_system_with_scheduled_confirms()
    rng = random.Random(7)
    failure_counter = {"count": 0}
    first_grasp_failed = {"done": False}

    original_start_primitive = orch.executor._start_primitive

    def flaky_start(primitive, world):
        if primitive.type == PrimitiveType.GRASP:
            # Guarantee at least one injected failure, then continue with 30% random failures.
            if not first_grasp_failed["done"]:
                first_grasp_failed["done"] = True
                failure_counter["count"] += 1
                return False
            if rng.random() < 0.30:
                failure_counter["count"] += 1
                return False
        return original_start_primitive(primitive, world)

    orch.executor._start_primitive = flaky_start

    try:
        snapshot = None
        for _ in range(260):
            snapshot = orch.step()
        assert snapshot is not None
        assert failure_counter["count"] >= 1
        assert snapshot.false_executions == 0
        # Recovery path should not crash the loop even after failures.
        assert orch.global_frame_counter >= 260
    finally:
        orch.close()


def test_random_timeout_aborts_safely():
    """System handles injected random execution failures (timeout-like) safely."""
    orch = _build_system_with_scheduled_confirms()
    rng = random.Random(11)
    injected_failures = {"count": 0}

    original_tick = orch.executor.tick

    def flaky_tick(world):
        status = original_tick(world)
        if status == ExecutorStatus.RUNNING and rng.random() < 0.20:
            injected_failures["count"] += 1
            return ExecutorStatus.FAILED
        return status

    orch.executor.tick = flaky_tick

    try:
        snapshot = None
        for _ in range(300):
            snapshot = orch.step()
        assert snapshot is not None
        assert injected_failures["count"] >= 1
        assert snapshot.false_executions == 0
    finally:
        orch.close()
