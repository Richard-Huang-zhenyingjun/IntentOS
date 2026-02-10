#!/usr/bin/env python3
"""
Main demo entry point.

SELECT -> PROPOSE -> CONFIRM -> EXECUTE
"""

import argparse
import json
import logging
import sys
import time
import traceback
from pathlib import Path
from dataclasses import asdict

import numpy as np
import pybullet as p
import yaml

# Add parent directory so src can be imported as a package
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.diag import (
    format_diagnostic_report,
    print_startup_banner,
    run_startup_diagnostics,
    validate_world_spawn,
)
from src.core.system_factory import build_system
from src.core.metrics import MetricsCollector
from src.core.perf import FrameTiming, PerfMonitor
from src.input.source_keyboard import KeyboardSource
from src.ui.overlay import DebugOverlay
from src.worlds.messy_table_world import reset_world

CONTROL_BOX = """
╔════════════════════════════════════════╗
║   INTENT-AUTHORIZED ARM CONTROL        ║
╠════════════════════════════════════════╣
║  L — Lock target (SELECT)              ║
║  C — Confirm action (EXECUTE)          ║
║  X — Cancel action                     ║
║  R — Reset world                       ║
║  Q — Quit                              ║
╚════════════════════════════════════════╝
""".strip("\n")

OVERLAY_UPDATE_INTERVAL = 15  # ~4 Hz at 60 FPS


def print_session_summary(metrics):
    print("\n" + "=" * 50)
    print("SESSION SUMMARY")
    print("=" * 50)
    print(f"Duration: {metrics.total_execution_time:.1f}s")
    print(f"Objects cleaned: {metrics.objects_succeeded}/{metrics.objects_attempted}")
    print(
        f"Success rate: "
        f"{metrics.objects_succeeded / max(1, metrics.objects_attempted) * 100:.1f}%"
    )
    print(f"Avg time per object: {metrics.avg_time_per_object:.1f}s")
    print(
        f"\nProposals: {metrics.proposals_generated} generated, "
        f"{metrics.proposals_confirmed} confirmed, "
        f"{metrics.proposals_cancelled} cancelled"
    )
    print(
        f"\nTrust events: {metrics.trust_penalties} penalties, "
        f"{metrics.trust_recoveries} recoveries"
    )
    print(f"Trust range: {metrics.min_trust:.2f} - {metrics.max_trust:.2f}")
    print(f"Re-auth events: {metrics.reauth_events}")
    print(
        f"\nFailures: {metrics.timeout_aborts} timeouts, "
        f"{metrics.grasp_failures} grasp fails, "
        f"{metrics.unreachable_skips} unreachable"
    )
    print(f"\n{'=' * 50}")
    print(f"SAFETY INVARIANT: false_executions = {metrics.false_executions}")
    print(f"{'=' * 50}\n")

    assert metrics.false_executions == 0, "CRITICAL: Safety invariant violated!"


def _configure_logging(level_name: str):
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(level=level, format="[%(levelname)s] %(message)s")


def _load_config(config_path: str) -> dict:
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def _apply_overrides(config: dict, headless: bool, gui: bool, seed: int | None):
    config.setdefault("simulator", {})
    if gui:
        config["simulator"]["use_gui"] = True
    elif headless:
        config["simulator"]["use_gui"] = False

    if seed is not None:
        config.setdefault("world", {})
        config["world"].setdefault("messy_table", {})
        config["world"]["messy_table"]["seed"] = seed


def _extract_keyboard_source(orch) -> KeyboardSource | None:
    if hasattr(orch, "decision_pipeline") and hasattr(orch.decision_pipeline, "router"):
        source = orch.decision_pipeline.router.get_source("keyboard")
        if isinstance(source, KeyboardSource):
            return source
    return None


def _next_uncleaned_object_id(orch) -> int | None:
    artifacts = getattr(orch, "world_artifacts", None)
    if artifacts is None or not artifacts.object_ids:
        return None
    center = np.array(artifacts.bin_zone_center)
    radius = artifacts.bin_zone_radius
    for obj_id in artifacts.object_ids:
        try:
            pos = np.array(p.getBasePositionAndOrientation(obj_id)[0])
        except Exception:
            continue
        if np.linalg.norm(pos[:2] - center[:2]) > radius:
            return obj_id
    return None


def _is_triggered(keys: dict, low: str, up: str) -> bool:
    return (
        (ord(low) in keys and keys[ord(low)] & p.KEY_WAS_TRIGGERED)
        or (ord(up) in keys and keys[ord(up)] & p.KEY_WAS_TRIGGERED)
    )


def _is_pressed_or_triggered(keys: dict, low: str, up: str) -> bool:
    mask = p.KEY_WAS_TRIGGERED | p.KEY_IS_DOWN
    return (
        (ord(low) in keys and keys[ord(low)] & mask)
        or (ord(up) in keys and keys[ord(up)] & mask)
    )


def _count_objects_in_bin(orch) -> int:
    artifacts = getattr(orch, "world_artifacts", None)
    if artifacts is None or not artifacts.object_ids:
        return 0

    center = np.array(artifacts.bin_zone_center)
    radius = artifacts.bin_zone_radius
    count = 0

    for obj_id in artifacts.object_ids:
        try:
            pos = np.array(p.getBasePositionAndOrientation(obj_id)[0])
        except Exception:
            continue
        if np.linalg.norm(pos[:2] - center[:2]) <= radius:
            count += 1

    return count


def _flush_events(orch):
    events = getattr(orch, "events", None)
    if events is not None and hasattr(events, "flush"):
        events.flush()
    if events is not None and hasattr(events, "close"):
        events.close()


def _build_orchestrator_or_exit(config: dict):
    orch = build_system(config)
    world_report = validate_world_spawn(orch)
    print(format_diagnostic_report(world_report, "Runtime World Diagnostics"))
    if world_report.errors:
        orch.close()
        raise RuntimeError("World diagnostics failed; cannot start demo.")
    return orch


def _reset_trust_engine(orch):
    trust = getattr(orch, "trust_engine", None)
    if trust is None:
        return
    trust._task_trust = trust.init_trust
    trust._consecutive_failures = 0
    trust._history = []
    trust._current_object_index = 0
    trust._session_active = False
    trust._auth_quality = 1.0


def _reset_executor(orch):
    executor = getattr(orch, "executor", None)
    if executor is None:
        return
    executor.active_plan = []
    executor.plan_index = 0
    executor.active_primitive_started = False
    try:
        from src.execution.primitive_executor import ExecutorStatus
        executor.status = ExecutorStatus.IDLE
    except Exception:
        pass


def _controlled_world_reset(orch, config: dict, seed: int | None = None):
    # Cancel any active grasp/constraint before deleting objects.
    if getattr(orch, "grasp", None) is not None and orch.grasp.is_holding():
        try:
            orch.grasp.detach()
        except Exception:
            pass

    # Reset world bodies and arm pose.
    orch.world_artifacts = reset_world(
        sim=orch.sim,
        config=config,
        previous_artifacts=orch.world_artifacts,
        seed=seed,
    )

    # Reset orchestrator state and safety/authorization context.
    orch.state_machine.reset()  # IDLE
    orch.current_proposal = None
    orch.current_scene = None
    orch._current_execution_plan = None
    orch._current_object_index = 0
    orch._safe_pause_primitives = []
    orch._safe_pause_active = False
    orch._awaiting_reauth = False
    orch._awaiting_object_confirm = False

    # Invalidate any active authorization token.
    if getattr(orch, "auth_manager", None) is not None and orch.auth_manager.get_active_token_id():
        orch.auth_manager.invalidate("world_reset")

    # Clear trust engine state to initial trust baseline.
    _reset_trust_engine(orch)

    # Reset execution/tracking state.
    _reset_executor(orch)


def main() -> int:
    parser = argparse.ArgumentParser(description="Intent Interface Demo")
    parser.add_argument("--config", default="configs/default.yaml", help="Config file")
    parser.add_argument("--gui", action="store_true", help="Force GUI mode")
    parser.add_argument("--headless", action="store_true", help="Run without GUI")
    parser.add_argument("--seed", type=int, default=None, help="Override world random seed")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING"],
        help="Logging verbosity",
    )
    parser.add_argument(
        "--export-metrics",
        action="store_true",
        help="Export finalized session metrics to JSON",
    )
    parser.add_argument(
        "--auto-confirm-n",
        type=int,
        default=0,
        help="Automatically emit confirm pulses for first N confirmation attempts",
    )
    parser.add_argument(
        "--n-objects",
        type=int,
        default=None,
        help="Override number of spawned table objects",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=4000,
        help="Hard stop for unattended runs",
    )
    parser.add_argument(
        "--metrics-path",
        default=None,
        help="Optional explicit path for metrics JSON export",
    )
    parser.add_argument(
        "--events-path",
        default=None,
        help="Optional explicit path for JSONL event log",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Enable per-frame performance profiling",
    )
    args = parser.parse_args()

    _configure_logging(args.log_level)
    print_startup_banner()

    try:
        config = _load_config(args.config)
    except Exception as exc:
        print(f"[DEMO] Failed to load config '{args.config}': {exc}")
        return 1

    _apply_overrides(config, args.headless, args.gui, args.seed)
    if args.auto_confirm_n > 0:
        config.setdefault("input", {})
        config["input"]["confirm_hold_frames"] = 1
        config["input"]["debounce_frames"] = 0
    if args.events_path:
        config.setdefault("logging", {})
        config["logging"]["events_enabled"] = True
        config["logging"]["events_path"] = args.events_path
    if args.n_objects is not None:
        config.setdefault("world", {})
        config["world"].setdefault("messy_table", {})
        config["world"]["messy_table"]["n_objects"] = args.n_objects

    startup_report = run_startup_diagnostics(config)
    print(format_diagnostic_report(startup_report, "Startup Diagnostics"))
    if startup_report.errors:
        print("[DEMO] Startup diagnostics reported errors. Exiting safely.")
        return 1

    print(CONTROL_BOX)

    orch = None
    overlay = None
    keyboard_source = None
    last_snapshot = None
    total_frames = 0
    start_time = time.time()
    metrics = MetricsCollector()
    perf_monitor = PerfMonitor(enabled=args.profile)
    auto_confirm_used = 0
    auto_confirm_cooldown = 0
    auto_mode = args.auto_confirm_n > 0

    try:
        orch = _build_orchestrator_or_exit(config)
        keyboard_source = _extract_keyboard_source(orch)
        overlay_enabled = config.get("ui", {}).get("show_overlay", True)
        overlay = None if args.headless or not overlay_enabled else DebugOverlay()
        if not args.headless:
            p.resetDebugVisualizerCamera(
                cameraDistance=1.5,
                cameraYaw=45,
                cameraPitch=-30,
                cameraTargetPosition=[0.0, 0.0, 0.3],
            )
        if auto_mode:
            next_id = _next_uncleaned_object_id(orch)
            if next_id is not None:
                orch.force_lock_target(next_id)
        if getattr(orch, "events", None) is not None and hasattr(orch.events, "on"):
            from src.core.events import EventType
            for event_type in EventType:
                orch.events.on(
                    event_type,
                    lambda et, data: metrics.process_event(
                        {"type": getattr(et, "value", str(et)), "data": data}
                    ),
                )

        if not args.headless:
            print("\n[DEMO] Click the PyBullet window to focus keyboard input.")
            print("[DEMO] Starting in 2 seconds...")
            time.sleep(2)

        while True:
            frame_start = time.perf_counter()
            keys = p.getKeyboardEvents() if not args.headless else {}

            auto_confirm = False
            if auto_mode and keyboard_source is not None and auto_confirm_used < args.auto_confirm_n:
                state = getattr(getattr(orch, "state_machine", None), "state", None)
                if auto_confirm_cooldown > 0:
                    auto_confirm_cooldown -= 1
                elif state is not None and state.value in ("idle", "confirming"):
                    auto_confirm = True
                    auto_confirm_used += 1
                    auto_confirm_cooldown = 8

            if keyboard_source is not None:
                keyboard_source.set_key_state(
                    confirm=auto_confirm or _is_pressed_or_triggered(keys, "c", "C"),
                    cancel=_is_pressed_or_triggered(keys, "x", "X"),
                )

            perf_monitor.start("orchestrator")
            last_snapshot = orch.step()
            orchestrator_ms = perf_monitor.end("orchestrator")
            total_frames += 1
            perf_monitor.start("metrics")
            metrics.process_snapshot(last_snapshot)
            metrics_ms = perf_monitor.end("metrics")

            if _is_triggered(keys, "l", "L"):
                if orch.world_artifacts and orch.world_artifacts.object_ids:
                    orch.force_lock_target(orch.world_artifacts.object_ids[0])
                    print("[DEMO] Target locked.")
                else:
                    print("[DEMO] No lockable target found.")

            if _is_triggered(keys, "r", "R"):
                print("[DEMO] Reset requested. Resetting world in place...")
                _controlled_world_reset(orch, config, seed=args.seed)
                world_report = validate_world_spawn(orch)
                print(format_diagnostic_report(world_report, "Runtime World Diagnostics (Post-Reset)"))
                if world_report.errors:
                    raise RuntimeError("Post-reset world diagnostics failed.")
                print("[DEMO] Reset complete.")
                continue

            if _is_triggered(keys, "q", "Q"):
                print("[DEMO] Quit requested.")
                break

            overlay_ms = 0.0
            if overlay is not None and total_frames % OVERLAY_UPDATE_INTERVAL == 0:
                perf_monitor.start("overlay")
                overlay.render(last_snapshot)
                overlay_ms = perf_monitor.end("overlay")

            total_ms = (time.perf_counter() - frame_start) * 1000.0
            physics_ms = max(0.0, total_ms - orchestrator_ms - overlay_ms - metrics_ms)
            perf_monitor.record_frame(
                FrameTiming(
                    frame_num=total_frames,
                    total_ms=total_ms,
                    orchestrator_ms=orchestrator_ms,
                    overlay_ms=overlay_ms,
                    metrics_ms=metrics_ms,
                    physics_ms=physics_ms,
                )
            )

            if last_snapshot.false_executions > 0:
                print("\n[DEMO] CRITICAL: false_executions > 0. Stopping session.")
                break

            if auto_mode and orch is not None and last_snapshot is not None:
                artifacts = getattr(orch, "world_artifacts", None)
                total_objects = len(artifacts.object_ids) if artifacts is not None else 0
                cleaned = _count_objects_in_bin(orch)

                # Continue unattended multi-object cycle by resetting/locking after DONE.
                if last_snapshot.state.value == "done":
                    next_id = _next_uncleaned_object_id(orch)
                    if next_id is not None and auto_confirm_used < args.auto_confirm_n:
                        orch.state_machine.reset()
                        orch.force_lock_target(next_id)
                    else:
                        print("[DEMO] Auto mode complete: DONE reached.")
                        break

                if total_objects > 0 and cleaned >= total_objects:
                    print("[DEMO] Auto mode complete: all objects cleaned.")
                    break

                if auto_confirm_used >= args.auto_confirm_n and last_snapshot.state.value in ("idle", "selecting", "done"):
                    print("[DEMO] Auto mode complete: confirm budget exhausted.")
                    break

            if total_frames >= args.max_frames:
                print(f"[DEMO] Max frames reached ({args.max_frames}). Exiting.")
                break

            time.sleep(1.0 / 60.0)

    except KeyboardInterrupt:
        print("\nShutdown requested by user.")
    except Exception as exc:
        print(f"\nCRITICAL ERROR: {exc}", file=sys.stderr)
        traceback.print_exc()
        print("\nAttempting graceful shutdown...")
        return 1
    finally:
        elapsed = time.time() - start_time
        finalized = metrics.finalize()
        # Keep definitive safety value from latest snapshot if present.
        if last_snapshot is not None:
            finalized.false_executions = int(last_snapshot.false_executions)
        objects_cleaned = _count_objects_in_bin(orch) if orch is not None else 0
        false_executions = last_snapshot.false_executions if last_snapshot is not None else "n/a"

        if orch is not None:
            _flush_events(orch)
            try:
                orch.close()
            except Exception:
                pass

        print("\n" + "=" * 60)
        print("[DEMO] Session Summary")
        print("=" * 60)
        print(f"[DEMO] Execution time: {elapsed:.2f}s")
        print(f"[DEMO] Frames processed: {total_frames}")
        print(f"[DEMO] Objects cleaned (in bin zone): {objects_cleaned}")
        print(f"[DEMO] false_executions: {false_executions}")
        print_session_summary(finalized)
        if args.profile:
            summary = perf_monitor.summary()
            print("\n=== PERFORMANCE SUMMARY ===")
            print(f"Frames sampled: {int(summary['frames'])}")
            print(f"Orchestrator: {summary['orchestrator_p50_ms']:.2f}ms (p50)")
            print(f"Overlay: {summary['overlay_p50_ms']:.2f}ms (p50)")
            print(f"Metrics: {summary['metrics_p50_ms']:.2f}ms (p50)")
            print(f"Physics/other: {summary['physics_p50_ms']:.2f}ms (p50)")
            print(f"Total frame: {summary['total_p50_ms']:.2f}ms (p50)")
            print(f"Total frame: {summary['total_p95_ms']:.2f}ms (p95)")
            print("Target: <16.67ms for 60 FPS")
        if args.export_metrics:
            metrics_path = args.metrics_path or f"metrics_{finalized.session_id}.json"
            total_objects = 0
            if orch is not None and getattr(orch, "world_artifacts", None) is not None:
                total_objects = len(orch.world_artifacts.object_ids)
            payload = asdict(finalized)
            payload["objects_cleaned_in_bin"] = objects_cleaned
            payload["objects_total"] = total_objects
            payload["success_rate"] = objects_cleaned / max(1, total_objects)
            with open(metrics_path, "w") as f:
                json.dump(payload, f, indent=2)
            print(f"[DEMO] Metrics exported to {metrics_path}")
        print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
