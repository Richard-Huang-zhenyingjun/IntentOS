"""
StateBridge connects CommandLoop events to the monitor server.

CommandLoop calls StateBridge after each turn. StateBridge updates monitor state
and pushes to the browser. It is the only coupling point between the
interaction layer and the monitor.
"""
from __future__ import annotations

from typing import Optional

import httpx

from src.monitor.server import command_queue, push_state_update, workspace_state


_PRESET_POSITIONS = {
    "red_block": (0.25, 0.35),
    "blue_block": (0.45, 0.55),
    "yellow_block": (0.65, 0.35),
    "tool": (0.40, 0.30),
    "screwdriver": (0.55, 0.30),
    "cup": (0.45, 0.45),
}

_OBJECT_COLORS = {
    "red_block": "#e74c3c",
    "blue_block": "#3498db",
    "yellow_block": "#f1c40f",
    "tool": "#95a5a6",
    "screwdriver": "#7f8c8d",
    "cup": "#ecf0f1",
}


class StateBridge:
    """
    Translates CommandLoop/IntentOS state into monitor workspace state.
    One instance per session.
    """

    def __init__(
        self,
        preset: Optional[dict] = None,
        monitor_url: str = "http://127.0.0.1:7788",
    ):
        self._preset = preset or {}
        self._monitor_url = monitor_url.rstrip("/")
        command_queue.clear()
        workspace_state.reset()
        self._post("/reset", {})
        self._objects = self._init_objects(preset)
        self._label_map = {}
        self._bin_count = 0
        self._tray_count = 0
        self._current_target_object_id = None
        self.reset_objects()

    def set_label_map(self, label_map: dict) -> None:
        self._label_map = label_map

    def add_object(
        self,
        object_id: str,
        label: str,
        body_id: int,
        color: str = "#9b59b6",
        x: float = 0.72,
        y: float = 0.58,
    ) -> None:
        """Add a live-injected object to the monitor canvas."""
        if any(obj.get("id") == object_id for obj in self._objects):
            self._label_map[object_id] = body_id
            return
        self._objects.append(
            {
                "id": object_id,
                "label": label,
                "color": color,
                "x": x,
                "y": y,
                "in_bin": False,
                "in_tray": False,
                "highlighted": True,
                "visible": True,
            }
        )
        self._label_map[object_id] = body_id
        self._push_workspace()

    def on_user_input(self, text: str) -> None:
        """Call when user types a command."""
        workspace_state.add_conversation_turn("user", text)
        self._post("/conversation", {"role": "user", "text": text})
        push_state_update()

    def on_system_response(self, text: str) -> None:
        """Call when system produces a response."""
        if text:
            workspace_state.add_conversation_turn("system", text)
            self._post("/conversation", {"role": "system", "text": text})
            push_state_update()

    def reset_objects(self) -> None:
        """Reset all objects to table state. Call at session start."""
        for obj in self._objects:
            obj["in_bin"] = False
            obj["in_tray"] = False
            obj["highlighted"] = False
        self._bin_count = 0
        self._tray_count = 0
        self._current_target_object_id = None
        self._push_workspace()

    def on_orchestrator_update(self, status: dict) -> None:
        """Call after each orchestrator tick with current status."""
        patch = {
            "intentos_state": status.get("intentos_state", "IDLE"),
            "kernel_state": status.get("kernel_state", "IDLE"),
            "false_executions": status.get("false_executions", 0),
            "goal": status.get("goal", ""),
            "nodes_total": status.get("nodes_total", 0),
            "nodes_complete": status.get("nodes_complete", 0),
            "plan_source": status.get("plan_source", ""),
            "uncertainty_max": status.get("uncertainty_max", 0.0),
            "task_graph": status.get("task_graph", []),
            "current_node": self._get_current_node(status),
        }
        workspace_state.update(patch)
        self._post("/state", patch)
        push_state_update()

    def on_node_complete(
        self,
        node_id: str,
        action_type: str,
        success: bool,
        parameters: dict = None,
    ) -> None:
        """Call when a TaskGraph node finishes."""
        if not success:
            return

        moved_to_destination = False
        destination = "bin"
        if action_type == "reach" and parameters:
            self._current_target_object_id = parameters.get("object_id")

        if action_type == "move":
            target_object_id = self._current_target_object_id
            if target_object_id is None and parameters:
                target_object_id = parameters.get("object_id")

            if parameters and parameters.get("target") == "tray":
                destination = "tray"

            def mark_object(obj):
                if destination == "tray":
                    obj["in_tray"] = True
                    self._tray_count += 1
                else:
                    obj["in_bin"] = True
                    self._bin_count += 1

            if target_object_id is not None:
                for obj in self._objects:
                    obj_body_id = self._label_map.get(obj["id"])
                    if obj_body_id == target_object_id:
                        mark_object(obj)
                        moved_to_destination = True
                        self._current_target_object_id = None
                        break

            if not moved_to_destination:
                for obj in self._objects:
                    if not obj["in_bin"] and not obj["in_tray"]:
                        mark_object(obj)
                        moved_to_destination = True
                        self._current_target_object_id = None
                        break

            for obj in self._objects:
                obj["highlighted"] = False
        ws = self._build_workspace_dict()
        ws["arm_position"] = "home"
        patch = {"workspace": ws}
        workspace_state.update(patch)
        self._post("/state", patch)
        if moved_to_destination:
            if destination == "tray":
                self._add_system_turn(
                    f"✓ Item placed in tray. {self._tray_count} in tray so far."
                )
            else:
                self._add_system_turn(
                    f"✓ Item placed in bin. {self._bin_count} in bin so far."
                )
        push_state_update()

    def on_goal_submitted(self, goal: str) -> None:
        """Call when a new goal is accepted."""
        for obj in self._objects:
            obj["highlighted"] = False
        for obj in self._objects:
            if not obj["in_bin"] and not obj["in_tray"]:
                obj["highlighted"] = True
                break
        ws = self._build_workspace_dict()
        ws["arm_position"] = "home"
        patch = {
            "goal": goal,
            "workspace": ws,
        }
        workspace_state.update(patch)
        self._post("/state", patch)
        push_state_update()

    def on_execution_start(self, object_label: str = None) -> None:
        """Call when arm starts moving."""
        ws = self._build_workspace_dict()
        ws["arm_position"] = "moving"
        patch = {"workspace": ws}
        workspace_state.update(patch)
        self._post("/state", patch)
        if object_label:
            msg = f"Moving the {object_label} toward the bin…"
        else:
            msg = "Moving the nearest item toward the bin…"
        self._add_system_turn(msg)
        push_state_update()

    def on_execution_complete(self, bin_count: int) -> None:
        """Call when execution finishes."""
        for obj in self._objects:
            obj["highlighted"] = False
        ws = self._build_workspace_dict()
        ws["arm_position"] = "home"
        ws["table_count"] = sum(
            1 for obj in self._objects if not obj["in_bin"] and not obj["in_tray"]
        )
        patch = {"workspace": ws}
        workspace_state.update(patch)
        self._post("/state", patch)
        table_remaining = max(0, len(self._objects) - self._bin_count - self._tray_count)
        msg = (
            f"Done. {table_remaining} item(s) still on table."
            if table_remaining > 0
            else "Table is clear."
        )
        self._add_system_turn(msg)
        push_state_update()

    @staticmethod
    def _init_objects(preset: Optional[dict]) -> list[dict]:
        if not preset:
            return []
        objects = []
        for obj in preset.get("objects", []):
            obj_id = obj.get("id", "")
            x, y = _PRESET_POSITIONS.get(obj_id, (0.4, 0.4))
            objects.append(
                {
                    "id": obj_id,
                    "label": obj.get("label", obj_id.replace("_", " ")),
                    "color": _OBJECT_COLORS.get(obj_id, "#bdc3c7"),
                    "x": x,
                    "y": y,
                    "in_bin": False,
                    "in_tray": False,
                    "highlighted": False,
                    "visible": obj.get("visible", True),
                }
            )
        return objects

    def _build_workspace_dict(self) -> dict:
        return {
            "objects": list(self._objects),
            "arm_position": "home",
            "arm_target": self._current_target(),
            "bin_count": self._bin_count,
            "tray_count": self._tray_count,
            "table_count": sum(
                1 for obj in self._objects if not obj["in_bin"] and not obj["in_tray"]
            ),
        }

    def _push_workspace(self) -> None:
        patch = {"workspace": self._build_workspace_dict()}
        workspace_state.update(patch)
        self._post("/state", patch)
        push_state_update()

    def _move_next_object_to_bin(self) -> bool:
        for obj in self._objects:
            if not obj["in_bin"] and not obj["in_tray"]:
                obj["in_bin"] = True
                obj["highlighted"] = False
                self._bin_count += 1
                return True
        return False

    def _current_target(self) -> Optional[dict]:
        for obj in self._objects:
            if obj.get("highlighted"):
                return {"x": obj["x"], "y": obj["y"]}
        return None

    @staticmethod
    def _get_current_node(status: dict) -> str:
        for node in status.get("task_graph", []):
            if node.get("status") in {"RUNNING", "IN_PROGRESS"}:
                return node.get("node_id", "")
        for node in status.get("task_graph", []):
            if node.get("status") == "PENDING":
                return node.get("node_id", "")
        return ""

    def _post(self, path: str, payload: dict) -> None:
        try:
            httpx.post(f"{self._monitor_url}{path}", json=payload, timeout=0.15)
        except Exception:
            pass

    def _add_system_turn(self, text: str) -> None:
        workspace_state.add_conversation_turn("system", text)
        self._post("/conversation", {"role": "system", "text": text})
