#!/usr/bin/env python3
"""
E5 demo: assistive-reach (CLEAR_SPECIFIC) end-to-end, narrated.

Drives the exact same path the heuristic CLEAN_TABLE proposer uses - state
machine -> _handle_confirm -> _authorize_and_start_phase2_execution ->
_execute_task_with_trust (per-tick is_authorized assertion) - no reach-
specific execution branch, no path to execution that skips authorization.

Uses a synthetic hand track (no camera) so this runs headless in any
environment; see tests/test_e5_reach_end_to_end.py for the same flow as
pytest assertions, including the cancel-mid-grasp safety case and the
end-to-end scope-gate rejections (wrong object / missing zone / arbitrary
attacker xyz).

Usage:
    python scripts/run_e5_reach_demo.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np

from src.core.schema import ArmUIState
from src.core.system_factory import build_system, load_config
from src.execution.primitive_executor import ExecutorStatus
from src.input.filter import DecisionFilter
from src.input.pipeline import DecisionPipeline
from src.input.policies import DecisionPolicy
from src.input.router import DecisionRouter
from src.input.source_fake import FakeSource
from src.interfaces.hand_state import HandState
from src.interfaces.intent_proposal import ActionType


def _config():
    config = load_config("configs/default.yaml")
    config.setdefault("simulator", {})["use_gui"] = False
    config.setdefault("gemini", {})["enabled"] = False
    config.setdefault("eeg", {})["enabled"] = False
    config.setdefault("openvla", {})["enabled"] = False
    config.setdefault("logging", {})["events_enabled"] = False
    return config


def _install_scheduled_confirms(orch, config, confirm_frames):
    test_cfg = dict(config)
    test_cfg["input"] = dict(config.get("input", {}))
    test_cfg["input"]["mode"] = "KEYBOARD_ONLY"
    test_cfg["input"]["sources_enabled"] = ["keyboard"]
    test_cfg["input"]["debounce_frames"] = 0
    test_cfg["input"]["confirm_hold_frames"] = 1
    test_cfg["input"]["min_quality"] = 0.0

    policy = DecisionPolicy.from_config(test_cfg)
    router = DecisionRouter(policy)
    fake = FakeSource()
    for frame in confirm_frames:
        fake.set_confirm_on_frame(frame)
    router.register_source("keyboard", fake)
    orch.decision_pipeline = DecisionPipeline(router, DecisionFilter(test_cfg))


def _hand_track_to(start_xy, end_xy, n_frames=8, fps=30.0, aperture=0.15):
    dt = 1.0 / fps
    sx, sy = start_xy
    ex, ey = end_xy
    dx = (ex - sx) / (n_frames - 1)
    dy = (ey - sy) / (n_frames - 1)
    vx, vy = dx / dt, dy / dt
    speed = math.hypot(vx, vy)
    n = math.hypot(dx, dy)
    direction_xy = (dx / n, dy / n) if n > 1e-9 else (0.0, 0.0)
    frames = []
    for i in range(n_frames):
        px, py = sx + dx * i, sy + dy * i
        frames.append(HandState(
            timestamp_s=i * dt,
            wrist_xy=(px, py),
            index_tip_xy=(px, py),
            thumb_tip_xy=(px + aperture, py),
            velocity_xy=(vx, vy),
            speed=speed,
            reach_direction_xy=direction_xy,
            grasp_aperture=aperture,
            detection_confidence=1.0,
            hand_present=True,
        ))
    return frames


def main():
    print("=" * 72)
    print("E5 demo: assistive-reach end-to-end")
    print("=" * 72)

    config = _config()
    orch = build_system(config)
    try:
        orch.step()
        target_id = orch.world_artifacts.object_ids[0]
        target_obj = next(
            o for o in orch.current_scene.objects_on_table if o.object_id == target_id
        )
        print(f"\n[1/5] Target object {target_id} at {tuple(target_obj.pos_xyz)}")

        print("[2/5] Feeding a synthetic reach toward it (no camera in this demo)...")
        reach_proposer = orch.proposer_registry.get("reach_intent")
        assert reach_proposer is not None, "reach_intent proposer not registered"
        end_xy = (target_obj.pos_xyz[0], target_obj.pos_xyz[1])
        start_xy = (end_xy[0] - 0.3, end_xy[1] - 0.1)
        for hand in _hand_track_to(start_xy, end_xy):
            reach_proposer.update_hand(hand)
        decision = reach_proposer.estimate(orch.current_scene)
        print(f"      committed={decision.committed} target={decision.target_object_id} "
              f"reason={decision.reason}")

        print("[3/5] Confirming (frame 5 locks target + proposes, frame 15 authorizes)...")
        _install_scheduled_confirms(orch, config, confirm_frames=[5, 15])
        for i in range(60):
            snapshot = orch.step()
            if orch.state_machine.state == ArmUIState.EXECUTING:
                print(f"      EXECUTING at frame {i}: proposal={orch.current_proposal.action.value} "
                      f"token={orch.auth_manager.get_active_token_id()}")
                break
        else:
            print("      FAILED to reach EXECUTING")
            return 1

        print("[4/5] Running the compiled plan (real physics grasp takes a while)...")
        max_false_executions = 0
        for i in range(900):
            snapshot = orch.step()
            max_false_executions = max(max_false_executions, snapshot.false_executions)
            if orch.executor.status == ExecutorStatus.COMPLETE or not orch.auth_manager.is_authorized():
                break

        holding = orch.grasp.attached_object_id
        final_world = orch._read_world_state()
        zone_center = np.array(config["planning"]["assistive_reach"]["delivery_zone_center_xyz"])
        dist = np.linalg.norm(final_world.ee_position - zone_center) if final_world.ee_position is not None else None

        print(f"[5/5] Done: false_executions={max_false_executions} "
              f"holding_object_id={holding} dist_to_delivery_zone={dist}")
        print("=" * 72)
        print("PASS" if (max_false_executions == 0 and holding == target_id) else "CHECK OUTPUT ABOVE")
        print("=" * 72)
    finally:
        orch.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
