import pytest

from src.core.perf import FrameTiming, PerfMonitor
from src.core.system_factory import build_system, load_config


@pytest.mark.slow
def test_frame_time_under_budget():
    """Average frame time stays under 16.67ms (60 FPS budget)."""
    config = load_config("configs/week8_full.yaml")
    config.setdefault("simulator", {})
    config["simulator"]["use_gui"] = False
    config.setdefault("gemini", {})
    config["gemini"]["enabled"] = False
    config.setdefault("eeg", {})
    config["eeg"]["enabled"] = False
    config.setdefault("logging", {})
    config["logging"]["events_enabled"] = False

    orch = build_system(config)
    monitor = PerfMonitor(enabled=True)
    try:
        for frame in range(1000):
            monitor.start("frame")
            monitor.start("orchestrator")
            snapshot = orch.step()
            orchestrator_ms = monitor.end("orchestrator")
            total_ms = monitor.end("frame")
            monitor.record_frame(
                FrameTiming(
                    frame_num=frame,
                    total_ms=total_ms,
                    orchestrator_ms=orchestrator_ms,
                    overlay_ms=0.0,
                    metrics_ms=0.0,
                    physics_ms=max(0.0, total_ms - orchestrator_ms),
                )
            )
            assert snapshot.false_executions == 0

        summary = monitor.summary()
        assert summary["total_p95_ms"] < 16.67
    finally:
        orch.close()
