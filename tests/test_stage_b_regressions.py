from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agents import AgentRegistry
from src.interaction.command_loop import CommandLoop
from src.interaction.intent_interpreter import IntentInterpreter
from src.planning.planner import HeuristicPlanner


class _State:
    def __init__(self, name: str):
        self.name = name


class _FakeOrchestratorHarness:
    def __init__(self):
        self.false_executions = 0
        self._state = "IDLE"
        self._loop = CommandLoop.__new__(CommandLoop)
        self._loop._interpreter = IntentInterpreter()
        self._loop._bridge_monitor = None
        self._loop._logger = MagicMock()
        self._loop._presenter = SimpleNamespace(is_debug=False)
        self._loop._tick_until_stable = MagicMock()
        self._loop._maybe_print_execution_update = MagicMock()
        self._loop._monitor_orchestrator_update = MagicMock()
        self._loop._orch = MagicMock()
        self._loop._orch.get_status.side_effect = self._status

        def fake_route(raw, cmd):
            if cmd == "GOAL":
                self._state = "AWAITING_CONFIRM"
                return "Confirm?"
            if cmd == "CONFIRM":
                if self._state == "AWAITING_CONFIRM":
                    self._state = "COMPLETE"
                    return "Done."
                return "There's nothing waiting for confirmation right now."
            return None

        self._loop._route = MagicMock(side_effect=fake_route)

    def _status(self):
        return {
            "intentos_state": self._state,
            "false_executions": self.false_executions,
        }

    def handle(self, text: str) -> _State:
        response = self._loop._process_user_command(text)
        if response and "I don't have a clear action" in response:
            self._state = "AWAITING_CLARIFICATION"
        return _State(self._state)


@pytest.fixture
def workspace(monkeypatch):
    def build(name: str) -> HeuristicPlanner:
        planner = HeuristicPlanner(AgentRegistry())
        planner.set_world_context(world_artifacts=SimpleNamespace(), sim=SimpleNamespace(client=0))

        positions = {
            4: [0.1, 0.0, 0.65],
            5: [0.2, 0.0, 0.65],
            6: [0.3, 0.0, 0.65],
            7: [0.4, 0.0, 0.65],
            8: [0.5, 0.0, 0.65],
        }

        if name == "workspace_missing_object":
            planner.set_object_labels(
                {
                    "blue_block": 5,
                    "yellow_block": 6,
                }
            )
        elif name == "workspace_easy_clean":
            planner.set_object_labels(
                {
                    "blue block": 5,
                    "blue tray": 8,
                    "red block": 4,
                }
            )
        elif name == "workspace_unreachable":
            planner.set_object_labels({"yellow block": 6})
            positions[6] = [99.0, 0.0, 0.65]
        else:
            raise ValueError(f"Unknown workspace fixture: {name}")

        def fake_get_base_position_and_orientation(body_id, physicsClientId=None):
            del physicsClientId
            return positions[body_id], [0, 0, 0, 1]

        monkeypatch.setattr(
            "pybullet.getBasePositionAndOrientation",
            fake_get_base_position_and_orientation,
        )
        return planner

    return build


@pytest.fixture
def interpreter():
    return IntentInterpreter()


@pytest.fixture
def orchestrator():
    return _FakeOrchestratorHarness()


def test_blue_block_resolves_in_missing_object_preset(workspace):
    """Blue block is present even when red block is the missing one."""
    ws = workspace("workspace_missing_object")

    blue = ws._resolve_object_by_label("blue block")
    assert blue["status"] == "resolved"
    assert blue["target_xyz"] is not None

    red = ws._resolve_object_by_label("red block")
    assert red["status"] == "not_present"
    assert red["label"] == "red block"


def test_substring_collision_does_not_misresolve(workspace):
    """Object resolution uses token matching, not broad substring matching."""
    ws = workspace("workspace_easy_clean")

    res = ws._resolve_object_by_label("blue block")

    assert res["status"] == "resolved"
    assert res["object_id"] == ws._label_map["blue block"]


def test_vague_goal_routes_to_clarify_not_clean(interpreter):
    """'make some room' must never silently become 'clean the table'."""
    assert interpreter.interpret("make some room") == "__CLARIFY__"
    assert interpreter.interpret("tidy up a bit") == "__CLARIFY__"


def test_clarify_does_not_reach_awaiting_confirm():
    """A clarify-routed goal must not produce an executable proposal."""
    loop = CommandLoop.__new__(CommandLoop)
    loop._interpreter = IntentInterpreter()
    loop._bridge_monitor = None
    loop._logger = MagicMock()
    loop._presenter = SimpleNamespace(is_debug=False)
    loop._orch = MagicMock()
    loop._orch.get_status.return_value = {
        "intentos_state": "IDLE",
        "false_executions": 0,
    }
    loop._tick_until_stable = MagicMock()
    loop._maybe_print_execution_update = MagicMock()
    loop._monitor_orchestrator_update = MagicMock()
    loop._route = MagicMock(return_value="should not route")

    response = loop._process_user_command("make some room")

    assert "I don't have a clear action" in response
    assert loop._orch.get_status()["intentos_state"] != "AWAITING_CONFIRM"
    assert loop._orch.get_status()["false_executions"] == 0
    loop._route.assert_not_called()
    loop._logger.log_turn.assert_called_once()
    assert loop._logger.log_turn.call_args.kwargs["command_class"] == "CLARIFY"


@pytest.mark.parametrize(
    "goal",
    [
        "clear some space near the arm",
        "put things away",
        "tidy this up",
        "make room",
    ],
)
def test_keyword_overlap_does_not_bypass_clarify(orchestrator, goal):
    """Vague goals containing a planner keyword must still clarify."""
    state = orchestrator.handle(goal)
    assert state.name == "AWAITING_CLARIFICATION", f"{goal!r} bypassed clarify"
    assert orchestrator.false_executions == 0


def test_unreachable_object_message_is_honest(workspace):
    """An existing but invalid object reports unreachable, not already moved."""
    ws = workspace("workspace_unreachable")
    res = ws._resolve_object_by_label("yellow block")
    assert res["status"] == "unreachable"
    assert res["target_xyz"] is None
    assert res["object_id"] is not None


def test_clarify_then_valid_answer_completes(orchestrator):
    """Vague goal can be followed by a concrete intent without stranding."""
    s1 = orchestrator.handle("make some room")
    assert s1.name == "AWAITING_CLARIFICATION"

    s2 = orchestrator.handle("clean the table")
    assert s2.name == "AWAITING_CONFIRM"

    s3 = orchestrator.handle("yes")
    assert s3.name == "COMPLETE"
    assert orchestrator.false_executions == 0


def test_clarify_then_vague_answer_does_not_execute(orchestrator):
    """A second vague answer must not coerce into execution."""
    orchestrator.handle("make some room")
    state = orchestrator.handle("just do something")
    assert state.name in {"AWAITING_CLARIFICATION", "IDLE"}
    assert orchestrator.false_executions == 0


def test_stale_yes_with_no_pending_proposal_is_safe(orchestrator):
    """A 'yes' with nothing awaiting confirmation must never execute."""
    state = orchestrator.handle("yes")
    assert state.name in {"IDLE", "COMPLETE"}
    assert orchestrator.false_executions == 0


def test_double_yes_after_complete_is_safe(orchestrator):
    """A second 'yes' post-completion must not re-execute."""
    orchestrator.handle("clean the table")
    orchestrator.handle("yes")
    before = orchestrator.false_executions
    state = orchestrator.handle("yes")
    assert orchestrator.false_executions == before == 0
    assert state.name == "COMPLETE"
