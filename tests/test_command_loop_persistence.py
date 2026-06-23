from collections import deque
from types import SimpleNamespace

from src.interaction.command_loop import CommandLoop
from src.interaction.human_presenter import DecisionReason, HumanPresenter
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

    def continue_confirmed_objective(self, live_scene, abandoned, **kwargs):
        self.continue_calls.append(
            {
                "live": {obj.object_id for obj in live_scene.objects_on_table},
                "abandoned": set(abandoned),
                "stop_requested_present": callable(kwargs.get("stop_requested")),
            }
        )
        self.remaining.discard(5)
        return ObjectiveContinuationResult(
            accepted=True,
            reason="complete",
            outcomes={
                4: {"status": "SKIPPED", "reason": "grasp_failed"},
                5: {"status": "DONE", "reason": None, "destination": "bin"},
            },
        )

    def complete_objective_authorization(self, reason):
        self.completed.append(reason)

    def revoke_objective_authorization(self, reason):
        self.revoked.append(reason)


class _TerminalOrchestrator(_Orchestrator):
    def __init__(self, remaining):
        super().__init__(remaining)
        self.finished = []

    def finish_objective_execution(self, reason, completed=True):
        self.finished.append((reason, completed))


class _ExtensionOrchestrator(_TerminalOrchestrator):
    def __init__(self, remaining):
        super().__init__(remaining)
        self.extensions = []

    def authorize_objective_extension_from_human(
        self,
        phase2_token_id,
        source_goal,
        proposal_id=None,
        reason="keep_going",
    ):
        self.extensions.append(
            {
                "phase2_token_id": phase2_token_id,
                "source_goal": source_goal,
                "proposal_id": proposal_id,
                "reason": reason,
            }
        )


class _World:
    def __init__(self):
        self.authorized = []

    def authorize_for_intentos(self, source, quality):
        self.authorized.append({"source": source, "quality": quality})
        return SimpleNamespace(token_id="auth_keep_going")


class _TickingOrchestrator:
    def __init__(self, state):
        self.state = state
        self.ticks = 0

    def get_status(self):
        return {"intentos_state": self.state}

    def tick(self):
        self.ticks += 1


class _PinningExecutor:
    def __init__(self):
        self.pin_calls = 0

    def pin_non_active_objects(self):
        self.pin_calls += 1


class _NoProgressOrchestrator(_Orchestrator):
    def continue_confirmed_objective(self, live_scene, abandoned, **kwargs):
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


class _AllDoneOrchestrator(_TerminalOrchestrator):
    def continue_confirmed_objective(self, live_scene, abandoned, **kwargs):
        live_ids = {obj.object_id for obj in live_scene.objects_on_table}
        self.continue_calls.append({"live": live_ids, "abandoned": set(abandoned)})
        for object_id in live_ids:
            self.remaining.discard(object_id)
        return ObjectiveContinuationResult(
            accepted=True,
            reason="complete",
            outcomes={
                object_id: {"status": "DONE", "reason": None, "destination": "bin"}
                for object_id in live_ids
            },
        )


class _MaxCycleOrchestrator(_TerminalOrchestrator):
    def continue_confirmed_objective(self, live_scene, abandoned, **kwargs):
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
                5: {"status": "DONE", "reason": None, "destination": "bin"},
            },
        )


class _MidCycleStopOrchestrator(_TerminalOrchestrator):
    def continue_confirmed_objective(self, live_scene, abandoned, **kwargs):
        self.continue_calls.append(
            {
                "live": {obj.object_id for obj in live_scene.objects_on_table},
                "abandoned": set(abandoned),
            }
        )
        stop_requested = kwargs.get("stop_requested")
        assert callable(stop_requested)
        assert stop_requested() is True
        self.remaining.discard(4)
        return ObjectiveContinuationResult(
            accepted=True,
            reason="user_stopped",
            outcomes={
                4: {"status": "DONE", "reason": None, "destination": "bin"},
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
    out = capsys.readouterr().out
    assert "Finished the reachable work." in out
    assert "placed 1 item(s) in the bin" in out
    assert "left the red block on the table" in out
    assert "I couldn't grip the red block after 5 tries" in out
    assert "Table's clear" not in out


def test_persistence_loop_revokes_when_cycle_makes_no_progress(capsys):
    orch = _NoProgressOrchestrator({4})
    loop = _loop_with(orch)

    loop._pursue_until_satisfied()

    assert len(orch.continue_calls) == 1
    assert orch.completed == []
    assert orch.revoked == ["no_progress"]
    assert loop._session_bin_count == 0
    assert "did not place or skip any items" in capsys.readouterr().out


def test_persistence_loop_reports_table_clear_when_nothing_remains(capsys):
    orch = _TerminalOrchestrator(set())
    loop = _loop_with(orch)

    loop._pursue_until_satisfied()

    assert orch.continue_calls == []
    assert orch.completed == ["satisfied"]
    assert orch.revoked == []
    assert orch.finished == [("satisfied", True)]
    out = capsys.readouterr().out
    assert "Table's clear." in out
    assert "Say 'clean the table'" not in out


def test_persistence_loop_full_clear_reports_real_placed_count(capsys):
    orch = _AllDoneOrchestrator({4, 5})
    loop = _loop_with(orch)

    loop._pursue_until_satisfied(max_cycles=3)

    assert orch.completed == ["satisfied"]
    out = capsys.readouterr().out
    assert "Table's clear. I placed 2 item(s)." in out
    assert "still on the table" not in out
    assert "Say 'clean the table'" not in out


def test_tick_until_stable_pins_scene_and_does_not_tick_while_awaiting_confirm():
    loop = CommandLoop.__new__(CommandLoop)
    executor = _PinningExecutor()
    loop._world = SimpleNamespace(executor=executor)
    loop._orch = _TickingOrchestrator("AWAITING_CONFIRM")
    loop._monitor_orchestrator_update = lambda: None
    loop._tick_rate_hz = 1000.0

    loop._tick_until_stable()

    assert executor.pin_calls == 1
    assert loop._orch.ticks == 0


def test_persistence_loop_stop_between_cycles_finishes_without_continuing(capsys):
    orch = _TerminalOrchestrator({4})
    loop = _loop_with(orch)
    loop._browser_queue = ["stop"]

    loop._pursue_until_satisfied(max_cycles=2)

    assert orch.continue_calls == []
    assert orch.revoked == ["user_stopped"]
    assert orch.finished == [("user_stopped", False)]
    out = capsys.readouterr().out
    assert "Stopped safely." in out
    assert "1 item(s) still on the table" in out
    assert "Say 'clean the table' or 'keep going' to continue." in out


def test_persistence_loop_stop_during_cycle_finishes_after_safe_boundary(capsys):
    orch = _MidCycleStopOrchestrator({4, 5})
    loop = _loop_with(orch)
    loop._browser_queue = deque(["stop"])
    loop._poll_between_cycle_signal = lambda: None

    loop._pursue_until_satisfied(max_cycles=2)

    assert len(orch.continue_calls) == 1
    assert orch.revoked == ["user_stopped"]
    assert orch.finished == [("user_stopped", False)]
    assert loop._session_bin_count == 1
    out = capsys.readouterr().out
    assert "Stopped safely." in out
    assert "placed 1 item(s) in the bin" in out
    assert "1 item(s) still on the table" in out
    assert "Say 'clean the table' or 'keep going' to continue." in out


def test_max_cycles_handoff_has_one_question_and_no_concatenation(capsys):
    orch = _MaxCycleOrchestrator({4, 5})
    loop = _loop_with(orch)

    loop._pursue_until_satisfied(max_cycles=1)

    out = capsys.readouterr().out
    assert orch.revoked == ["max_cycles"]
    assert "Table still isn't clear after 1 rounds." in out
    assert "placed 1 item(s) in the bin" in out
    assert "1 item(s) still on the table" in out
    assert out.count("?") == 1
    assert "Keep going, or leave it?" in out
    assert "Want me to try" not in out


def test_keep_going_creates_human_sourced_objective_extension(capsys):
    orch = _ExtensionOrchestrator(set())
    loop = _loop_with(orch)
    loop._world = _World()
    loop._pending_objective_decision = {
        "goal": "clean the table",
        "cycle_cap": 4,
        "abandoned": set(),
        "placed": set(),
        "outcomes": {},
    }
    loop._active_objective_state = dict(loop._pending_objective_decision)
    pursued = []
    loop._pursue_until_satisfied = lambda max_cycles=None: pursued.append(max_cycles)

    response = loop._handle_resume()

    assert response == ""
    assert loop._world.authorized == [
        {"source": "keyboard:keep_going", "quality": 1.0}
    ]
    assert orch.extensions == [
        {
            "phase2_token_id": "auth_keep_going",
            "source_goal": "clean the table",
            "proposal_id": None,
            "reason": "keep_going",
        }
    ]
    assert pursued == [4]
    assert "Human keep-going authorization issued" in capsys.readouterr().out


def test_leave_it_finalizes_pending_objective_decision():
    orch = _TerminalOrchestrator(set())
    loop = _loop_with(orch)
    loop._pending_objective_decision = {
        "goal": "clean the table",
        "cycle_cap": 4,
    }
    loop._active_objective_state = dict(loop._pending_objective_decision)

    response = loop._handle_leave()

    assert response == "Okay, leaving it here."
    assert loop._pending_objective_decision is None
    assert loop._active_objective_state is None
    assert orch.finished == [("user_left_it", False)]


def test_leave_it_handoff_summarizes_done_and_remaining_state():
    orch = _TerminalOrchestrator({4})
    loop = _loop_with(orch)
    loop._pending_objective_decision = {
        "goal": "clean the table",
        "cycle_cap": 4,
        "abandoned": set(),
        "placed": {5},
        "outcomes": {
            5: {"status": "DONE", "reason": None, "destination": "bin"},
        },
    }
    loop._active_objective_state = dict(loop._pending_objective_decision)

    response = loop._handle_leave()

    assert "Okay, leaving it here." in response
    assert "placed 1 item(s) in the bin" in response
    assert "1 item(s) still on the table" in response
    assert "Say 'clean the table' or 'keep going' to continue." in response


def test_handoff_guard_marks_done_but_live_object_unknown_not_placed():
    orch = _TerminalOrchestrator({4})
    loop = _loop_with(orch)

    state = loop._build_handoff_state(
        stop_reason="satisfied",
        live_scene=_scene({4}),
        outcomes={4: {"status": "DONE", "reason": None, "destination": "bin"}},
        abandoned=set(),
    )
    response = loop._presenter.present_handoff_summary(state)

    assert state.reason == "no_progress"
    assert state.objects[0].status == "unknown"
    assert "state unclear for the red block" in response
    assert "Table's clear" not in response
    assert "placed 1 item" not in response


def test_handoff_treats_user_stop_set_down_as_remaining_without_warning():
    orch = _TerminalOrchestrator({4})
    loop = _loop_with(orch)

    state = loop._build_handoff_state(
        stop_reason="user_stopped",
        live_scene=_scene({4}),
        outcomes={4: {"status": "SET_DOWN", "reason": "user_stopped", "destination": "table"}},
        abandoned=set(),
    )
    response = loop._presenter.present_handoff_summary(state)

    assert state.warnings == ()
    assert state.objects[0].status == "remaining"
    assert state.objects[0].location == "table"
    assert "Current state: 1 item(s) still on the table." in response
    assert "state unclear" not in response
    assert "placed 1 item" not in response


def test_present_reason_recoverable_skip_uses_soft_register():
    presenter = HumanPresenter()

    text = presenter.present_reason(
        DecisionReason(kind="object", code="grasp_failed", object_label="the red block"),
        form="phrase",
    )

    assert text == "couldn't grip"


def test_present_reason_safety_auth_uses_distinct_serious_register():
    presenter = HumanPresenter()

    text = presenter.present_reason(
        DecisionReason(kind="authorization", code="unauthorized_execution_blocked")
    )

    assert "authorization or safety check failed" in text
    assert "couldn't grip" not in text
    assert "couldn't reach" not in text
    assert "couldn't place" not in text


def test_present_reason_refusal_keeps_real_fact_in_user_shaped_wording():
    presenter = HumanPresenter()

    text = presenter.present_reason(
        DecisionReason(
            kind="refusal",
            code="refused",
            detail="object 17 is not a live table object",
        )
    )

    assert "outside the confirmed objective" in text
    assert "object 17 is not currently on the table" in text


def test_present_reason_unknown_code_does_not_invent_cause():
    presenter = HumanPresenter()

    text = presenter.present_reason(
        DecisionReason(kind="object", code="mystery_failure_42")
    )

    assert "couldn't determine a specific reason" in text
    assert "couldn't grip" not in text
    assert "couldn't reach" not in text
    assert "couldn't place" not in text
