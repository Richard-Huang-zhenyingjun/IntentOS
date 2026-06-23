"""
HumanPresenter - translates IntentOS internal state into plain English.

Rules:
  - Human Mode output never contains technical terms
  - Debug Mode output shows everything
  - This class has no side effects - pure translation only
  - Never called from orchestrator internals
  - Only the CommandLoop calls this
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Optional

from src.intentos.recovery import MAX_RETRIES_PER_NODE


@dataclass
class SceneDescription:
    """
    What the presenter knows about the current workspace.
    Populated by CommandLoop from world state before calling presenter.
    """

    objects: list[dict]
    arm_position: str
    bin_count: int
    tray_count: int
    table_count: int


@dataclass(frozen=True)
class HandoffObject:
    """One object in the verified handoff state."""

    object_id: int
    label: str
    status: str  # placed | skipped | remaining | unknown
    location: str = "unknown"  # bin | tray | table | unknown
    reason: Optional[str] = None


@dataclass(frozen=True)
class HandoffState:
    """Verified objective state at the moment control returns to the user."""

    goal: str
    reason: str
    objects: list[HandoffObject]
    cycles: Optional[int] = None
    warnings: tuple[str, ...] = ()


class HumanPresenter:
    """
    Translates internal IntentOS state to human-readable strings.

    Two modes:
      Human Mode (default) - plain English, no internals
      Debug Mode           - full technical state, toggled per session
    """

    def __init__(self):
        self._debug_mode = False
        self._id_to_label = {}

    def set_label_map(self, label_map: dict) -> None:
        """
        label_map: {"red_block": 4, "blue_block": 5, ...}
        _id_to_label: {4: "red_block", 5: "blue_block", ...}
        """
        self._id_to_label = {
            int(body_id): label
            for label, body_id in label_map.items()
        }

    def toggle_debug(self) -> str:
        self._debug_mode = not self._debug_mode
        return "[DEBUG ON]" if self._debug_mode else "[DEBUG OFF]"

    @property
    def is_debug(self) -> bool:
        return self._debug_mode

    def present_proposal(
        self,
        goal: str,
        scene: SceneDescription,
        plan_nodes: list[dict],
        uncertainty_max: float,
        plan_source: str,
        estimated_duration_s: float,
    ) -> str:
        """
        Translate a plan into a human-readable proposal.
        This is the most important method - what the user reads before confirming.
        """
        if self._debug_mode:
            return self._debug_proposal(
                goal,
                plan_nodes,
                uncertainty_max,
                plan_source,
                estimated_duration_s,
            )

        scene_summary = self._describe_scene(scene)
        action_summary = self._describe_plan(plan_nodes, scene)
        warning = self._uncertainty_warning(uncertainty_max)
        time_str = self._format_duration(estimated_duration_s)

        lines = []
        if scene_summary:
            lines.append(scene_summary)
        lines.append(action_summary)
        if warning:
            lines.append(warning)
        lines.append("")
        lines.append(f"This will take about {time_str}. Confirm?")

        return "\n".join(lines)

    def present_checkpoint(
        self,
        segment_summary: str,
        nodes_done: int,
        nodes_total: int,
        uncertainty_max: float,
    ) -> str:
        """Mid-execution checkpoint - shown between segments."""
        if self._debug_mode:
            return (
                f"[DEBUG] Checkpoint: {nodes_done}/{nodes_total} steps complete. "
                f"Next segment uncertainty={uncertainty_max:.2f}"
            )

        done_pct = int(100 * nodes_done / max(nodes_total, 1))
        warning = self._uncertainty_warning(uncertainty_max)

        lines = [f"Halfway there ({done_pct}% done)."]
        lines.append(f"Next: {segment_summary}")
        if warning:
            lines.append(warning)
        lines.append("Continue?")
        return "\n".join(lines)

    def present_node_start(self, node: dict, scene: SceneDescription) -> str:
        """One-line status as a node begins."""
        if self._debug_mode:
            return f"[DEBUG] Starting node {node.get('node_id')} ({node.get('action_type')})"
        return self._describe_node_action(node, scene, tense="present")

    def present_node_done(self, node: dict, scene: SceneDescription) -> str:
        """One-line confirmation as a node completes."""
        if self._debug_mode:
            return f"[DEBUG] ✓ Node {node.get('node_id')} complete"
        return "  ✓ " + self._describe_node_action(node, scene, tense="past")

    def present_completion(
        self,
        goal: str,
        nodes_done: int,
        duration_s: float,
        final_scene: SceneDescription,
        task_graph: Optional[list[dict]] = None,
    ) -> str:
        """Task complete summary."""
        if self._debug_mode:
            return (
                f"[DEBUG] Goal complete. {nodes_done} nodes. "
                f"{duration_s:.1f}s. false_executions=0"
            )

        graph_summary = self._completion_summary_from_graph(task_graph or [])
        if graph_summary is not None:
            return graph_summary

        table_str = (
            f"{final_scene.table_count} item(s) still on table"
            if final_scene.table_count > 0
            else "table is clear"
        )
        bin_str = (
            f"{final_scene.bin_count} item(s) in bin"
            if final_scene.bin_count > 0
            else ""
        )
        tray_str = (
            f"{final_scene.tray_count} item(s) in tray"
            if final_scene.tray_count > 0
            else ""
        )

        summary_parts = [p for p in [table_str, bin_str, tray_str] if p]
        summary = ", ".join(summary_parts) if summary_parts else "workspace updated"

        time_str = self._format_duration(duration_s)
        return f"Done in {time_str}. {summary.capitalize()}."

    def present_handoff_summary(self, state: HandoffState) -> str:
        """Honest objective handoff derived from verified object buckets."""
        if self._debug_mode:
            return (
                f"[DEBUG] Handoff reason={state.reason} "
                f"objects={[(obj.object_id, obj.status, obj.location, obj.reason) for obj in state.objects]}"
            )

        placed = [obj for obj in state.objects if obj.status == "placed"]
        skipped = [obj for obj in state.objects if obj.status == "skipped"]
        remaining = [obj for obj in state.objects if obj.status == "remaining"]
        unknown = [obj for obj in state.objects if obj.status == "unknown"]

        lines: list[str] = []
        if state.reason == "satisfied" and not remaining and not skipped and not unknown:
            if placed:
                lines.append(f"Table's clear. I placed {len(placed)} item(s).")
            else:
                lines.append("Table's clear. There wasn't anything left to move.")
        elif state.reason == "satisfied":
            lines.append("Finished the reachable work.")
        elif state.reason == "max_cycles":
            lines.append(
                f"Table still isn't clear after {state.cycles or 0} rounds."
            )
        elif state.reason == "user_stopped":
            lines.append("Stopped safely.")
        elif state.reason == "user_left_it":
            lines.append("Okay, leaving it here.")
        elif state.reason == "no_progress":
            lines.append("I stopped because the objective made no progress.")
        elif state.reason.startswith("refused"):
            lines.append(f"I stopped because {state.reason}.")
        else:
            lines.append("Here's where I stopped.")

        state_parts = []
        if placed:
            state_parts.append(
                f"placed {len(placed)} item(s)"
                + self._location_suffix(placed)
            )
        if skipped:
            state_parts.append(
                "left "
                + self._join_readable([obj.label for obj in skipped])
                + " on the table"
            )
        if remaining:
            state_parts.append(
                f"{len(remaining)} item(s) still on the table"
            )
        if unknown:
            state_parts.append(
                "state unclear for "
                + self._join_readable([obj.label for obj in unknown])
            )
        if state_parts and not (
            state.reason == "satisfied" and not remaining and not skipped and not unknown
        ):
            lines.append("Current state: " + "; ".join(state_parts) + ".")

        for obj in skipped:
            phrase = self._handoff_reason_phrase(obj.reason)
            lines.append(
                f"I {phrase} {obj.label} after {MAX_RETRIES_PER_NODE} tries, "
                "so I left it on the table."
            )
        for obj in unknown:
            lines.append(
                f"I can't honestly place {obj.label} in a final bucket "
                "because the execution result and live scene disagree."
            )

        if remaining or skipped or unknown:
            if state.reason == "max_cycles":
                lines.append("Keep going, or leave it?")
            elif state.reason in {"user_stopped", "user_left_it", "no_progress"} or state.reason.startswith("refused"):
                lines.append("Say 'clean the table' or 'keep going' to continue.")
            elif state.reason == "satisfied":
                lines.append("Say 'clean the table' if you want me to try the remaining item(s).")

        return " ".join(lines)

    @staticmethod
    def _location_suffix(objects: list[HandoffObject]) -> str:
        locations = {obj.location for obj in objects}
        if locations == {"bin"}:
            return " in the bin"
        if locations == {"tray"}:
            return " in the tray"
        if locations <= {"bin", "tray"}:
            return " in the bin/tray"
        return ""

    @staticmethod
    def _handoff_reason_phrase(reason: Optional[str]) -> str:
        reason_lower = str(reason or "").lower()
        if "grasp_failed" in reason_lower or "grasp_no_object" in reason_lower:
            return "couldn't grip"
        if "unreachable" in reason_lower or "ik_out_of_limits" in reason_lower:
            return "couldn't reach"
        if "move_not_arrived" in reason_lower or "move_invalid_pose" in reason_lower:
            return "couldn't place"
        if "timeout" in reason_lower:
            return "took too long with"
        return "couldn't move"

    def _completion_summary_from_graph(self, task_graph: list[dict]) -> Optional[str]:
        chains = self._object_chains(task_graph)
        if not chains:
            return None

        placed = 0
        skipped: list[tuple[str, str]] = []
        for nodes in chains.values():
            statuses = {str(node.get("status", "")) for node in nodes}
            if "SKIPPED" in statuses:
                skipped.append(self._describe_skipped_chain(nodes))
            elif statuses and all(status == "DONE" for status in statuses):
                placed += 1

        total = len(chains)
        if not skipped:
            return None

        if placed == 0:
            prefix = f"I couldn't clean any of the {total} item(s)."
        else:
            prefix = f"Cleaned {placed} of {total}."

        skip_sentences = [
            (
                f"I {reason} {label} after {MAX_RETRIES_PER_NODE} tries, "
                "so I left it on the table."
            )
            for label, reason in skipped
        ]

        labels = [label for label, _reason in skipped]
        if len(labels) == 1:
            retry_text = f"Want me to try {labels[0]} again, or leave it?"
        else:
            retry_text = (
                "Want me to try "
                f"{self._join_readable(labels)} again, or leave them?"
            )

        return " ".join([prefix, *skip_sentences, retry_text])

    @staticmethod
    def _object_chains(task_graph: list[dict]) -> dict[int, list[dict]]:
        chains: dict[int, list[dict]] = {}
        for node in task_graph:
            node_id = str(node.get("node_id", ""))
            match = re.match(r"^(reach|grasp|move|release)_(\d+)$", node_id)
            if not match:
                continue
            chains.setdefault(int(match.group(2)), []).append(node)
        return dict(sorted(chains.items()))

    def _describe_skipped_chain(self, nodes: list[dict]) -> tuple[str, str]:
        label = self._label_skipped_chain(nodes)
        reason = self._skip_reason_phrase(nodes)
        return label, reason

    def _label_skipped_chain(self, nodes: list[dict]) -> str:
        for node in nodes:
            params = node.get("parameters") or {}
            object_id = params.get("object_id")
            if object_id is not None:
                return self._label_object(f"object_{object_id}")
            target = params.get("target")
            if target:
                return self._label_object(str(target))
        return "that item"

    @staticmethod
    def _skip_reason_phrase(nodes: list[dict]) -> str:
        reason = " ".join(
            str(node.get("error") or "")
            for node in nodes
            if node.get("status") == "SKIPPED" or node.get("error")
        ).lower()
        if "grasp_failed" in reason or "grasp_no_object" in reason:
            return "couldn't grip"
        if "unreachable" in reason or "ik_out_of_limits" in reason:
            return "couldn't reach"
        if "move_not_arrived" in reason or "move_invalid_pose" in reason:
            return "couldn't place"
        if "timeout" in reason:
            return "took too long with"
        return "couldn't move"

    @staticmethod
    def _join_readable(items: list[str]) -> str:
        if len(items) <= 1:
            return items[0] if items else ""
        if len(items) == 2:
            return f"{items[0]} and {items[1]}"
        return f"{', '.join(items[:-1])}, and {items[-1]}"

    def present_pause(
        self,
        current_action: str,
        done: list[str],
        pending: list[str],
        holding: Optional[str],
    ) -> str:
        """State shown immediately after user says 'pause'."""
        if self._debug_mode:
            return (
                "[DEBUG] Paused mid-execution. "
                f"Done: {done}. Pending: {pending}. Holding: {holding}"
            )

        lines = ["Paused."]
        if holding:
            lines.append(f"I'm holding the {holding} safely.")
        if done:
            lines.append("\nWhat's done:")
            for item in done:
                lines.append(f"  ✓ {item}")
        if pending:
            lines.append("\nStill to do:")
            for item in pending:
                lines.append(f"  · {item}")
        lines.append(
            '\nSay "resume" to continue, "stop" to end here, '
            'or "undo" to reverse what\'s done.'
        )
        return "\n".join(lines)

    def present_stop(
        self,
        done: list[str],
        undone: list[str],
    ) -> str:
        """State after user says 'stop' and arm has placed object safely."""
        if self._debug_mode:
            return f"[DEBUG] Stopped. Completed: {done}. Remaining: {undone}"

        lines = []
        if done:
            lines.append("What's done:")
            for item in done:
                lines.append(f"  ✓ {item}")
        if undone:
            lines.append("\nStill on the table:")
            for item in undone:
                lines.append(f"  · {item}")
        lines.append(
            '\nSay "continue cleaning" to pick up where we left off, '
            'or "undo" to return everything to where it started.'
        )
        return "\n".join(lines)

    def present_failure(
        self,
        failed_action: str,
        reason: str,
        recovery_class: str,
        options: Optional[list[str]] = None,
    ) -> str:
        """Translate a failure into a human-facing recovery prompt."""
        if self._debug_mode:
            return (
                f"[DEBUG] Failure: {failed_action}. "
                f"Reason: {reason}. Class: {recovery_class}. "
                f"Options: {options}"
            )

        human_reason = self._translate_failure_reason(reason, failed_action)

        if recovery_class == "TRANSIENT":
            return f"{human_reason} Let me try again..."

        if recovery_class == "REPLANNING":
            lines = [human_reason]
            if options:
                for i, opt in enumerate(options, 1):
                    lines.append(f"  Option {i}: {opt}")
            else:
                lines.append('Say "retry" to try again or "skip" to move on.')
            return "\n".join(lines)

        return (
            f"{human_reason}\n"
            "I can't continue without your help. "
            'Say "retry", "skip this step", or "stop".'
        )

    def present_ambiguity(
        self,
        goal: str,
        options: list[dict],
    ) -> str:
        """Ask user to clarify an ambiguous goal."""
        if self._debug_mode:
            opts_str = "\n".join(
                f"  [{o['key']}] {o['description']} "
                f"(confidence={o['confidence']:.2f})"
                for o in options
            )
            return f"[DEBUG] Ambiguous goal: {goal!r}\nOptions:\n{opts_str}"

        lines = ["I want to make sure I get this right - which did you mean?"]
        lines.append("")
        for opt in options:
            lines.append(f"  · {opt['description']}")
        return "\n".join(lines)

    def present_debug_state(self, state: dict) -> str:
        """Full debug dump - only shown in Debug Mode or on explicit request."""
        lines = ["[DEBUG STATE]"]

        if "intentos_state" in state:
            lines.append(f"  IntentOS state:    {state['intentos_state']}")
        if "kernel_state" in state:
            ks = state["kernel_state"]
            intentos_s = state.get("intentos_state", "")
            note = ""
            if ks == "EXECUTING" and intentos_s == "COMPLETE":
                note = "  (Phase 2 finishing release - will settle shortly)"
            lines.append(f"  Kernel state:      {ks}{note}")
        if "false_executions" in state:
            lines.append(f"  false_executions:  {state['false_executions']}")
        if "plan_source" in state:
            lines.append(f"  Plan source:       {state['plan_source']}")
        if "planning_ms" in state:
            lines.append(f"  Planning time:     {state['planning_ms']:.0f}ms")
        if "nodes_total" in state:
            lines.append(
                "  Nodes:             "
                f"{state.get('nodes_complete', 0)}/{state['nodes_total']}"
            )
        if "current_token" in state:
            lines.append(f"  Token:             {state['current_token']}")
        if "uncertainty_max" in state:
            lines.append(f"  Max uncertainty:   {state['uncertainty_max']:.2f}")
        if "recovery_events" in state:
            lines.append(f"  Recovery events:   {state['recovery_events']}")
        if "task_graph" in state:
            lines.append("\n  Task graph:")
            for node in state["task_graph"]:
                lines.append(
                    f"    [{node.get('status', '?'):10s}] "
                    f"{node.get('node_id', '?'):20s} "
                    f"{node.get('action_type', '?'):10s} "
                    f"uncertainty={node.get('uncertainty', 0):.2f}"
                )

        return "\n".join(lines)

    def _describe_scene(self, scene: SceneDescription) -> str:
        """Opening line describing what the system sees."""
        total = scene.table_count
        if total == 0:
            return ""
        if total == 1:
            return "I can see 1 item on the table."
        return f"I can see {total} loose items on the table."

    def _describe_plan(self, plan_nodes: list[dict], scene: SceneDescription) -> str:
        """
        Translate a list of nodes into a plain-English action summary.
        Groups reach+grasp+move+release into single object movements.
        """
        movements = self._group_into_movements(plan_nodes)

        if not movements:
            if scene.table_count > 0:
                return f"I'll clear the {scene.table_count} item(s) from the table."
            return "I'll tidy up the workspace."

        if len(movements) == 1:
            return f"I'll {movements[0].lower()}."

        lines = ["I'll:"]
        for movement in movements:
            lines.append(f"  · {movement}")
        return "\n".join(lines)

    def _group_into_movements(self, nodes: list[dict]) -> list[str]:
        """
        Convert technical node sequences into plain movement descriptions.
        reach(target=X)+grasp+move(target=Y)+release -> "move X to Y"
        """
        movements = []
        current_object = "the object"

        for node in nodes:
            action = node.get("action_type", "")
            params = node.get("parameters", {})

            if action == "reach":
                current_object = params.get("target", "the object")
                continue

            if action == "grasp":
                continue

            if action == "move":
                dest = params.get("target") or params.get("destination", "")
                dest_label = self._label_destination(dest)
                target_label = self._label_object(current_object)
                movements.append(f"Move {target_label} {dest_label}")
                continue

            if action == "release":
                current_object = "the object"
                continue

            if action == "home":
                movements.append("Return arm to resting position")
                current_object = "the object"

        return movements if movements else ["Tidy up the workspace"]

    def _label_object(self, target: str) -> str:
        import re

        labels = {
            "nearest_object": "the nearest loose item",
            "red_block":      "the red block",
            "blue_block":     "the blue block",
            "yellow_block":   "the yellow block",
            "tool":           "the tool",
            "screwdriver":    "the screwdriver",
        }
        if target in labels:
            return labels[target]

        # Handle "object_4" format: extract body_id and look up label.
        m = re.match(r"^object_(\d+)$", target)
        if m:
            body_id = int(m.group(1))
            label = self._id_to_label.get(body_id)
            if label:
                return f"the {label.replace('_', ' ')}"
            label = self._id_to_label.get(str(body_id))
            if label:
                return f"the {label.replace('_', ' ')}"
            return "the nearest item"

        if target in self._id_to_label:
            return f"the {self._id_to_label[target]}"

        return f"the {target.replace('_', ' ')}"

    @staticmethod
    def _label_destination(dest: str) -> str:
        """Turn internal destination IDs into readable labels."""
        labels = {
            "bin": "into the bin",
            "tray": "into the tray",
            "home": "to its original position",
        }
        return labels.get(dest, f"to the {dest.replace('_', ' ')}")

    @staticmethod
    def _uncertainty_warning(uncertainty_max: float) -> Optional[str]:
        """Return a warning string if uncertainty is high enough to mention."""
        if uncertainty_max >= 0.85:
            return "⚠ I'm not confident I can do this safely right now."
        if uncertainty_max >= 0.70:
            return "I'm not fully sure about one of these steps - I'll be careful."
        if uncertainty_max >= 0.60:
            return "One of these steps is a bit tricky."
        return None

    @staticmethod
    def _translate_failure_reason(reason: str, action: str) -> str:
        """Translate internal failure reasons to human-readable explanations."""
        reason_lower = reason.lower()
        if "not found" in reason_lower or "missing" in reason_lower:
            return "I can't find that object on the table."
        if "moved" in reason_lower:
            return "That object has moved since I planned this."
        if "blocked" in reason_lower or "collision" in reason_lower:
            return "Something is in the way."
        if "unreachable" in reason_lower or "out of range" in reason_lower:
            return "I can't reach that from here."
        if "grasp slip" in reason_lower:
            return "I lost my grip on that."
        if "ik timeout" in reason_lower or "path" in reason_lower:
            return "I couldn't find a safe path to get there."
        if "joint limit" in reason_lower:
            return "I can't bend that far."
        if "gripper" in reason_lower:
            return "There's a problem with the gripper."
        if "safety" in reason_lower or "emergency" in reason_lower:
            return "A safety issue came up - I stopped immediately."
        return f"Something went wrong while trying to {action.replace('_', ' ')}."

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Round duration to nearest 5 seconds for human readability."""
        if seconds < 5:
            return "a few seconds"
        rounded = max(5, int(math.ceil(seconds / 5.0) * 5))
        return f"{rounded} seconds"

    def _debug_proposal(
        self,
        goal,
        nodes,
        uncertainty_max,
        plan_source,
        duration_s,
    ) -> str:
        lines = [f"[DEBUG] Goal: {goal!r}"]
        lines.append(f"  Plan source:    {plan_source}")
        lines.append(f"  Nodes:          {len(nodes)}")
        lines.append(f"  Max uncertainty: {uncertainty_max:.2f}")
        lines.append(f"  Est. duration:  {duration_s:.1f}s")
        lines.append("  Nodes:")
        for node in nodes:
            lines.append(
                f"    {node.get('node_id', '?'):20s} "
                f"{node.get('action_type', '?'):10s} "
                f"-> {node.get('parameters', {})}"
            )
        return "\n".join(lines)

    def _describe_node_action(
        self,
        node: dict,
        scene: SceneDescription,
        tense: str = "present",
    ) -> str:
        """One-line action description for execution updates."""
        del scene
        action = node.get("action_type", "")
        params = node.get("parameters", {})
        target = self._label_object(params.get("target", "object"))

        if action == "move":
            if tense == "past":
                return f"{target.capitalize()} -> {params.get('destination', 'done')}"
            return f"Moving {target}..."
        if action == "home":
            return "Returning arm to rest..." if tense == "present" else "Arm at rest."
        return f"Working on {target}..."
