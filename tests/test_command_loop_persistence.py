from types import SimpleNamespace

from src.interaction.command_loop import CommandLoop
from src.interaction.human_presenter import HumanPresenter
from src.intentos.orchestrator import ObjectiveContinuationResult


class _Orchestrator:
    def __init__(self, remaining):
        self.remaining = remaining
        self.continue_calls = []
        self.completed = []
        self.revoked = []

    def get_status(self):
        return {
            "goal": "clean the table",
            "nodes_complete": 4,
            "task_graph": [],
        }

    def continue_confirmed_objective(self, live_scene, abandoned):
        self.continue_calls.append(
            {
                "live": {obj.object_id for obj in live_scene.objects_on_table},
                "abandoned": set(abandoned),
            }
        )
        self.remaining.discard(5)
        return ObjectiveContinuationResult(
            accepted=True,
            reason="complete",
            outcomes={
                4: {"status": "SKIPPED", "reason": "grasp_failed"},
                5: {"status": "DONE", "reason": None},
            },
        )

    def complete_objective_authorization(self, reason):
        self.completed.append(reason)

    def revoke_objective_authorization(self, reason):
        self.revoked.append(reason)


class _NoProgressOrchestrator(_Orchestrator):
    def continue_confirmed_objective(self, live_scene, abandoned):
        self.continue_calls.append(
            {
                "live": {obj.object_id for obj in live_scene.objects_on_table},
                "abandoned": set(abandoned),
            }
        )
        return ObjectiveContinuationResult(
            accepted=True,
            reason="complete",
            outcomes={
                4: {"status": "PENDING", "reason": None},
            },
        )


class _Bridge:
    def __init__(self):
        self._label_map = {"red_block": 4, "blue_block": 5}
        self._objects = [
            {"id": "red_block", "in_bin": False, "in_tray": False},
            {"id": "blue_block", "in_bin": False, "in_tray": False},
        ]
        self._current_target_object_id = None

    def on_node_complete(self, node_id, action_type, success, parameters=None):
        if not success:
            return
        parameters = parameters or {}
        if action_type == "reach":
            self._current_target_object_id = parameters.get("object_id")
            return
        if action_type != "move":
            return

        target_object_id = parameters.get("object_id") or self._current_target_object_id
        for obj in self._objects:
            if self._label_map.get(obj["id"]) == target_object_id:
                if parameters.get("target") == "tray":
                    obj["in_tray"] = True
                else:
                    obj["in_bin"] = True
                self._current_target_object_id = None
                return

    def flags(self):
        return {
            obj["id"]: {
                "in_bin": obj["in_bin"],
                "in_tray": obj["in_tray"],
            }
            for obj in self._objects
        }


def _scene(object_ids):
    objects = tuple(
        SimpleNamespace(object_id=object_id)
        for object_id in sorted(object_ids)
    )
    return SimpleNamespace(objects_on_table=objects)


def _loop_with(orch):
    loop = CommandLoop.__new__(CommandLoop)
    loop._orch = orch
    loop._task_start_time = 0.0
    loop._preset_objects = []
    loop._bin_count = 0
    loop._session_bin_count = 0
    loop._tray_count = 0
    loop._moved_object_ids = set()
    loop._presenter = HumanPresenter()
    loop._presenter.set_label_map(
        {
            "red_block": 4,
            "blue_block": 5,
        }
    )
    loop._monitor_execution_complete = lambda count: None
    loop._monitor_system_response = lambda msg: None
    loop._mark_planner_object_moved = lambda object_id: None
    loop._current_live_scene = lambda: _scene(orch.remaining)
    loop._bridge_monitor = _Bridge()
    return loop


def test_persistence_loop_continues_under_one_objective_and_abandons_skips(capsys):
    remaining = {4, 5}
    orch = _Orchestrator(remaining)
    loop = _loop_with(orch)

    loop._pursue_until_satisfied(max_cycles=3)

    assert len(orch.continue_calls) == 1
    assert orch.continue_calls[0]["live"] == {4, 5}
    assert orch.continue_calls[0]["abandoned"] == set()
    assert orch.completed == ["satisfied"]
    assert orch.revoked == []
    assert loop._moved_object_ids == {5}
    assert loop._session_bin_count == 1
    assert loop._bridge_monitor.flags() == {
        "red_block": {"in_bin": False, "in_tray": False},
        "blue_block": {"in_bin": True, "in_tray": False},
    }
    assert (
        "Cleaned 1 of 2. I couldn't grip the red block after 5 tries, "
        "so I left it on the table. Want me to try the red block again, "
        "or leave it?"
    ) in capsys.readouterr().out


def test_persistence_loop_revokes_when_cycle_makes_no_progress(capsys):
    orch = _NoProgressOrchestrator({4})
    loop = _loop_with(orch)

    loop._pursue_until_satisfied()

    assert len(orch.continue_calls) == 1
    assert orch.completed == []
    assert orch.revoked == ["no_progress"]
    assert loop._session_bin_count == 0
    assert "made no progress" in capsys.readouterr().out


def test_persistence_loop_reports_table_clear_when_nothing_remains(capsys):
    orch = _Orchestrator(set())
    loop = _loop_with(orch)

    loop._pursue_until_satisfied()

    assert orch.continue_calls == []
    assert orch.completed == ["satisfied"]
    assert orch.revoked == []
    assert "Table's clear." in capsys.readouterr().out
