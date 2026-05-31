from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


AMBIGUOUS_WORDS = {
    "that",
    "this",
    "there",
    "here",
    "it",
    "left",
    "right",
    "side",
    "area",
    "corner",
    "over",
    "near",
    "far",
    "middle",
    "center",
}


@dataclass
class PresetObject:
    id: str
    label: str
    side: Optional[str] = None
    visible: bool = True
    color: Optional[str] = None
    blocked_by: Optional[str] = None


@dataclass
class PresetWorldState:
    objects: list[PresetObject]
    failure_type: Optional[str]
    missing_object: Optional[str]
    blocked_object: Optional[str]
    blocking_object: Optional[str]
    bin_count: int = 0


@dataclass
class InjectionResult:
    world_state: PresetWorldState
    scene_summary: str
    pre_plan_failure: Optional[str]
    should_block_plan: bool


class PresetSceneInjector:
    """
    Reads a preset dict and produces scene state plus pre-plan failure checks.
    Called by CommandLoop before submit_goal().
    """

    def __init__(self, preset: dict):
        self._preset = preset
        self._world_state = self._build_world_state(preset)

    def inject(self, goal: str) -> InjectionResult:
        """
        Given a goal string and preset, return:
          - world_state: enriched scene for presenter
          - scene_summary: text for planner
          - pre_plan_failure: human message if should block
          - should_block_plan: True if system should not plan
        """
        failure = self._preset.get("failure_injection", {})
        failure_type = failure.get("type") if isinstance(failure, dict) else None

        if failure_type == "object_missing":
            missing = failure.get("missing_object", "")
            if self._goal_references_object(goal, missing):
                return InjectionResult(
                    world_state=self._world_state,
                    scene_summary=self._build_scene_summary(),
                    pre_plan_failure=(
                        f"I can't find the {missing.replace('_', ' ')} "
                        "on the table. It doesn't seem to be here."
                    ),
                    should_block_plan=True,
                )

        if failure_type == "spatial_block":
            blocked = failure.get("blocked_object", "")
            blocker = failure.get("blocking_object", "")
            if self._goal_references_object(goal, blocked):
                return InjectionResult(
                    world_state=self._world_state,
                    scene_summary=self._build_scene_summary(),
                    pre_plan_failure=(
                        f"I can see the {blocked.replace('_', ' ')}, "
                        f"but the {blocker.replace('_', ' ')} is in the way.\n"
                        f"Should I move the {blocker.replace('_', ' ')} "
                        f"first, then get the {blocked.replace('_', ' ')}?"
                    ),
                    should_block_plan=True,
                )

        if self._is_ambiguous(goal):
            sides = self._detect_sides()
            if len(sides) > 1:
                options = " or ".join(
                    f"{side} side ({', '.join(obj.label for obj in objs)})"
                    for side, objs in sides.items()
                )
                return InjectionResult(
                    world_state=self._world_state,
                    scene_summary=self._build_scene_summary(),
                    pre_plan_failure=(
                        "I want to make sure I get this right - "
                        f"which did you mean?\n  · {options}"
                    ),
                    should_block_plan=True,
                )

        return InjectionResult(
            world_state=self._world_state,
            scene_summary=self._build_scene_summary(),
            pre_plan_failure=None,
            should_block_plan=False,
        )

    def get_world_state(self) -> PresetWorldState:
        return self._world_state

    @staticmethod
    def _build_world_state(preset: dict) -> PresetWorldState:
        failure = preset.get("failure_injection", {})
        failure_type = failure.get("type") if isinstance(failure, dict) else None

        objects = []
        for obj in preset.get("objects", []):
            obj_id = obj.get("id", "")
            objects.append(
                PresetObject(
                    id=obj_id,
                    label=obj.get("label", obj_id.replace("_", " ")),
                    side=obj.get("side"),
                    visible=obj.get("visible", True),
                    color=obj.get("color"),
                    blocked_by=(
                        failure.get("blocking_object")
                        if failure_type == "spatial_block"
                        and obj_id == failure.get("blocked_object")
                        else None
                    ),
                )
            )

        return PresetWorldState(
            objects=objects,
            failure_type=failure_type,
            missing_object=(
                failure.get("missing_object")
                if failure_type == "object_missing"
                else None
            ),
            blocked_object=(
                failure.get("blocked_object")
                if failure_type == "spatial_block"
                else None
            ),
            blocking_object=(
                failure.get("blocking_object")
                if failure_type == "spatial_block"
                else None
            ),
        )

    def _build_scene_summary(self) -> str:
        ws = self._world_state
        visible = [obj for obj in ws.objects if obj.visible]
        if not visible:
            return "Table appears empty."
        labels = ", ".join(obj.label for obj in visible)
        return f"{len(visible)} object(s) on table: {labels}. Bin count: {ws.bin_count}."

    @staticmethod
    def _goal_references_object(goal: str, object_id: str) -> bool:
        """True if goal text mentions this object by id or label words."""
        goal_lower = goal.lower()
        label = object_id.replace("_", " ").lower()
        words = [word for word in label.split() if len(word) > 2]
        if label in goal_lower:
            return True
        if words and words[0] in goal_lower:
            return True
        return object_id.lower() in goal_lower

    @staticmethod
    def _is_ambiguous(goal: str) -> bool:
        words = set(goal.lower().split())
        return bool(words & AMBIGUOUS_WORDS)

    def _detect_sides(self) -> dict:
        """Return dict of side to objects for objects with side labels."""
        sides: dict = {}
        for obj in self._world_state.objects:
            if obj.side:
                sides.setdefault(obj.side, []).append(obj)
        return sides
