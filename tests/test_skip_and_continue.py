import contextlib
import io

import numpy as np
import pybullet as p
import yaml

from src.core.system_factory import build_system
from src.interaction.human_presenter import HumanPresenter, SceneDescription
from src.interaction.confirm_bridge import ConfirmBridge
from src.intentos import IntentOSConfig, IntentOSOrchestrator
from src.intentos.recovery import MAX_RETRIES_PER_NODE
from src.kernel import ExecutionKernel
from src.planning import IntentPlanner, PlannerConfig


def _workspace_easy_clean_config():
    with open("configs/default.yaml") as f:
        cfg = yaml.safe_load(f)
    with open("configs/workspace_presets.yaml") as f:
        preset = yaml.safe_load(f)["presets"]["workspace_easy_clean"]

    preset_objects = preset["objects"]
    cfg.setdefault("simulator", {})["use_gui"] = False
    cfg.setdefault("gemini", {})["enabled"] = False
    cfg.setdefault("eeg", {})["enabled"] = False
    cfg.setdefault("logging", {})["events_enabled"] = False
    cfg.setdefault("input", {})["mode"] = "KEYBOARD_ONLY"
    cfg["input"]["sources_enabled"] = ["keyboard"]

    world_cfg = cfg.setdefault("world", {}).setdefault("messy_table", {})
    world_cfg["n_objects"] = len(preset_objects)
    world_cfg["object_positions"] = [obj["position"] for obj in preset_objects]
    world_cfg["object_colors"] = [
        [0.8, 0.1, 0.1, 1.0],
        [0.1, 0.2, 0.9, 1.0],
        [0.95, 0.85, 0.1, 1.0],
        [0.55, 0.55, 0.6, 1.0],
    ]
    return cfg, preset_objects


def _build_intentos_system():
    cfg, preset_objects = _workspace_easy_clean_config()
    system = build_system(cfg)

    planner_cfg = PlannerConfig(llm_enabled=False)
    kernel = ExecutionKernel(
        phase2_orchestrator=system,
        phase2_auth_manager=system.auth_manager,
        invariant_checker=system.executor._invariant_checker,
    )
    planner = IntentPlanner(agent_registry=system.agent_registry, cfg=planner_cfg)
    planner._heuristic.set_world_context(system.world_artifacts, system.sim)

    label_map = {}
    for i, obj in enumerate(preset_objects):
        if i < len(system.world_artifacts.object_ids):
            label_map[obj["id"]] = system.world_artifacts.object_ids[i]
    planner._heuristic.set_object_labels(label_map)

    intentos = IntentOSOrchestrator(
        kernel=kernel,
        agent_registry=system.agent_registry,
        planner=planner,
        cfg=IntentOSConfig(planner=planner_cfg),
    )
    system.intentos = intentos
    return system, intentos


def _tick_until_state(intentos, target_state, max_ticks=300):
    for _ in range(max_ticks):
        intentos.tick()
        kernel = getattr(intentos, "_kernel", None)
        system = getattr(kernel, "orchestrator", None)
        executor = getattr(system, "executor", None)
        if executor is not None and hasattr(executor, "pin_non_active_objects"):
            executor.pin_non_active_objects()
        if intentos.get_status().get("intentos_state") == target_state:
            return
    raise AssertionError(f"IntentOS never reached {target_state}")


def _object_positions(system):
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


def _live_scene(system):
    return system.scene_summarizer.summarize(
        system._read_world_state(),
        system.world_artifacts,
        timestamp_frame=getattr(system, "global_frame_counter", 0),
    )


def _max_position_delta(before, after):
    return max(
        float(np.linalg.norm(after[obj_id] - before[obj_id]))
        for obj_id in before
    )


def _nodes_by_object(status, object_ids):
    result = {obj_id: [] for obj_id in object_ids}
    for node in status.get("task_graph", []):
        object_id = (node.get("parameters") or {}).get("object_id")
        if object_id in result:
            result[object_id].append(node)
    return result


def _is_sane_position(pos):
    return (
        abs(float(pos[0])) <= 1.0
        and abs(float(pos[1])) <= 1.0
        and 0.0 <= float(pos[2]) <= 1.2
    )


def _on_table_ids(system):
    scene = _live_scene(system)
    return {obj.object_id for obj in scene.objects_on_table}


def test_recoverable_first_grasp_failure_skips_and_continues_without_fling():
    system = None
    captured = io.StringIO()

    try:
        with contextlib.redirect_stdout(captured):
            system, intentos = _build_intentos_system()

            object_ids = list(system.world_artifacts.object_ids)
            failed_object_id = object_ids[0]
            remaining_object_ids = object_ids[1:]
            system.executor.force_grasp_failure(failed_object_id)

            assert intentos.submit_goal(
                "clean the table",
                "workspace_easy_clean with red, blue, yellow, and tool",
            )
            _tick_until_state(intentos, "AWAITING_CONFIRM")

            before_confirm = _object_positions(system)
            bridge = ConfirmBridge(
                None,
                system,
                system.auth_manager,
                intentos,
                system.executor._invariant_checker,
            )
            bridge_result = bridge.confirm()
            after_confirm = _object_positions(system)
            confirm_delta = _max_position_delta(before_confirm, after_confirm)

            for _ in range(1000):
                intentos.tick()
                if intentos.get_status().get("intentos_state") in {
                    "COMPLETE",
                    "ERROR",
                    "ABORTED",
                }:
                    break

        log = captured.getvalue()
        status = intentos.get_status()
        object_ids = list(system.world_artifacts.object_ids)
        failed_object_id = object_ids[0]
        remaining_object_ids = object_ids[1:]
        nodes = _nodes_by_object(status, object_ids)
        positions = _object_positions(system)
        bin_center = np.array(system.world_artifacts.bin_zone_center, dtype=float)

        assert bridge_result.success is True
        assert confirm_delta == 0.0
        assert status.get("intentos_state") == "COMPLETE"
        assert system.executor._invariant_checker.false_executions == 0

        failed_nodes = nodes[failed_object_id]
        assert any(node["status"] == "SKIPPED" for node in failed_nodes)
        assert all(node["status"] != "FAILED" for node in failed_nodes)
        assert _is_sane_position(positions[failed_object_id])
        assert np.linalg.norm(positions[failed_object_id][:2] - bin_center[:2]) > 0.04

        for object_id in remaining_object_ids:
            object_nodes = nodes[object_id]
            assert object_nodes
            assert all(
                node["status"] not in {"FAILED", "SKIPPED", "INVALIDATED"}
                for node in object_nodes
            ), object_nodes
            assert any(node["status"] == "DONE" for node in object_nodes)
            assert _is_sane_position(positions[object_id])
            assert np.linalg.norm(positions[object_id][:2] - bin_center[:2]) <= 0.04

        assert all(_is_sane_position(pos) for pos in positions.values())

        presenter = HumanPresenter()
        presenter.set_label_map({"red_block": failed_object_id})
        report = presenter.present_completion(
            goal=status.get("goal", "clean the table"),
            nodes_done=status.get("nodes_complete", 0),
            duration_s=1.0,
            final_scene=SceneDescription(
                objects=[],
                arm_position="home",
                bin_count=len(remaining_object_ids),
                tray_count=0,
                table_count=1,
            ),
            task_graph=status.get("task_graph", []),
        )
        assert report.startswith("Cleaned 3 of 4. I couldn't ")
        assert "the red block after " in report
        assert f"{MAX_RETRIES_PER_NODE} tries" in report
        assert "so I left it on the table." in report
        assert "Want me to try the red block again, or leave it?" in report

        grasp_failure_count = log.count("Forced magnet failure")
        assert 0 < grasp_failure_count <= MAX_RETRIES_PER_NODE
        assert "unauthorized_execution_blocked" not in log
        assert "reauth" not in log.lower()

    finally:
        if system is not None:
            system.close()


def test_user_stop_while_carrying_safe_releases_object_without_false_execution():
    system = None
    captured = io.StringIO()

    try:
        with contextlib.redirect_stdout(captured):
            system, intentos = _build_intentos_system()

            assert intentos.submit_goal(
                "clean the table",
                "workspace_easy_clean with red, blue, yellow, and tool",
            )
            _tick_until_state(intentos, "AWAITING_CONFIRM")

            bridge = ConfirmBridge(
                None,
                system,
                system.auth_manager,
                intentos,
                system.executor._invariant_checker,
            )
            bridge_result = bridge.confirm()
            assert bridge_result.success is True

            stop_seen_while_carrying = {"value": False}

            def stop_when_carrying():
                if system.executor.is_holding_object():
                    stop_seen_while_carrying["value"] = True
                    return True
                return False

            result = intentos.continue_confirmed_objective(
                _live_scene(system),
                set(),
                stop_requested=stop_when_carrying,
            )
            intentos.finish_objective_execution("user_stopped", completed=False)

        object_ids = list(system.world_artifacts.object_ids)
        carried_object_id = object_ids[0]
        positions = _object_positions(system)
        bin_center = np.array(system.world_artifacts.bin_zone_center, dtype=float)
        carried_pos = positions[carried_object_id]
        on_table_ids = _on_table_ids(system)
        carried_outcome = result.outcomes[carried_object_id]

        assert stop_seen_while_carrying["value"] is True
        assert result.accepted is True
        assert result.reason == "user_stopped"
        assert carried_outcome["status"] == "SET_DOWN"
        assert carried_outcome["destination"] == "table"
        assert carried_outcome["reason"] == "user_stopped"
        assert intentos.get_status().get("intentos_state") == "COMPLETE"
        assert system.executor._invariant_checker.false_executions == 0
        assert system.executor._grasp_constraint_id is None
        assert not system.executor.is_holding_object()
        assert all(_is_sane_position(pos) for pos in positions.values())
        assert carried_object_id in on_table_ids
        assert np.linalg.norm(carried_pos[:2] - bin_center[:2]) > 0.04
        assert abs(float(carried_pos[0])) <= 0.35
        assert abs(float(carried_pos[1])) <= 0.25
        assert 0.60 <= float(carried_pos[2]) <= 0.70

    finally:
        if system is not None:
            system.close()


def test_user_stop_before_carrying_halts_without_moving_objects():
    system = None

    try:
        system, intentos = _build_intentos_system()

        assert intentos.submit_goal(
            "clean the table",
            "workspace_easy_clean with red, blue, yellow, and tool",
        )
        _tick_until_state(intentos, "AWAITING_CONFIRM")

        bridge = ConfirmBridge(
            None,
            system,
            system.auth_manager,
            intentos,
            system.executor._invariant_checker,
        )
        assert bridge.confirm().success is True

        before = _object_positions(system)
        result = intentos.continue_confirmed_objective(
            _live_scene(system),
            set(),
            stop_requested=lambda: True,
        )
        after = _object_positions(system)
        intentos.finish_objective_execution("user_stopped", completed=False)

        assert result.accepted is True
        assert result.reason == "user_stopped"
        assert system.executor._invariant_checker.false_executions == 0
        assert system.executor._grasp_constraint_id is None
        assert all(_is_sane_position(pos) for pos in after.values())
        assert _max_position_delta(before, after) < 0.01
        assert intentos.get_status().get("intentos_state") == "COMPLETE"

    finally:
        if system is not None:
            system.close()


def test_user_stop_while_reaching_aborts_without_grasping_target():
    system = None

    try:
        system, intentos = _build_intentos_system()

        assert intentos.submit_goal(
            "clean the table",
            "workspace_easy_clean with red, blue, yellow, and tool",
        )
        _tick_until_state(intentos, "AWAITING_CONFIRM")

        bridge = ConfirmBridge(
            None,
            system,
            system.auth_manager,
            intentos,
            system.executor._invariant_checker,
        )
        assert bridge.confirm().success is True

        object_ids = list(system.world_artifacts.object_ids)
        target_object_id = object_ids[0]
        before = _object_positions(system)
        stop_seen_during_reach = {"value": False}

        def stop_during_reach():
            plan = getattr(system.executor, "active_plan", [])
            index = getattr(system.executor, "plan_index", 0)
            if not plan or index >= len(plan):
                return False
            primitive = plan[index]
            kind = system.executor._primitive_kind(primitive)
            if kind == "reach" and not system.executor.is_holding_object():
                stop_seen_during_reach["value"] = True
                return True
            return False

        result = intentos.continue_confirmed_objective(
            _live_scene(system),
            set(),
            stop_requested=stop_during_reach,
        )
        after = _object_positions(system)
        intentos.finish_objective_execution("user_stopped", completed=False)

        nodes = _nodes_by_object(intentos.get_status(), object_ids)[target_object_id]
        node_status_by_id = {node["node_id"]: node["status"] for node in nodes}

        assert stop_seen_during_reach["value"] is True
        assert result.accepted is True
        assert result.reason == "user_stopped"
        assert system.executor._invariant_checker.false_executions == 0
        assert system.executor._grasp_constraint_id is None
        assert not system.executor.is_holding_object()
        assert node_status_by_id.get("grasp_0") != "DONE"
        assert target_object_id in _on_table_ids(system)
        assert np.linalg.norm(after[target_object_id] - before[target_object_id]) < 0.02

    finally:
        if system is not None:
            system.close()


def test_user_stop_after_object_release_does_not_start_next_object():
    system = None

    try:
        system, intentos = _build_intentos_system()

        assert intentos.submit_goal(
            "clean the table",
            "workspace_easy_clean with red, blue, yellow, and tool",
        )
        _tick_until_state(intentos, "AWAITING_CONFIRM")

        bridge = ConfirmBridge(
            None,
            system,
            system.auth_manager,
            intentos,
            system.executor._invariant_checker,
        )
        assert bridge.confirm().success is True

        object_ids = list(system.world_artifacts.object_ids)
        first_object_id, second_object_id = object_ids[0], object_ids[1]
        before = _object_positions(system)
        stop_seen_after_release = {"value": False}

        def stop_after_first_release():
            graph = getattr(getattr(intentos, "_context", None), "graph", None)
            release_node = graph.get_node("release_0") if graph is not None else None
            release_done = release_node is not None and release_node.status.name == "DONE"
            if release_done:
                stop_seen_after_release["value"] = True
                return True
            return False

        result = intentos.continue_confirmed_objective(
            _live_scene(system),
            set(),
            stop_requested=stop_after_first_release,
        )
        after = _object_positions(system)
        intentos.finish_objective_execution("user_stopped", completed=False)

        status = intentos.get_status()
        nodes_by_object = _nodes_by_object(status, object_ids)
        second_status_by_id = {
            node["node_id"]: node["status"]
            for node in nodes_by_object[second_object_id]
        }
        bin_center = np.array(system.world_artifacts.bin_zone_center, dtype=float)

        assert stop_seen_after_release["value"] is True
        assert result.accepted is True
        assert result.reason == "user_stopped"
        assert system.executor._invariant_checker.false_executions == 0
        assert np.linalg.norm(after[first_object_id][:2] - bin_center[:2]) <= 0.04
        assert second_object_id in _on_table_ids(system)
        assert np.linalg.norm(after[second_object_id] - before[second_object_id]) < 0.02
        assert second_status_by_id.get("reach_1") != "DONE"
        assert second_status_by_id.get("grasp_1") != "DONE"

    finally:
        if system is not None:
            system.close()
