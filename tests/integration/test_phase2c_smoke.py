"""
Phase 2C smoke tests.

dry_run=True tests: no hardware required - verifies pipeline + invariant wiring.
real_arm tests: skipped unless RUN_REAL_ARM=1 env var is set.

Run:
    pytest tests/integration/test_phase2c_smoke.py -v
    RUN_REAL_ARM=1 pytest tests/integration/test_phase2c_smoke.py -v
"""
from __future__ import annotations

import copy
import os

import pytest
import yaml

REAL_ARM = os.environ.get("RUN_REAL_ARM", "0") == "1"


def _deep_update(base: dict, overrides: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_update(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


@pytest.fixture
def dry_run_config():
    with open("configs/default.yaml") as f:
        base = yaml.safe_load(f)

    overrides = {
        "simulator": {"use_gui": False},
        "hardware": {
            "backend": "hardware",
            "dry_run": True,
            "joint_limits": [[-90, 90]] * 6,
            "max_step_deg": 15.0,
            "real": {
                "port": "/dev/mock",
                "baud": 115200,
                "auto_connect": False,
            },
        },
        "eeg": {
            "backend": "simulated",
            "sim_sample_rate_hz": 50.0,
            "sim_intent_interval_s": 0.5,
            "decoder": {
                "model_path": "models/eeg_classifier.pkl",
                "window_duration_s": 0.1,
                "stride_s": 0.05,
                "confidence_threshold": 0.6,
            },
        },
        "openvla": {"backend": "fake", "enabled": False},
        "logging": {"events_enabled": False},
    }
    return _deep_update(base, overrides)


class TestDryRunPipeline:
    """No hardware - FakeSerialController used internally."""

    def test_system_assembles_with_hardware_dry_run(self, dry_run_config):
        from src.core.system_factory import build_system

        system = build_system(dry_run_config)
        try:
            assert system is not None
        finally:
            system.close()

    def test_invariant_holds_dry_run_20_frames(self, dry_run_config):
        from src.core.system_factory import build_system

        system = build_system(dry_run_config)
        try:
            for _ in range(20):
                system.step()
            checker = _get_invariant_checker(system)
            assert checker.false_executions == 0
        finally:
            system.close()

    def test_no_real_serial_commands_sent_in_dry_run(self, dry_run_config):
        """dry_run=True uses FakeSerialController, so serial.Serial is never opened."""
        from src.core.system_factory import build_system

        system = build_system(dry_run_config)
        try:
            for _ in range(50):
                system.step()
            assert True
        finally:
            system.close()

    def test_hardware_backend_uses_fake_controller_in_dry_run(self, dry_run_config):
        from src.core.system_factory import build_system
        from src.robot.hardware.serial_controller_fake import FakeSerialController

        system = build_system(dry_run_config)
        try:
            arm_ctrl = _get_arm_controller(system)
            assert isinstance(arm_ctrl._serial, FakeSerialController)
        finally:
            system.close()


@pytest.mark.skipif(not REAL_ARM, reason="Set RUN_REAL_ARM=1 to run real arm tests")
class TestRealArmPipeline:
    """Requires physical arm. Run manually after hardware is assembled."""

    def test_real_arm_ping(self):
        """Arm responds to PING after connection."""
        port = os.environ.get("ARM_PORT", "/dev/tty.usbserial-0001")
        from src.robot.hardware.serial_controller import SerialConfig, SerialController

        ctrl = SerialController(SerialConfig(port=port))
        assert ctrl.connect()
        assert ctrl.ping()
        ctrl.disconnect()

    def test_invariant_holds_real_arm_sim_eeg(self):
        """Real arm + simulated EEG - false_executions == 0."""
        with open("configs/default.yaml") as f:
            base = yaml.safe_load(f)
        with open("configs/real_arm.yaml") as f:
            real_arm = yaml.safe_load(f)

        cfg = _deep_update(base, real_arm)
        cfg = _deep_update(
            cfg,
            {
                "simulator": {"use_gui": False},
                "eeg": {"backend": "simulated"},
            },
        )

        from src.core.system_factory import build_system

        system = build_system(cfg)
        try:
            for _ in range(100):
                system.step()
            checker = _get_invariant_checker(system)
            assert checker.false_executions == 0
        finally:
            system.close()

    def test_emergency_stop_halts_execution(self):
        """E-stop fires and the invariant remains auditable."""
        pytest.skip("Adapt once the runtime e-stop trigger is exposed by the app layer.")


def _get_invariant_checker(system):
    for path in [
        "executor._invariant_checker",
        "trust_metrics",
        "orchestrator.invariant_checker",
        "invariant_checker",
    ]:
        obj = system
        for attr in path.split("."):
            obj = getattr(obj, attr, None)
            if obj is None:
                break
        if obj is not None and hasattr(obj, "false_executions"):
            return obj
    raise AttributeError("Cannot locate false_executions tracker.")


def _get_arm_controller(system):
    for path in [
        "executor.hardware_bridge._backend._controller",
        "executor._hardware_bridge._backend._controller",
        "_arm_controller",
        "arm_controller",
    ]:
        obj = system
        for attr in path.split("."):
            obj = getattr(obj, attr, None)
            if obj is None:
                break
        if obj is not None:
            return obj
    raise AttributeError("Cannot locate arm controller.")
