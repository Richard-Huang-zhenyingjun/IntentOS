"""Startup and runtime diagnostics for demo entrypoints."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import os
import sys

import pybullet as p
import pybullet_data


@dataclass
class DiagnosticReport:
    all_clear: bool = True
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    config_summary: Dict[str, Any] = field(default_factory=dict)

    def add_warning(self, message: str):
        self.warnings.append(message)
        self.all_clear = False

    def add_error(self, message: str):
        self.errors.append(message)
        self.all_clear = False


_REQUIRED_CONFIG_PATHS = [
    ("world", "messy_table"),
    ("planning", "clean_table"),
    ("input", "mode"),
    ("input", "sources_enabled"),
    ("simulator", "use_gui"),
]


def print_startup_banner():
    """Print once at startup to verify execution paths."""
    print("=" * 60)
    print("[DIAG] Startup Environment Check")
    print("=" * 60)
    print(f"[DIAG] Python: {sys.executable}")
    print(f"[DIAG] CWD: {os.getcwd()}")
    print(f"[DIAG] Repo root: {Path(__file__).parent.parent.parent}")
    print("=" * 60)


def diag_print(msg: str, enabled: bool = True):
    """Conditional diagnostic print."""
    if enabled:
        print(f"[DIAG] {msg}")


def _get_nested(config: dict, path: tuple) -> Optional[Any]:
    node: Any = config
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _summarize_config(config: dict) -> Dict[str, Any]:
    world_cfg = config.get("world", {}).get("messy_table", {})
    input_cfg = config.get("input", {})
    gemini_cfg = config.get("gemini", {})
    eeg_cfg = config.get("eeg", {})
    sim_cfg = config.get("simulator", {})
    auto_cfg = config.get("autonomy", {})

    return {
        "use_gui": sim_cfg.get("use_gui", False),
        "seed": world_cfg.get("seed"),
        "n_objects": world_cfg.get("n_objects"),
        "input_mode": input_cfg.get("mode"),
        "sources_enabled": input_cfg.get("sources_enabled", []),
        "autonomy_level": auto_cfg.get("level", "A2_TASK_CONFIRM"),
        "gemini_enabled": gemini_cfg.get("enabled", False),
        "openvla_enabled": config.get("openvla", {}).get("enabled", False),
        "eeg_enabled": eeg_cfg.get("enabled", False),
    }


def _check_openvla(config: dict) -> tuple[str, List[str]]:
    """Check OpenVLA proposer status and runtime readiness hints."""
    warnings: List[str] = []
    openvla_cfg = config.get("openvla", {})

    if not openvla_cfg.get("enabled", False):
        return "DISABLED (config)", warnings

    backend = openvla_cfg.get("backend")
    if backend is None:
        backend = "fake" if openvla_cfg.get("use_fake", True) else "real"

    if backend == "fake":
        return "OK (fake adapter, no GPU)", warnings

    try:
        import torch

        if torch.cuda.is_available():
            try:
                gpu_name = torch.cuda.get_device_name(0)
            except Exception:
                gpu_name = "CUDA device"
            return f"OK (GPU: {gpu_name})", warnings

        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "OK (MPS available)", warnings

        warnings.append("OpenVLA real adapter enabled without CUDA/MPS; inference will be slow.")
        return "WARNING (no accelerator, will be slow)", warnings
    except ImportError:
        warnings.append("OpenVLA real adapter enabled but torch is not installed.")
        return "WARNING (torch not installed)", warnings


def run_startup_diagnostics(config: dict) -> DiagnosticReport:
    """Run preflight diagnostics before building the system."""
    report = DiagnosticReport(config_summary=_summarize_config(config))

    # Required config keys
    for path in _REQUIRED_CONFIG_PATHS:
        if _get_nested(config, path) is None:
            dotted = ".".join(path)
            report.add_error(f"Missing required config key: {dotted}")

    # Gemini API key checks
    gemini_cfg = config.get("gemini", {})
    if gemini_cfg.get("enabled", False):
        if gemini_cfg.get("use_fake_client", False):
            report.add_warning("Gemini enabled with fake client; real API not used.")
        else:
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                report.add_warning(
                    "Gemini enabled but GEMINI_API_KEY is not set. "
                    "Fallback proposer may be used."
                )

    # OpenVLA checks
    openvla_status, openvla_warnings = _check_openvla(config)
    report.config_summary["openvla"] = openvla_status
    for warning in openvla_warnings:
        report.add_warning(warning)

    # EEG checks (do not touch src/input/eeg/*)
    eeg_cfg = config.get("eeg", {})
    if eeg_cfg.get("enabled", False):
        backend = eeg_cfg.get("backend", "brainlink")
        if backend == "brainlink":
            report.add_warning(
                "EEG backend is 'brainlink'. If device is unavailable, system will skip/" 
                "fallback per factory behavior."
            )
        elif backend == "replay":
            replay_file = eeg_cfg.get("replay_file")
            if replay_file and not Path(replay_file).exists():
                report.add_warning(f"EEG replay file not found: {replay_file}")
        else:
            report.add_warning(f"Unknown EEG backend configured: {backend}")

    # PyBullet connection + URDF checks
    client = None
    try:
        client = p.connect(p.DIRECT)
        if client < 0:
            report.add_error("PyBullet failed to connect in DIRECT mode.")
        else:
            data_path = Path(pybullet_data.getDataPath())
            plane_urdf = data_path / "plane.urdf"
            robot_urdf = data_path / "kuka_iiwa" / "model.urdf"

            if not plane_urdf.exists():
                report.add_error(f"Missing URDF file: {plane_urdf}")
            if not robot_urdf.exists():
                report.add_error(f"Missing URDF file: {robot_urdf}")

            p.setAdditionalSearchPath(str(data_path))
            p.setGravity(0, 0, -9.81)

            try:
                p.loadURDF("plane.urdf")
            except Exception as exc:
                report.add_error(f"Failed to load plane URDF: {exc}")

            try:
                p.loadURDF("kuka_iiwa/model.urdf", useFixedBase=True)
            except Exception as exc:
                report.add_error(f"Failed to load KUKA URDF: {exc}")
    except Exception as exc:
        report.add_error(f"PyBullet diagnostic check failed: {exc}")
    finally:
        if client is not None and client >= 0:
            try:
                p.disconnect(client)
            except Exception:
                pass

    report.all_clear = len(report.errors) == 0 and len(report.warnings) == 0
    return report


def run_diagnostics(config: dict) -> DiagnosticReport:
    """Backward-compatible public entrypoint for demo preflight checks."""
    return run_startup_diagnostics(config)


def validate_world_spawn(orch: Any) -> DiagnosticReport:
    """Validate that required world artifacts were created in a live orchestrator."""
    report = DiagnosticReport(config_summary={})

    artifacts = getattr(orch, "world_artifacts", None)
    if artifacts is None:
        report.add_error("World artifacts missing on orchestrator.")
        return report

    table_id = getattr(artifacts, "table_id", None)
    object_ids = list(getattr(artifacts, "object_ids", []) or [])
    bin_center = getattr(artifacts, "bin_zone_center", None)
    bin_radius = getattr(artifacts, "bin_zone_radius", None)

    report.config_summary = {
        "table_id": table_id,
        "object_count": len(object_ids),
        "bin_zone_center": bin_center,
        "bin_zone_radius": bin_radius,
    }

    if table_id is None:
        report.add_error("World table_id is missing.")
    else:
        try:
            p.getBodyInfo(table_id)
        except Exception:
            report.add_error(f"World table_id is invalid/unspawned: {table_id}")

    if not object_ids:
        report.add_error("No world objects spawned.")
    else:
        for obj_id in object_ids:
            try:
                p.getBodyInfo(obj_id)
            except Exception:
                report.add_error(f"Invalid object id in world artifacts: {obj_id}")

    if bin_center is None:
        report.add_error("Bin zone center missing.")
    if bin_radius is None or bin_radius <= 0:
        report.add_error(f"Bin zone radius invalid: {bin_radius}")

    report.all_clear = len(report.errors) == 0 and len(report.warnings) == 0
    return report


def format_diagnostic_report(report: DiagnosticReport, title: str) -> str:
    """Create a human-readable diagnostic report block."""
    lines = [
        "=" * 60,
        f"[DIAG] {title}",
        "=" * 60,
    ]

    if report.config_summary:
        lines.append("[DIAG] Configuration Summary:")
        for key, value in report.config_summary.items():
            lines.append(f"  - {key}: {value}")

    if report.warnings:
        lines.append("[DIAG] Warnings:")
        for warning in report.warnings:
            lines.append(f"  - {warning}")

    if report.errors:
        lines.append("[DIAG] Errors:")
        for err in report.errors:
            lines.append(f"  - {err}")

    if not report.warnings and not report.errors:
        lines.append("[DIAG] All checks passed.")

    lines.append("=" * 60)
    return "\n".join(lines)
