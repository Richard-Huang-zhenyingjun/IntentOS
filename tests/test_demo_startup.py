"""Smoke tests for demo startup diagnostics and controlled reset."""

from src.core.diag import run_diagnostics
from src.core.system_factory import build_system, load_config
from scripts.run_demo import _controlled_world_reset


def _base_config() -> dict:
    config = load_config("configs/default.yaml")
    config.setdefault("gemini", {})
    config["gemini"]["enabled"] = False
    config.setdefault("eeg", {})
    config["eeg"]["enabled"] = False
    config.setdefault("simulator", {})
    config["simulator"]["use_gui"] = False
    return config


def test_diagnostics_run_without_crash():
    """Diagnostic report can be generated."""
    config = _base_config()
    report = run_diagnostics(config)

    assert isinstance(report.all_clear, bool)
    assert isinstance(report.warnings, list)
    assert isinstance(report.errors, list)


def test_demo_script_imports():
    """Demo script imports don't crash."""
    import scripts.run_demo as demo

    assert hasattr(demo, "main")


def test_world_reset_clears_state():
    """World reset brings system back to IDLE."""
    config = _base_config()
    orch = build_system(config)
    try:
        # Move out of IDLE so reset behavior is observable.
        if orch.world_artifacts.object_ids:
            orch.force_lock_target(orch.world_artifacts.object_ids[0])

        _controlled_world_reset(orch, config, seed=123)

        assert orch.state_machine.state.value == "idle"
        assert orch.auth_manager.get_active_token_id() is None
        assert orch.trust_engine.task_trust == orch.trust_engine.init_trust
        assert orch.world_artifacts is not None
        assert len(orch.world_artifacts.object_ids) > 0
    finally:
        orch.close()
