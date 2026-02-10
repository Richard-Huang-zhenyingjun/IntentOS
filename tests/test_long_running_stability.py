"""Long-running stability smoke tests."""

import tracemalloc

import pytest

from src.core.system_factory import build_system, load_config
from src.worlds.messy_table_world import reset_world


def _stability_config() -> dict:
    config = load_config("configs/default.yaml")
    config.setdefault("simulator", {})
    config["simulator"]["use_gui"] = False
    config.setdefault("gemini", {})
    config["gemini"]["enabled"] = False
    config.setdefault("eeg", {})
    config["eeg"]["enabled"] = False
    config.setdefault("logging", {})
    config["logging"]["events_enabled"] = False
    return config


@pytest.mark.slow
def test_1000_frame_run_no_memory_leak():
    """System runs for 1000 frames with bounded Python memory growth."""
    config = _stability_config()
    orch = build_system(config)
    try:
        tracemalloc.start()
        start_current, _ = tracemalloc.get_traced_memory()
        for _ in range(1000):
            snapshot = orch.step()
        end_current, _ = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        assert snapshot.false_executions == 0
        growth_mb = max(0, end_current - start_current) / (1024 * 1024)
        assert growth_mb < 60.0
    finally:
        orch.close()


@pytest.mark.slow
def test_10_consecutive_resets():
    """System tolerates repeated reset cycles without degradation."""
    config = _stability_config()
    orch = build_system(config)
    try:
        for i in range(10):
            orch.world_artifacts = reset_world(
                sim=orch.sim,
                config=config,
                previous_artifacts=orch.world_artifacts,
                seed=100 + i,
            )
            orch.state_machine.reset()
            orch.current_proposal = None
            orch.current_scene = None
            for _ in range(25):
                snapshot = orch.step()

            assert len(orch.world_artifacts.object_ids) > 0
            assert snapshot.false_executions == 0
    finally:
        orch.close()
