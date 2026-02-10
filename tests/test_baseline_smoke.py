"""Baseline smoke tests for factory assembly and basic stepping."""

import yaml
from src.core.system_factory import build_system


def _load_baseline_config() -> dict:
    with open("configs/default.yaml", "r") as f:
        config = yaml.safe_load(f)

    # Disable external/optional runtime sources for deterministic smoke tests.
    config.setdefault("gemini", {})
    config["gemini"]["enabled"] = False

    config.setdefault("eeg", {})
    config["eeg"]["enabled"] = False

    # Ensure test runs headless.
    config.setdefault("simulator", {})
    config["simulator"]["use_gui"] = False

    return config


def test_system_factory_assembles():
    config = _load_baseline_config()

    system = build_system(config)
    try:
        assert system is not None
        assert hasattr(system, "step")
        assert callable(system.step)
    finally:
        system.close()


def test_orchestrator_runs_10_frames_no_crash():
    config = _load_baseline_config()

    system = build_system(config)
    try:
        for _ in range(10):
            system.step()
    finally:
        system.close()
