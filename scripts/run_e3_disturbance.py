#!/usr/bin/env python3
"""E3 disturbance experiment: add a new object between persistence cycles."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pybullet as p
import yaml

from src.core.system_factory import build_system
from src.interaction.command_loop import CommandLoop
from src.intentos import IntentOSConfig, IntentOSOrchestrator
from src.kernel import ExecutionKernel
from src.planning import IntentPlanner, PlannerConfig


class DummyLogger:
    def log_turn(self, *args, **kwargs) -> None:
        pass

    def close(self) -> None:
        pass


def _workspace_config(n_objects: int):
    with open("configs/default.yaml") as f:
        cfg = yaml.safe_load(f)
    with open("configs/workspace_presets.yaml") as f:
        preset = yaml.safe_load(f)["presets"]["workspace_easy_clean"]

    preset_objects = preset["objects"][:n_objects]
    cfg.setdefault("simulator", {})["use_gui"] = False
    cfg.setdefault("gemini", {})["enabled"] = False
    cfg.setdefault("eeg", {})["enabled"] = False
    cfg.setdefault("logging", {})["events_enabled"] = False
    cfg.setdefault("input", {})["mode"] = "KEYBOARD_ONLY"
    cfg["input"]["sources_enabled"] = ["keyboard"]

    world_cfg = cfg.setdefault("world", {}).setdefault("messy_table", {})
    world_cfg["n_objects"] = len(preset_objects)
    world_cfg["object_positions"] = [obj["position"] for obj in preset_objects]
    colors = [
        [0.8, 0.1, 0.1, 1.0],
        [0.1, 0.2, 0.9, 1.0],
        [0.95, 0.85, 0.1, 1.0],
        [0.55, 0.55, 0.6, 1.0],
    ]
    world_cfg["object_colors"] = colors[: len(preset_objects)]
    return cfg, preset_objects


def _build_system(n_objects: int):
    cfg, preset_objects = _workspace_config(n_objects)
    system = build_system(cfg)

    planner_cfg = PlannerConfig(llm_enabled=False)
    kernel = ExecutionKernel(
        phase2_orchestrator=system,
        phase2_auth_manager=system.auth_manager,
        invariant_checker=system.executor._invariant_checker,
    )
    planner = IntentPlanner(agent_registry=system.agent_registry, cfg=planner_cfg)
    planner._heuristic.set_world_context(system.world_artifacts, system.sim)

    object_ids = list(system.world_artifacts.object_ids)
    label_map = {
        obj["id"]: object_ids[i]
        for i, obj in enumerate(preset_objects)
        if i < len(object_ids)
    }
    planner._heuristic.set_object_labels(label_map)

    intentos = IntentOSOrchestrator(
        kernel=kernel,
        agent_registry=system.agent_registry,
        planner=planner,
        cfg=IntentOSConfig(planner=planner_cfg),
    )
    system.intentos = intentos
    return system, intentos, preset_objects, label_map


def _inject_cube(system, pos=(0.24, -0.16, 0.66), color=(0.7, 0.1, 0.8, 1.0)) -> int:
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


def _positions(system):
    return {
        obj_id: np.array(
            p.getBasePositionAndOrientation(
                obj_id,
                physicsClientId=system.sim.client,
            )[0],
            dtype=float,
        )
        for obj_id in system.world_artifacts.object_ids
    }


def _is_sane(pos) -> bool:
    return (
        abs(float(pos[0])) <= 1.0
        and abs(float(pos[1])) <= 1.0
        and 0.0 <= float(pos[2]) <= 1.2
    )


def main() -> int:
    system = None
    try:
        system, intentos, preset_objects, label_map = _build_system(3)
        initial_ids = list(system.world_artifacts.object_ids)
        injected = {"done": False, "id": None}
        scene_reads: list[tuple[int, ...]] = []
        continuation_results = []
        issued_tokens: list[str] = []

        original_issue = intentos._issue_current_segment_token

        def traced_issue():
            original_issue()
            token = getattr(intentos, "_current_token", None)
            if token is not None:
                issued_tokens.append(token.token_id)
                print(
                    f"[AUTH E3] issued_scoped_token={token.token_id} "
                    f"covers={sorted(token.authorized_node_ids)}"
                )

        intentos._issue_current_segment_token = traced_issue

        original_release = system.executor._execute_release

        def release_with_injection():
            finished = original_release()
            if finished and not injected["done"]:
                injected["id"] = _inject_cube(system)
                injected["done"] = True
                print(
                    f"[DISTURB E3] injected_new_object={injected['id']} "
                    "after_first_release"
                )
            return finished

        system.executor._execute_release = release_with_injection

        loop = CommandLoop(
            intentos,
            system,
            DummyLogger(),
            "workspace_easy_clean",
            preset_objects,
        )
        loop.set_label_map(label_map)

        original_scene = loop._current_live_scene

        def traced_scene():
            scene = original_scene()
            ids = tuple(obj.object_id for obj in scene.objects_on_table)
            scene_reads.append(ids)
            print(f"[CYCLE E3] live_scene_read={ids}")
            return scene

        loop._current_live_scene = traced_scene

        original_continue = intentos.continue_confirmed_objective

        def traced_continue(live_scene, abandoned):
            ids = tuple(obj.object_id for obj in live_scene.objects_on_table)
            print(
                f"[OBJECTIVE E3] continue_request live={ids} "
                f"abandoned={sorted(abandoned)}"
            )
            result = original_continue(live_scene, abandoned)
            continuation_results.append((ids, result.reason, result.outcomes))
            print(
                f"[OBJECTIVE E3] continue_result reason={result.reason} "
                f"outcomes={result.outcomes}"
            )
            return result

        intentos.continue_confirmed_objective = traced_continue

        print("[E3] command='clean the table'")
        proposal = loop._handle_goal("clean the table")
        print(f"[E3] proposal={proposal.replace(chr(10), ' | ')}")
        print("[E3] confirmation='yes'")
        loop._handle_confirm()

        auth = intentos._objective_authorization
        status = intentos.get_status()
        positions = _positions(system)
        bin_center = np.array(system.world_artifacts.bin_zone_center, dtype=float)
        in_bin = {
            obj_id: float(np.linalg.norm(pos[:2] - bin_center[:2])) <= 0.04
            for obj_id, pos in positions.items()
        }
        sane = {obj_id: _is_sane(pos) for obj_id, pos in positions.items()}
        injected_seen = any(
            injected["id"] in read
            for read in scene_reads
            if injected["id"] is not None
        )

        print(f"[E3 RESULT] initial_ids={initial_ids}")
        print(f"[E3 RESULT] injected_id={injected['id']}")
        print(f"[E3 RESULT] all_ids={list(system.world_artifacts.object_ids)}")
        print(f"[E3 RESULT] scene_reads={scene_reads}")
        print(f"[E3 RESULT] continuation_results={continuation_results}")
        print(f"[E3 RESULT] scoped_tokens={issued_tokens} unique={len(set(issued_tokens))}")
        print(
            f"[E3 RESULT] objective_status={auth.status.name} "
            f"reason={auth.reason} confirmations=1"
        )
        print(
            f"[E3 RESULT] final_state={status.get('intentos_state')} "
            f"false_executions={system.executor._invariant_checker.false_executions}"
        )
        print(f"[E3 RESULT] in_bin={in_bin}")
        print(f"[E3 RESULT] sane={sane}")
        print(f"[E3 RESULT] injected_perceived={injected_seen}")

        ok = (
            injected["id"] is not None
            and injected_seen
            and len(issued_tokens) >= 3
            and len(set(issued_tokens)) == len(issued_tokens)
            and auth.status.name == "COMPLETED"
            and status.get("intentos_state") == "COMPLETE"
            and system.executor._invariant_checker.false_executions == 0
            and all(in_bin.values())
            and all(sane.values())
        )
        return 0 if ok else 1
    finally:
        if system is not None:
            system.close()


if __name__ == "__main__":
    raise SystemExit(main())
