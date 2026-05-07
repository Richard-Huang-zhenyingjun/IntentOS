#!/usr/bin/env python3
"""
IntentOS demo script.

Full pipeline:
  1. Start the Phase 2 simulation through system_factory
  2. Submit a human goal to IntentOS
  3. Plan with Gemini or deterministic heuristic fallback
  4. Confirm from the console
  5. Execute through the IntentOS kernel/agent path
  6. Print final safety and memory results

Usage:
    python scripts/run_intentos_demo.py
    python scripts/run_intentos_demo.py --goal "clean the table"
    python scripts/run_intentos_demo.py --goal "home" --no-llm
    python scripts/run_intentos_demo.py --config configs/real_arm.yaml
"""
from __future__ import annotations

import argparse
import copy
import logging
import sys
import time
from pathlib import Path
from typing import Any, Optional

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger("intentos_demo")


class DemoPlannerAdapter:
    """
    Wraps IntentPlanner and concretizes demo-friendly symbolic targets.

    The IntentOS heuristic planner deliberately emits high-level parameters
    such as ``target=nearest_object``. The current ArmAgent executes Phase 2
    primitives, which need concrete ``target_xyz`` coordinates for reach/move
    primitives. This adapter is demo glue only; it leaves planner code clean.
    """

    def __init__(self, planner: Any, system: Any, cfg: dict):
        self._planner = planner
        self._system = system
        self._cfg = cfg

    def plan(self, goal: str, scene_summary: str):
        result = self._planner.plan(goal, scene_summary)
        _concretize_task_graph_for_demo(result.graph, self._system, self._cfg)
        return result


def run_demo(goal: str, no_llm: bool, config_path: str, timeout_s: float) -> int:
    from src.core.system_factory import build_system
    from src.intentos import IntentOSConfig, IntentOSOrchestrator
    from src.kernel import KernelEvent
    from src.planning import IntentPlanner, PlannerConfig
    from src.world_model.system_memory import SystemMemory

    cfg = _load_config(config_path)
    _apply_demo_overrides(cfg, no_llm)

    print("\n" + "=" * 60)
    print("  IntentOS Demo")
    print("=" * 60)
    print(f"  Config:  {config_path}")
    print(f"  LLM:     {'disabled' if no_llm else 'enabled if configured'}")
    print(f"  Goal:    {goal!r}")
    print("=" * 60 + "\n")

    system = None
    memory = SystemMemory()
    memory.increment_session()
    final_status: dict[str, Any] = {}
    final_state = "ERROR"
    start = time.monotonic()

    try:
        print("Starting Phase 2 system...")
        system = build_system(cfg)

        goal_type = _classify_goal(goal)
        preferred_source = memory.preferred_plan_source(goal_type)
        if preferred_source:
            print(
                "System memory: preferred plan source for "
                f"{goal_type!r} is {preferred_source!r}"
            )

        planner_cfg = PlannerConfig(
            llm_enabled=not no_llm and bool(cfg.get("gemini", {}).get("enabled", False)),
            llm_timeout_s=_gemini_timeout_s(cfg),
        )
        base_planner = IntentPlanner(
            agent_registry=system.agent_registry,
            cfg=planner_cfg,
            gemini_adapter=getattr(system, "gemini", None),
        )
        planner = DemoPlannerAdapter(base_planner, system, cfg)

        intentos = IntentOSOrchestrator(
            kernel=system.execution_kernel,
            agent_registry=system.agent_registry,
            planner=planner,
            cfg=IntentOSConfig(planner=planner_cfg, log_execution_steps=True),
            coordinator=getattr(system, "agent_coordinator", None),
        )

        scene_summary = _get_scene_summary(system)
        print(f"\nSubmitting goal: {goal!r}")
        print(f"Scene summary: {scene_summary}")
        if not intentos.submit_goal(goal, scene_summary):
            print("Goal rejected: IntentOS is not idle.")
            return 1

        print("\nRunning. Press Ctrl+C to cancel.\n")
        prompted_for_state = False
        while True:
            intentos.tick()
            final_status = intentos.get_status()
            final_state = final_status["intentos_state"]

            if final_state == "AWAITING_CONFIRM" and not prompted_for_state:
                prompted_for_state = True
                if not _handle_confirmation_prompt(intentos, final_status, KernelEvent):
                    final_state = "ABORTED"
                    break
            elif final_state != "AWAITING_CONFIRM":
                prompted_for_state = False

            if final_state in ("COMPLETE", "ABORTED", "ERROR"):
                break

            if time.monotonic() - start > timeout_s:
                print(f"\nTimed out after {timeout_s:.0f}s; cancelling.")
                intentos.cancel()
                final_status = intentos.get_status()
                final_state = final_status["intentos_state"]
                break

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nCancelled by user.")
        final_state = "ABORTED"
    finally:
        duration = time.monotonic() - start
        if system is not None:
            try:
                final_status = final_status or system.intentos.get_status()
            except Exception:
                pass
            try:
                system.close()
            except Exception:
                pass

        plan_source = final_status.get("plan_source", "unknown")
        success = final_state == "COMPLETE"
        memory.record_plan_outcome(
            goal_type=_classify_goal(goal),
            plan_source=plan_source,
            success=success,
        )

        print("\n" + "=" * 60)
        print(f"  Result: {final_state}")
        print(f"  Duration: {duration:.1f}s")
        if "nodes_complete" in final_status:
            print(
                "  Steps: "
                f"{final_status['nodes_complete']}/{final_status.get('nodes_total', '?')}"
            )
        print(f"  Plan source: {plan_source}")
        print(f"  Planning time: {final_status.get('planning_ms', 0):.0f}ms")
        print(f"  false_executions: {final_status.get('false_executions', 0)}")
        print(f"  Memory sessions: {memory.summary()['session_count']}")
        print("=" * 60 + "\n")

    return 0 if final_state == "COMPLETE" else 1


def _handle_confirmation_prompt(intentos: Any, status: dict, kernel_event_cls: Any) -> bool:
    """Display confirmation prompt and inject a console confirmation event."""
    print("\n" + "-" * 60)
    print("  Waiting for confirmation.")
    print(f"  Plan source: {status.get('plan_source', '?')}")
    print(f"  Steps: {status.get('nodes_total', '?')}")
    print(f"  Segments: {status.get('current_segment_idx', 0) + 1}/"
          f"{status.get('segments_total', '?')}")
    print("  Press ENTER to confirm, or type 'x' to cancel.")
    print("-" * 60)
    try:
        choice = input("  > ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        intentos.cancel()
        return False

    if choice == "x":
        intentos.cancel()
        print("  Cancelled.")
        return False

    event = kernel_event_cls(
        kind="confirmed",
        proposal_id=None,
        agent_id=None,
        timestamp_ms=time.time() * 1000.0,
        details={"source": "demo_keyboard"},
    )
    # Console demo bridge: Phase 2 still owns real keyboard/EEG decisions; this
    # script injects a kernel-level confirmation after explicit terminal input.
    intentos._react_to_events([event])
    print("  Confirmed. Executing...")
    return True


def _load_config(config_path: str) -> dict:
    with open(config_path, "r") as f:
        return yaml.safe_load(f) or {}


def _apply_demo_overrides(cfg: dict, no_llm: bool) -> None:
    cfg.setdefault("simulator", {})
    cfg["simulator"]["use_gui"] = False
    cfg.setdefault("ui", {})
    cfg["ui"]["show_overlay"] = False
    if no_llm:
        cfg.setdefault("gemini", {})
        cfg["gemini"]["enabled"] = False
    cfg.setdefault("openvla", {})
    cfg["openvla"]["enabled"] = False


def _gemini_timeout_s(cfg: dict) -> float:
    gemini = cfg.get("gemini", {})
    if "timeout_sec" in gemini:
        return float(gemini["timeout_sec"])
    if "timeout_ms" in gemini:
        return float(gemini["timeout_ms"]) / 1000.0
    return 10.0


def _get_scene_summary(system: Any) -> str:
    artifacts = getattr(system, "world_artifacts", None)
    object_ids = list(getattr(artifacts, "object_ids", []) or [])
    if object_ids:
        return f"{len(object_ids)} objects on table"
    return "Table scene (details unavailable)"


def _classify_goal(goal: str) -> str:
    goal_lower = goal.lower()
    if any(word in goal_lower for word in ("clean", "clear", "tidy")):
        return "clean_table"
    if "home" in goal_lower:
        return "home"
    return "generic"


def _concretize_task_graph_for_demo(graph: Any, system: Any, cfg: dict) -> None:
    """Fill in target_xyz/object_id fields needed by the Phase 2 arm adapter."""
    target_obj_id, target_pos = _first_object(system)
    safe_home = _safe_home_xyz(cfg)
    bin_center = _bin_center(cfg)
    approach_height = float(
        cfg.get("planning", {}).get("clean_table", {}).get("approach_height", 0.10)
    )
    bin_hover = float(
        cfg.get("planning", {}).get("clean_table", {}).get("bin_hover_height", 0.12)
    )

    for node in getattr(graph, "nodes", []) or []:
        params = node.parameters
        action = node.action_type

        if action == "home":
            params.setdefault("target_xyz", safe_home)
        elif action == "reach":
            if "target_xyz" not in params:
                base = target_pos or safe_home
                params["target_xyz"] = [base[0], base[1], base[2] + approach_height]
            if target_obj_id is not None:
                params.setdefault("object_id", target_obj_id)
        elif action in ("move", "move_to"):
            if "target_xyz" not in params:
                params["target_xyz"] = [
                    bin_center[0],
                    bin_center[1],
                    bin_center[2] + bin_hover,
                ]
            if target_obj_id is not None:
                params.setdefault("object_id", target_obj_id)
        elif action in ("grasp", "release") and target_obj_id is not None:
            params.setdefault("object_id", target_obj_id)


def _first_object(system: Any) -> tuple[Optional[int], Optional[list[float]]]:
    artifacts = getattr(system, "world_artifacts", None)
    object_ids = list(getattr(artifacts, "object_ids", []) or [])
    if not object_ids:
        return None, None
    obj_id = int(object_ids[0])
    try:
        import pybullet as p

        pos = list(p.getBasePositionAndOrientation(obj_id)[0])
        return obj_id, pos
    except Exception:
        return obj_id, None


def _safe_home_xyz(cfg: dict) -> list[float]:
    return list(
        copy.deepcopy(
            cfg.get("planning", {})
            .get("clean_table", {})
            .get("safe_home_xyz", [0.3, 0.0, 0.8])
        )
    )


def _bin_center(cfg: dict) -> list[float]:
    return list(
        copy.deepcopy(
            cfg.get("world", {})
            .get("messy_table", {})
            .get("bin_zone_center", [0.4, 0.0, 0.75])
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="IntentOS Demo")
    parser.add_argument("--goal", default="clean the table", help="Goal to execute")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM")
    parser.add_argument(
        "--config",
        default="configs/default.yaml",
        help="Config file path",
    )
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=120.0,
        help="Maximum demo runtime before cancellation",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )
    return run_demo(args.goal, args.no_llm, args.config, args.timeout_s)


if __name__ == "__main__":
    raise SystemExit(main())
