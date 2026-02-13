#!/usr/bin/env python3
"""
OpenVLA Intent-Authorized Manipulation Demo.

Runs the integrated pipeline:
  1. Simulator + world load
  2. OpenVLA proposer proposes
  3. Confirm (auto or interactive)
  4. Authorization token issued
  5. Execution via compiler + executor
  6. Trust updates
  7. Metrics and invariant summary
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from typing import Optional

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.system_factory import build_system, load_config
from src.input.types import DecisionFrame, DecisionIntent, SourceType


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OpenVLA Intent-Authorized Demo")
    parser.add_argument("--seed", type=int, default=42, help="World random seed")
    parser.add_argument("--auto-confirm", action="store_true", help="Auto-confirm each proposal")
    parser.add_argument("--headless", action="store_true", help="Run without GUI")
    parser.add_argument("--max-frames", type=int, default=2000, help="Frame budget")
    parser.add_argument("--export-metrics", action="store_true", help="Write metrics JSON")
    parser.add_argument("--log-level", default="INFO", help="Python log level")
    return parser.parse_args()


def _build_config(args: argparse.Namespace) -> dict:
    config = load_config("configs/default.yaml")
    config.setdefault("simulator", {})
    config["simulator"]["use_gui"] = not args.headless

    config.setdefault("world", {})
    config["world"].setdefault("messy_table", {})
    config["world"]["messy_table"]["seed"] = args.seed

    config.setdefault("gemini", {})
    config["gemini"]["enabled"] = False
    config.setdefault("eeg", {})
    config["eeg"]["enabled"] = False

    config.setdefault("openvla", {})
    config["openvla"]["enabled"] = True
    config["openvla"]["use_fake"] = True

    config.setdefault("logging", {})
    config["logging"]["events_enabled"] = True
    config["logging"]["events_path"] = f"demo_artifacts/openvla_demo_seed{args.seed}.jsonl"
    return config


def _decision_confirm(frame_number: int) -> DecisionFrame:
    return DecisionFrame(
        intent=DecisionIntent.CONFIRM,
        source_type=SourceType.TEST,
        quality=1.0,
        frame_number=frame_number,
    )


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("openvla_demo")
    np.random.seed(args.seed)

    print("=" * 70)
    print("INTENT-AUTHORIZED ROBOTIC MANIPULATION DEMO")
    print("OpenVLA + Authorization + Trust")
    print("=" * 70)
    print(f"Seed: {args.seed}")
    print(f"Mode: {'auto-confirm' if args.auto_confirm else 'interactive-confirm'}")
    print(f"GUI: {'off' if args.headless else 'on'}")
    print(f"Max frames: {args.max_frames}")
    print()

    os.makedirs("demo_artifacts", exist_ok=True)
    config = _build_config(args)
    orch = build_system(config)

    # Kick off selection by locking a target.
    if orch.world_artifacts and orch.world_artifacts.object_ids:
        orch.force_lock_target(orch.world_artifacts.object_ids[0])

    total_proposals = 0
    total_confirms = 0
    total_rejects = 0
    last_proposal_frame: Optional[int] = None
    start = time.time()

    try:
        for _ in range(args.max_frames):
            snapshot = orch.step()

            # Track OpenVLA proposal appearances in CONFIRMING.
            if (
                snapshot.state.value == "confirming"
                and orch.current_proposal is not None
                and orch.current_proposal.source == "openvla"
                and snapshot.frame_count != last_proposal_frame
            ):
                total_proposals += 1
                last_proposal_frame = snapshot.frame_count
                meta = orch.current_proposal.metadata or {}
                logger.info(
                    "Proposal frame=%d instruction=%s delta=%s",
                    snapshot.frame_count,
                    meta.get("instruction", ""),
                    meta.get("delta_position"),
                )

            # Interactive/auto confirmation gate when waiting in CONFIRMING.
            if snapshot.state.value == "confirming" and orch.current_proposal is not None:
                if args.auto_confirm:
                    orch._handle_confirm(_decision_confirm(snapshot.frame_count))
                    total_confirms += 1
                else:
                    response = input("Confirm proposal? [y/N]: ").strip().lower()
                    if response in ("y", "yes"):
                        orch._handle_confirm(_decision_confirm(snapshot.frame_count))
                        total_confirms += 1
                    else:
                        orch.state_machine.reset()
                        total_rejects += 1

            # Physics sanity guard.
            arm = orch.sim.get_arm_state()
            joints = np.asarray(arm.joint_positions, dtype=float)
            if not np.all(np.isfinite(joints)):
                logger.error("Non-finite joint state detected at frame=%d", snapshot.frame_count)
                break

            # Keep running even if scene summary temporarily reports no on-table
            # objects. Some environments need additional frames before stable
            # object visibility/segmentation.

        elapsed = time.time() - start
        final_metrics = orch.metrics.finalize()
        inv = orch.executor.invariant_summary if hasattr(orch.executor, "invariant_summary") else {}

        print()
        print("=" * 70)
        print("SESSION SUMMARY")
        print("=" * 70)
        print(f"Duration: {elapsed:.1f}s")
        print(f"Frames: {orch.global_frame_counter}")
        print(f"OpenVLA proposals seen: {total_proposals}")
        print(f"Confirms: {total_confirms}")
        print(f"Rejects: {total_rejects}")
        print(f"Task trust: {orch.trust_engine.task_trust:.3f}")
        print(f"False executions (trust metrics): {orch.trust_metrics.false_executions}")
        print(f"False executions (executor invariant): {inv.get('false_executions', 'n/a')}")
        print(f"Invariant holds: {inv.get('invariant_holds', True)}")
        print()

        if hasattr(orch.executor, "_invariant_checker"):
            orch.executor._invariant_checker.assert_invariant()  # hard fail if violated

        if args.export_metrics:
            export = {
                "seed": args.seed,
                "auto_confirm": bool(args.auto_confirm),
                "headless": bool(args.headless),
                "elapsed_s": elapsed,
                "frames": orch.global_frame_counter,
                "proposals_seen": total_proposals,
                "confirms": total_confirms,
                "rejects": total_rejects,
                "task_trust": orch.trust_engine.task_trust,
                "executor_invariant": inv,
                "collector_metrics": orch.metrics.as_dict(),
                "collector_final": final_metrics.__dict__,
                "proposer_stats": orch.proposer_registry.get_stats(),
            }
            path = f"demo_artifacts/openvla_demo_seed{args.seed}_metrics.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(export, f, indent=2)
            print(f"Metrics exported: {path}")

        print("Demo complete.")
        return 0
    finally:
        # Best-effort close event file, then close simulator.
        if getattr(orch, "events", None) is not None:
            try:
                orch.events.flush()
                orch.events.close()
            except Exception:
                pass
        orch.close()


if __name__ == "__main__":
    raise SystemExit(main())
