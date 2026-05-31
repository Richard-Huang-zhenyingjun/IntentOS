from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agents import AgentRegistry
from src.interaction.command_loop import CommandLoop
from src.interaction.intent_interpreter import IntentInterpreter
from src.planning.planner import HeuristicPlanner


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
