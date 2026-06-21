#!/usr/bin/env python3
"""Smart Workspace v1 interactive runner."""
from __future__ import annotations

import argparse
import copy
import logging
import os
import re
import sys
from pathlib import Path
from typing import TextIO

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))


def _setup_logging(session_dir: str = "data/sessions") -> None:
    """
    Human Mode: suppress Phase 2 internals from terminal.
    Route everything to a log file instead.
    IntentOS interaction layer stays visible.
    """
    os.makedirs(session_dir, exist_ok=True)
    log_path = os.path.join(session_dir, "phase2_debug.log")

    fh = logging.FileHandler(log_path, mode="a")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s %(name)s %(levelname)s: %(message)s"
    ))

    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    root.addHandler(fh)

    for name in ("src.interaction", "src.intentos", "src.kernel"):
        logging.getLogger(name).setLevel(logging.INFO)


def _redirect_native_stderr(session_dir: str = "data/sessions") -> None:
    """Route native library stderr writes, such as pybullet banners, to file."""
    log_path = os.path.join(session_dir, "phase2_debug.log")
    sys.stderr.flush()
    native_stderr = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(native_stderr, 2)
    os.close(native_stderr)


class _HumanModeStdout:
    """
    Filters known Phase 2 console prefixes from terminal output.
    Captured lines still go to the log file via logging.
    """

    _FILTER = (
        "[FSM]", "[ORCH]", "[SIM]", "[CTRL]", "[EXECUTOR]",
        "[OPENVLA]", "[RELEASE]", "[FACTORY]", "[CTRL-IK]",
        "pybullet", "b3Printf", "bullet", "OpenGL",
        "[REGISTRY]", "[SIM-DIAG]", "[PHASE2]", "startThreads",
        "WARN:", "numActiveThreads", "[DISCOVERY]", "[GRASP]",
        "[WORLD]", "[FSM DEBUG]",
    )
    _FILTER_EXACT_OR_PREFIX = (
        "target_id:", "locked:", "current state BEFORE:",
        "Should be SELECTING", "set_target complete",
        "Index  Name", "----",
    )
    _log = logging.getLogger("src.phase2.stdout")

    def __init__(self, real: TextIO):
        self._real = real
        self._buffer = ""
        self._suppress_joint_table = False

    def write(self, text: str) -> int:
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._write_line(line + "\n")
        return len(text)

    def flush(self) -> None:
        if self._buffer:
            self._write_line(self._buffer)
            self._buffer = ""
        self._real.flush()

    def __getattr__(self, name):
        return getattr(self._real, name)

    def _write_line(self, line: str) -> None:
        stripped = line.strip()
        if self._should_filter(stripped):
            if stripped:
                self._log.debug(stripped)
            return
        self._real.write(line)

    def _should_filter(self, stripped: str) -> bool:
        if not stripped:
            return self._suppress_joint_table
        if stripped.startswith("JOINT TABLE"):
            self._suppress_joint_table = True
            return True
        if self._suppress_joint_table:
            if stripped.startswith("==="):
                self._suppress_joint_table = False
            return True
        if any(stripped.startswith(p) for p in self._FILTER):
            return True
        if any(stripped.startswith(p) for p in self._FILTER_EXACT_OR_PREFIX):
            return True
        if stripped and set(stripped) <= {"=", "-"}:
            return True
        if re.match(r"^\d+\s+\S+", stripped):
            return True
        if re.match(r"^[\[\]\d\s.,+-]+$", stripped):
            return True
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Smart Workspace v1")
    parser.add_argument("--preset", default="workspace_easy_clean")
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument(
        "--no-monitor",
        action="store_true",
        help="Disable browser monitor (default: monitor runs on port 7788)",
    )
    parser.add_argument(
        "--reset-history",
        action="store_true",
        help="Clear execution history before this session (for clean interaction tests)",
    )
    parser.add_argument(
        "--e3-disturbance",
        action="store_true",
        help=(
            "TEMP: start with 3 objects and inject a new object after the "
            "first release for the live E3 disturbance experiment."
        ),
    )
    parser.add_argument(
        "--e4-disturbance",
        action="store_true",
        help=(
            "TEMP: start with 1 object and inject a new object after every "
            "objective-continuation cycle until max_cycles stops the loop."
        ),
    )
    args = parser.parse_args()
    if args.e3_disturbance and args.e4_disturbance:
        parser.error("--e3-disturbance and --e4-disturbance are mutually exclusive")

    if args.reset_history:
        history_path = "data/execution_history.json"
        if os.path.exists(history_path):
            os.remove(history_path)
            print("[INFO] Execution history cleared for this session.")

    cfg = _load_yaml(args.config)
    if args.headless:
        cfg.setdefault("simulator", {})["use_gui"] = False
    cfg.setdefault("eeg", {})["backend"] = "sim"
    cfg.setdefault("input", {})["sources_enabled"] = ["keyboard"]
    if args.no_llm:
        cfg.setdefault("gemini", {})["enabled"] = False

    _setup_logging()
    _redirect_native_stderr()
    sys.stdout = _HumanModeStdout(sys.stdout)
    sys.stderr = _HumanModeStdout(sys.stderr)

    presets = _load_yaml("configs/workspace_presets.yaml").get("presets", {})
    preset = presets.get(args.preset)
    if preset is None:
        print(f"Unknown preset: {args.preset}")
        print(f"Available presets: {', '.join(sorted(presets))}")
        return 1
    if args.e3_disturbance:
        preset = copy.deepcopy(preset)
        preset["objects"] = list(preset.get("objects", []))[:3]
        preset["description"] = (
            f"{preset.get('description', '')} [E3 disturbance: starts with 3; "
            "injects a new object after first release.]"
        )
    if args.e4_disturbance:
        preset = copy.deepcopy(preset)
        preset["objects"] = list(preset.get("objects", []))[:1]
        preset["description"] = (
            f"{preset.get('description', '')} [E4 disturbance: starts with 1; "
            "injects a new object after every continuation cycle.]"
        )

    print(f"\nPreset: {args.preset}")
    print(f"Scene:  {preset.get('description', '')}")
    print("Try:")
    for goal in preset.get("suggested_goals", []):
        print(f"  - {goal}")
    preset_objects = preset.get("objects", [])
    n_preset_objects = len(preset_objects)
    if "world" in cfg and "messy_table" in cfg["world"]:
        cfg["world"]["messy_table"]["n_objects"] = n_preset_objects
        cfg["world"]["messy_table"]["object_positions"] = [
            obj["position"] for obj in preset_objects
        ]
    object_colors = [
        _hex_to_rgba(_PRESET_HEX_COLORS.get(obj["id"], "#888888"))
        for obj in preset_objects
    ]
    cfg.setdefault("world", {}).setdefault("messy_table", {})["object_colors"] = object_colors
    _print_preset_objects(preset)

    state_bridge = None
    if not args.no_monitor:
        import threading
        import time

        from src.monitor.server import command_queue, run_server
        from src.monitor.state_bridge import StateBridge

        monitor_thread = threading.Thread(
            target=run_server,
            kwargs={"host": "127.0.0.1", "port": 7788},
            daemon=True,
        )
        monitor_thread.start()
        time.sleep(1.5)
        state_bridge = StateBridge(preset=preset)

    system = None
    logger = None
    try:
        from src.core.system_factory import build_system
        from src.external.gemini.gemini_interpreter_adapter import (
            GeminiInterpreterAdapter,
        )
        from src.interaction.command_loop import CommandLoop
        from src.interaction.context_aware_interpreter import ContextAwareInterpreter
        from src.interaction.session_logger import SessionLogger
        from src.intentos import IntentOSConfig, IntentOSOrchestrator
        from src.kernel import ExecutionKernel
        from src.planning import IntentPlanner, PlannerConfig

        system = build_system(cfg)
        # TODO: wire to actual PyBullet scene spawning.

        planner_cfg = PlannerConfig(
            llm_enabled=not args.no_llm and bool(cfg.get("gemini", {}).get("enabled", False)),
        )
        kernel = ExecutionKernel(
            phase2_orchestrator=system,
            phase2_auth_manager=system.auth_manager,
            invariant_checker=system.executor._invariant_checker,
        )
        planner = IntentPlanner(
            agent_registry=system.agent_registry,
            cfg=planner_cfg,
        )
        planner._heuristic.set_world_context(system.world_artifacts, system.sim)
        object_ids = system.world_artifacts.object_ids
        label_map = {}
        for i, obj in enumerate(preset_objects):
            if i < len(object_ids):
                label_map[obj["id"]] = object_ids[i]
        planner._heuristic.set_object_labels(label_map)
        if state_bridge is not None:
            state_bridge.set_label_map(label_map)
        intentos = IntentOSOrchestrator(
            kernel=kernel,
            agent_registry=system.agent_registry,
            planner=planner,
            cfg=IntentOSConfig(planner=planner_cfg),
        )
        raw_gemini = getattr(system, "gemini", None)
        gemini_adapter = GeminiInterpreterAdapter(raw_gemini) if raw_gemini else None
        interpreter = ContextAwareInterpreter(gemini_adapter=gemini_adapter)
        if args.e3_disturbance:
            _install_e3_disturbance_hook(system, state_bridge, label_map)
        if args.e4_disturbance:
            _install_e4_disturbance_hook(intentos, system, state_bridge, label_map)

        logger = SessionLogger(preset_name=args.preset)
        loop = CommandLoop(
            orchestrator=intentos,
            world=system,
            logger=logger,
            preset_name=args.preset,
            preset_objects=preset_objects,
            state_bridge=state_bridge,
        )
        loop.set_preset(preset)
        loop.set_label_map(label_map)
        loop.set_interpreter(interpreter)
        if not args.no_monitor:
            loop.set_browser_queue(command_queue)
        loop.run()
        return 0
    except KeyboardInterrupt:
        if logger is not None:
            logger.close()
        print("\nCancelled.")
        return 130
    finally:
        if system is not None:
            system.close()


def _load_yaml(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


_PRESET_HEX_COLORS = {
    "red_block": "#e74c3c",
    "blue_block": "#3498db",
    "yellow_block": "#f1c40f",
    "tool": "#95a5a6",
    "screwdriver": "#7f8c8d",
    "cup": "#ecf0f1",
}


def _hex_to_rgba(hex_color: str) -> list[float]:
    if not hex_color or not hex_color.startswith("#"):
        return [0.7, 0.7, 0.7, 1.0]
    h = hex_color.lstrip("#")
    r = int(h[0:2], 16) / 255
    g = int(h[2:4], 16) / 255
    b = int(h[4:6], 16) / 255
    return [r, g, b, 1.0]


def _print_preset_objects(preset: dict) -> None:
    objects = preset.get("objects", [])
    if not objects:
        return
    print("Objects:")
    for obj in objects:
        print(
            "  - "
            f"{obj.get('label', obj.get('id', 'object'))} "
            f"at {obj.get('position')} "
            f"visible={obj.get('visible', True)}"
        )


def _install_e3_disturbance_hook(system, state_bridge, label_map: dict) -> None:
    """TEMP E3 live experiment: inject one new cube after first release."""
    injected = {"done": False}
    original_release = system.executor._execute_release

    def release_with_injection():
        finished = original_release()
        if finished and not injected["done"]:
            obj_id = _inject_e3_cube(system)
            injected["done"] = True
            label_key = f"e3_injected_{obj_id}"
            label_map[label_key] = obj_id
            if state_bridge is not None and hasattr(state_bridge, "add_object"):
                state_bridge.add_object(
                    object_id=label_key,
                    label="new purple block",
                    body_id=obj_id,
                    color="#9b59b6",
                    x=0.72,
                    y=0.58,
                )
                state_bridge.set_label_map(label_map)
            print(
                f"[E3] Injected new object {obj_id} after first release. "
                "The persistence loop should pick it up next cycle."
            )
        return finished

    system.executor._execute_release = release_with_injection
    print("[E3] Disturbance hook enabled: will inject one object after first release.")


def _install_e4_disturbance_hook(intentos, system, state_bridge, label_map: dict) -> None:
    """TEMP E4 live experiment: inject one new cube after each objective cycle."""
    injected_ids: list[int] = []
    original_continue = intentos.continue_confirmed_objective

    def continue_with_injection(live_scene, abandoned_object_ids, *args, **kwargs):
        result = original_continue(live_scene, abandoned_object_ids, *args, **kwargs)
        if result.accepted and result.outcomes:
            obj_id = _inject_e4_cube(system, len(injected_ids))
            injected_ids.append(obj_id)
            label_key = f"e4_injected_{obj_id}"
            label_map[label_key] = obj_id
            if state_bridge is not None and hasattr(state_bridge, "add_object"):
                state_bridge.add_object(
                    object_id=label_key,
                    label=f"new block {len(injected_ids)}",
                    body_id=obj_id,
                    color=_E4_MONITOR_COLORS[(len(injected_ids) - 1) % len(_E4_MONITOR_COLORS)],
                    x=0.68 - 0.08 * ((len(injected_ids) - 1) % 3),
                    y=0.58 + 0.08 * (((len(injected_ids) - 1) // 3) % 2),
                )
                state_bridge.set_label_map(label_map)
            print(
                f"[E4] Injected new object {obj_id} after continuation "
                f"cycle {len(injected_ids)}."
            )
        return result

    intentos.continue_confirmed_objective = continue_with_injection
    print(
        "[E4] Disturbance hook enabled: starts with 1 object; "
        "will inject after every continuation cycle."
    )


def _inject_e3_cube(
    system,
    pos=(0.24, -0.16, 0.66),
    color=(0.7, 0.1, 0.8, 1.0),
) -> int:
    import pybullet as p

    client = system.sim.client
    size = 0.03
    collision = p.createCollisionShape(
        p.GEOM_BOX,
        halfExtents=[size] * 3,
        physicsClientId=client,
    )
    visual = p.createVisualShape(
        p.GEOM_BOX,
        halfExtents=[size] * 3,
        rgbaColor=color,
        physicsClientId=client,
    )
    obj_id = p.createMultiBody(
        baseMass=0.08,
        baseCollisionShapeIndex=collision,
        baseVisualShapeIndex=visual,
        basePosition=list(pos),
        physicsClientId=client,
    )
    p.changeDynamics(
        obj_id,
        -1,
        lateralFriction=1.5,
        spinningFriction=0.1,
        rollingFriction=0.05,
        restitution=0.1,
        contactStiffness=10000,
        contactDamping=100,
        physicsClientId=client,
    )
    system.world_artifacts.object_ids.append(obj_id)
    system.executor.set_world_objects(system.world_artifacts.object_ids)
    return obj_id


_E4_INJECTION_POSITIONS = [
    (0.22, -0.16, 0.66),
    (0.05, -0.16, 0.66),
    (-0.18, -0.14, 0.66),
    (0.24, 0.16, 0.66),
    (-0.24, 0.16, 0.66),
]

_E4_INJECTION_COLORS = [
    (0.7, 0.1, 0.8, 1.0),
    (0.1, 0.7, 0.8, 1.0),
    (0.8, 0.4, 0.1, 1.0),
    (0.2, 0.8, 0.2, 1.0),
    (0.8, 0.8, 0.1, 1.0),
]

_E4_MONITOR_COLORS = [
    "#9b59b6",
    "#1abc9c",
    "#e67e22",
    "#2ecc71",
    "#f1c40f",
]


def _inject_e4_cube(system, index: int) -> int:
    pos = _E4_INJECTION_POSITIONS[index % len(_E4_INJECTION_POSITIONS)]
    color = _E4_INJECTION_COLORS[index % len(_E4_INJECTION_COLORS)]
    return _inject_e3_cube(system, pos=pos, color=color)


if __name__ == "__main__":
    raise SystemExit(main())
