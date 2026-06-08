"""
CommandLoop - typed natural language command interface for Smart Workspace v1.

Accepts:
  - Natural language goals
  - yes / no / pause / resume / stop / retry / skip
  - explain / why / show debug / hide debug / show plan

Never requires:
  - Specific key presses
  - Technical command names
  - Node IDs or segment references
"""
from __future__ import annotations

import time
import readline  # Enables arrow keys in input() on Mac/Linux
import select
import sys
from typing import Optional

from src.interaction.confirm_bridge import ConfirmBridge
from src.interaction.human_presenter import HumanPresenter, SceneDescription
from src.interaction.session_logger import SessionLogger
from src.intentos.orchestrator import IntentOSState


_CONFIRM_WORDS = {
    "yes",
    "confirm",
    "ok",
    "sure",
    "go ahead",
    "do it",
    "just do it",
    "yep",
    "y",
    "yeah",
    "proceed",
}
_CANCEL_WORDS = {
    "no",
    "cancel",
    "stop",
    "don't",
    "nope",
    "n",
    "abort",
    "nevermind",
    "never mind",
}
_PAUSE_WORDS = {"pause", "wait", "hold on", "hold", "stop for now"}
_RESUME_WORDS = {"resume", "continue", "go", "keep going", "carry on"}
_EXEC_STOP_WORDS = {
    "stop",
    "cancel",
    "halt",
    "abort",
    "freeze",
    "wait",
    "stop it",
    "stop now",
    "stop that",
}
_EXEC_PAUSE_WORDS = {"pause", "hold on", "hold"}
_UNDO_WORDS = {"undo", "put it back", "reverse", "go back", "undo that", "put them back"}
_RETRY_WORDS = {"retry", "try again", "try that again", "try once more"}
_SKIP_WORDS = {"skip", "skip that", "skip this step", "move on", "skip it", "ignore that"}
_EXPLAIN_WORDS = {
    "explain",
    "why",
    "what",
    "tell me more",
    "what are you doing",
    "why did you stop",
    "what happened",
    "what went wrong",
}
_DEBUG_ON = {"show debug", "debug on", "debug", "developer mode"}
_DEBUG_OFF = {"hide debug", "debug off", "normal mode"}
_SHOW_PLAN = {"show plan", "what's the plan", "what is the plan", "show me the plan", "show task"}
_EXIT_WORDS = {"exit", "quit", "bye", "goodbye", "q"}


def _classify(text: str) -> str:
    """Classify typed input into a command category."""
    t = text.strip().lower()
    if t in _CONFIRM_WORDS:
        return "CONFIRM"
    if t in _CANCEL_WORDS:
        return "CANCEL"
    if t in _PAUSE_WORDS:
        return "PAUSE"
    if t in _RESUME_WORDS:
        return "RESUME"
    if t in _UNDO_WORDS:
        return "UNDO"
    if t in _RETRY_WORDS:
        return "RETRY"
    if t in _SKIP_WORDS:
        return "SKIP"
    if t in _EXPLAIN_WORDS:
        return "EXPLAIN"
    if t in _DEBUG_ON:
        return "DEBUG_ON"
    if t in _DEBUG_OFF:
        return "DEBUG_OFF"
    if t in _SHOW_PLAN:
        return "SHOW_PLAN"
    if t in _EXIT_WORDS:
        return "EXIT"
    if t:
        return "GOAL"
    return "EMPTY"


class CommandLoop:
    """
    Main interaction loop for Smart Workspace v1.

    Usage:
        loop = CommandLoop(orchestrator, world, logger)
        loop.run()
    """

    PROMPT = "\n> "

    def __init__(
        self,
        orchestrator,
        world,
        logger: SessionLogger,
        preset_name: str = "default",
        preset_objects: list = None,
        state_bridge=None,
    ):
        self._orch = orchestrator
        self._world = world
        self._planner = getattr(orchestrator, "_planner", None)
        self._logger = logger
        self._presenter = HumanPresenter()
        self._preset = preset_name
        self._preset_objects = preset_objects or []
        self._label_map = {}
        self._injector: Optional[object] = None
        self._bridge_monitor = state_bridge
        self._browser_queue = None
        self._interpreter = None
        self._running = False
        self._last_plan: Optional[dict] = None
        self._tick_rate_hz = 10.0
        self._last_reported_complete = False
        self._last_reported_error = False
        self._task_start_time = 0.0
        self._bin_count = 0
        self._session_bin_count = 0
        self._tray_count = 0
        self._completed_node_ids: set[str] = set()
        self._moved_object_ids: set = set()
        self._bridge = ConfirmBridge(
            keyboard_source=world.decision_pipeline.router.get_source("keyboard"),
            phase2_orchestrator=world,
            auth_manager=world.auth_manager,
            intentos_orchestrator=self._orch,
            invariant_checker=world.executor._invariant_checker,
        )

    def set_preset(self, preset: dict) -> None:
        from src.interaction.preset_scene_injector import PresetSceneInjector

        self._injector = PresetSceneInjector(preset)
        self._bin_count = 0
        self._session_bin_count = 0
        self._tray_count = 0
        self._moved_object_ids = set()
        self._reset_planner_moved_objects()
        self._last_reported_complete = False
        self._last_reported_error = False
        if self._interpreter is not None and hasattr(self._interpreter, "reset_context"):
            self._interpreter.reset_context()
        if self._label_map:
            self._presenter.set_label_map(self._label_map)
        if self._bridge_monitor is not None:
            self._bridge_monitor.reset_objects()

    def set_label_map(self, label_map: dict) -> None:
        self._label_map = label_map
        self._presenter.set_label_map(label_map)

    def set_browser_queue(self, queue) -> None:
        """Connect browser command queue from monitor server."""
        self._browser_queue = queue

    def set_interpreter(self, interpreter) -> None:
        """Connect optional natural-language intent interpreter."""
        self._interpreter = interpreter

    def _heuristic_planner(self):
        return getattr(self._planner, "_heuristic", None)

    def _sync_moved_objects_to_planner(self) -> None:
        heuristic = self._heuristic_planner()
        if heuristic is None:
            return
        if hasattr(heuristic, "set_moved_objects"):
            heuristic.set_moved_objects(self._moved_object_ids)
        else:
            heuristic._moved_object_ids = set(self._moved_object_ids)

    def _mark_planner_object_moved(self, object_id: int) -> None:
        heuristic = self._heuristic_planner()
        if heuristic is None:
            return
        if hasattr(heuristic, "mark_object_moved"):
            heuristic.mark_object_moved(object_id)

    def _reset_planner_moved_objects(self) -> None:
        heuristic = self._heuristic_planner()
        if heuristic is None:
            return
        if hasattr(heuristic, "reset_moved_objects"):
            heuristic.reset_moved_objects()

    def run(self) -> None:
        """Start the interaction loop."""
        self._running = True
        self._print_welcome()
        print(self.PROMPT, end="", flush=True)

        try:
            while self._running:
                try:
                    processed_browser_command = self._process_browser_queue()
                    if processed_browser_command and self._running:
                        print(self.PROMPT, end="", flush=True)

                    user_input = self._read_terminal_input()
                except (KeyboardInterrupt, EOFError):
                    self._handle_exit()
                    break

                if user_input is None:
                    self._monitor_orchestrator_update()
                    continue

                user_input = user_input.strip()
                if not user_input:
                    continue

                self._process_user_command(user_input)
                if self._running:
                    print(self.PROMPT, end="", flush=True)
        finally:
            self._logger.close()

    def _read_terminal_input(self) -> Optional[str]:
        """Poll terminal input briefly so browser commands can be handled live."""
        try:
            ready, _, _ = select.select([sys.stdin], [], [], 1.0 / self._tick_rate_hz)
        except (OSError, ValueError):
            return input("")
        if not ready:
            return None
        return input("")

    def _process_browser_queue(self) -> bool:
        """Process queued browser commands, if any."""
        processed = False
        if self._browser_queue:
            while self._browser_queue:
                browser_cmd = self._browser_queue.popleft()
                if not browser_cmd:
                    continue
                print(f"\n> {browser_cmd}", flush=True)
                response = self._process_user_command(browser_cmd)

                if self._is_busy_response(response):
                    self._browser_queue.clear()
                    processed = True
                    break

                processed = True
                time.sleep(0.3)
        return processed

    def _process_user_command(
        self,
        user_input: str,
        suppress_busy_response: bool = False,
    ) -> Optional[str]:
        """Process a browser or terminal command through the same path."""
        original_input = user_input
        if self._interpreter:
            user_input = self._interpreter.interpret(user_input)

        self._monitor_user_input(original_input)
        if user_input == "__CLARIFY__":
            cmd = "CLARIFY"
            response = self._clarification_response(original_input)
        else:
            cmd = _classify(user_input)
            response = self._route(user_input, cmd)
        should_surface_response = not (
            suppress_busy_response and self._is_busy_response(response)
        )

        if response and should_surface_response:
            print(f"\n{response}", flush=True)
            self._monitor_system_response(response)

        self._logger.log_turn(
            user_input=original_input,
            command_class=cmd,
            system_response=response or "",
            orchestrator_state=self._orch.get_status(),
            debug_mode=self._presenter.is_debug,
        )

        self._tick_until_stable()
        self._maybe_print_execution_update()
        self._monitor_orchestrator_update()
        return response

    @staticmethod
    def _clarification_response(user_input: str) -> str:
        return (
            f"I don't have a clear action for {user_input!r}. "
            "Did you mean clean the table, or move specific items?"
        )

    @staticmethod
    def _is_busy_response(response: Optional[str]) -> bool:
        if not response:
            return False
        lowered = response.lower()
        return any(
            word in lowered
            for word in ("busy", "finishing", "not ready", "moment")
        )

    def _route(self, raw: str, cmd: str) -> Optional[str]:
        """Route classified command to appropriate handler."""
        if cmd == "GOAL":
            return self._handle_goal(raw)
        if cmd == "CONFIRM":
            return self._handle_confirm()
        if cmd == "CANCEL":
            return self._handle_cancel()
        if cmd == "PAUSE":
            return self._handle_pause()
        if cmd == "RESUME":
            return self._handle_resume()
        if cmd == "UNDO":
            return self._handle_undo()
        if cmd == "RETRY":
            return self._handle_retry()
        if cmd == "SKIP":
            return self._handle_skip()
        if cmd == "EXPLAIN":
            return self._handle_explain()
        if cmd == "DEBUG_ON":
            if not self._presenter.is_debug:
                self._presenter.toggle_debug()
            status = self._orch.get_status()
            return "[DEBUG ON]\n" + self._presenter.present_debug_state(status)
        if cmd == "DEBUG_OFF":
            if self._presenter.is_debug:
                return self._presenter.toggle_debug()
            return "[DEBUG already off]"
        if cmd == "SHOW_PLAN":
            return self._handle_show_plan()
        if cmd == "EXIT":
            self._handle_exit()
            return None
        if cmd == "EMPTY":
            return None
        return None

    def _handle_goal(self, goal: str) -> str:
        """Submit goal to IntentOS planner."""
        status = self._orch.get_status()
        state = status.get("intentos_state", "IDLE")

        if state == "EXECUTING":
            return 'I\'m still working on something. Say "pause" or "stop" first.'

        if state == "AWAITING_CONFIRM":
            return (
                "I'm waiting for your answer on the current plan. "
                'Say "yes" to confirm or "no" to cancel.'
            )

        if state in ("COMPLETE", "ABORTED", "ERROR"):
            self._orch.cancel()
            self._orch.tick()
            self._last_reported_complete = False
            self._last_reported_error = False
            settled = self._wait_for_phase2_idle(timeout_s=15.0)
            if not settled:
                # IntentOS already reached a terminal state; if Phase 2 is slow
                # to settle, reset the interaction layer and let the next goal proceed.
                self._orch._state = IntentOSState.IDLE
                settled = True
            self._orch._state = IntentOSState.IDLE

        scene = self._get_scene()
        scene_summary = self._build_scene_summary(scene)
        if self._injector is not None:
            injection = self._injector.inject(goal)
            if injection.should_block_plan:
                self._logger.log_turn(
                    user_input=goal,
                    command_class="GOAL_BLOCKED",
                    system_response=injection.pre_plan_failure or "",
                    orchestrator_state=self._orch.get_status(),
                    debug_mode=self._presenter.is_debug,
                )
                return injection.pre_plan_failure or ""
            scene_summary = injection.scene_summary

        self._sync_moved_objects_to_planner()
        accepted = self._orch.submit_goal(goal, scene_summary)
        if not accepted:
            return "I'm not ready for a new task right now."
        self._monitor_goal_submitted(goal)

        self._last_reported_complete = False
        self._last_reported_error = False
        self._completed_node_ids = set()
        self._bin_count = 0
        self._tray_count = 0
        self._task_start_time = time.monotonic()

        self._tick_until_state("AWAITING_CONFIRM", timeout_s=15.0)
        status = self._orch.get_status()

        if status.get("intentos_state") == "AWAITING_CONFIRM":
            return self._present_current_proposal(goal, scene, status)
        elif status.get("intentos_state") == "ABORTED":
            return "I couldn't put together a safe plan for that. Could you try rephrasing?"
        else:
            return "Something went wrong during planning."

    def _handle_confirm(self) -> str:
        """Handle yes/confirm."""
        state = self._orch.get_status().get("intentos_state")
        if state != "AWAITING_CONFIRM":
            return "There's nothing waiting for confirmation right now."

        self._monitor_system_response("Preparing authorization…")
        result = self._signal_confirm()
        if not result.success:
            return result.reason

        new_state = self._orch.get_status().get("intentos_state")
        if new_state not in ("EXECUTING", "COMPLETE"):
            return "Something went wrong. Try again."

        print("\nOn it.", flush=True)
        self._monitor_system_response("On it.")
        self._monitor_execution_start()
        self._task_start_time = time.monotonic()

        self._wait_for_execution_complete()
        return ""

    def _handle_cancel(self) -> str:
        """Handle no/cancel/stop."""
        state = self._orch.get_status().get("intentos_state")
        if state == "IDLE":
            return "Nothing is running."
        self._orch.cancel()
        return "Stopped."

    def _handle_pause(self) -> str:
        """Handle pause."""
        return "Pausing... (pause not yet wired - say 'stop' to halt)"

    def _handle_resume(self) -> str:
        """Handle resume."""
        return "Resuming... (resume not yet wired)"

    def _handle_undo(self) -> str:
        """Handle undo request."""
        return (
            "Undo is coming in v1.1. "
            "For now, say a new goal to move objects back manually."
        )

    def _handle_retry(self) -> str:
        """Handle retry."""
        return "Retrying... (retry not yet wired)"

    def _handle_skip(self) -> str:
        """Handle skip."""
        return "Skipping that step... (skip not yet wired)"

    def _handle_explain(self) -> str:
        """Handle explain/why."""
        status = self._orch.get_status()
        state = status.get("intentos_state", "IDLE")

        if state == "IDLE":
            return "I'm not doing anything right now. Give me a goal to work on."

        if self._presenter.is_debug:
            return self._presenter.present_debug_state(status)

        if state == "AWAITING_CONFIRM":
            goal = status.get("goal", "a task")
            return (
                f"I have a plan for: {goal!r}. "
                "I'm waiting for you to say yes before I do anything. "
                "Say 'show plan' to see what I intend to do."
            )
        if state == "EXECUTING":
            goal = status.get("goal", "that task")
            done = status.get("nodes_complete", 0)
            total = status.get("nodes_total", 0)
            return f"I'm working on: {goal!r}. Step {done} of {total} in progress."
        if state == "COMPLETE":
            goal = status.get("goal", "that task")
            bin_count = self._bin_count
            return (
                f"I completed the last task: {goal!r}. "
                "I moved 1 item into the bin "
                f"({bin_count} total in bin so far). "
                "Say the same goal again to continue."
            )
        if state == "ERROR":
            return (
                "Something went wrong and I stopped. "
                "Say \"retry\" to try again or give me a new goal."
            )
        return f"Current state: {state}."

    def _handle_show_plan(self) -> str:
        """Show plan - Human Mode shows readable summary, Debug shows graph."""
        status = self._orch.get_status()
        state = status.get("intentos_state", "IDLE")
        goal = status.get("goal", "")
        nodes = status.get("task_graph", [])

        if self._presenter.is_debug:
            return self._presenter.present_debug_state(status)

        if not goal:
            return "No plan is active right now."

        if state == "AWAITING_CONFIRM":
            movements = [n for n in nodes if n.get("action_type") == "move"]
            if movements:
                dest = movements[0].get("parameters", {}).get("target", "bin")
                return (
                    f"Plan: move the nearest item to the {dest}.\n"
                    "Waiting for your confirmation."
                )
            return f"Plan: {goal}. Waiting for your confirmation."

        if state == "COMPLETE":
            return (
                "Last plan: move the nearest item into the bin.\n"
                f"Completed. {self._bin_count} item(s) in bin so far."
            )

        if state == "EXECUTING":
            done = status.get("nodes_complete", 0)
            total = status.get("nodes_total", 0)
            return f"Executing: {goal}. Step {done}/{total}."

        return f"Current goal: {goal}. State: {state}."

    def _handle_exit(self) -> None:
        self._running = False
        print("\nSession ended. Goodbye.")

    def _tick_until_stable(self, max_ticks: int = 5) -> None:
        """Advance orchestrator a few ticks after each command."""
        for _ in range(max_ticks):
            self._orch.tick()
            self._monitor_orchestrator_update()
            time.sleep(1.0 / self._tick_rate_hz)

    def _maybe_print_execution_update(self) -> None:
        status = self._orch.get_status()
        state = status.get("intentos_state")

        if state == "COMPLETE" and not self._last_reported_complete:
            self._last_reported_complete = True
            done = status.get("nodes_complete", 0)
            total = status.get("nodes_total", 0)
            print(f"\n  ✓ Done. ({done}/{total} steps completed)")
            print(self.PROMPT, end="", flush=True)

        elif state == "ERROR" and not self._last_reported_error:
            self._last_reported_error = True
            print("\n  Something went wrong. Say 'explain' for details.")
            print(self.PROMPT, end="", flush=True)

    def _poll_input_during_execution(self):
        """
        Non-blocking check for a stop/pause command while executing.

        Returns one of: "STOP", "PAUSE", or None. Browser queue commands that
        are not execution interrupts are put back for the normal input loop.
        """
        if self._browser_queue:
            remaining = []
            hit = None
            while self._browser_queue:
                cmd = self._browser_queue.popleft()
                low = (cmd or "").strip().lower()
                if low in _EXEC_STOP_WORDS:
                    hit = "STOP"
                    break
                if low in _EXEC_PAUSE_WORDS:
                    hit = "PAUSE"
                    break
                remaining.append(cmd)
            for cmd in reversed(remaining):
                self._browser_queue.appendleft(cmd)
            if hit:
                return hit

        try:
            ready, _, _ = select.select([sys.stdin], [], [], 0.0)
        except (OSError, ValueError):
            return None
        if not ready:
            return None

        line = sys.stdin.readline()
        if not line:
            return None
        low = line.strip().lower()
        if low in _EXEC_STOP_WORDS:
            return "STOP"
        if low in _EXEC_PAUSE_WORDS:
            return "PAUSE"
        if low:
            print(
                "\n  I'm in the middle of something - say 'stop' to halt.",
                flush=True,
            )
        return None

    def _handle_execution_interrupt(self, kind: str) -> None:
        """Abort or pause the running plan and report completed progress."""
        moved = self._bin_count + self._tray_count
        in_flight_target = self._get_current_target_label()

        self._orch.cancel()

        for _ in range(3):
            self._orch.tick()
            self._monitor_orchestrator_update()

        if moved == 0:
            if in_flight_target:
                msg = (
                    f"Stopped. I was reaching for the {in_flight_target}, "
                    "but nothing's been placed in the bin yet."
                )
            else:
                msg = (
                    "Stopped. I hadn't started moving anything yet - "
                    "nothing was placed."
                )
        else:
            placed = f"{moved} item" + ("" if moved == 1 else "s")
            if in_flight_target:
                msg = (
                    f"Stopped. I'd already placed {placed} and was reaching "
                    f"for the {in_flight_target}; I won't continue with the rest."
                )
            else:
                msg = (
                    f"Stopped. I'd already placed {placed}; "
                    "I won't start the rest."
                )

        if kind == "PAUSE":
            msg += " (I can't pause-and-resume yet, so I halted instead.)"

        print(f"\n  {msg}", flush=True)
        self._monitor_system_response(msg)
        self._last_reported_complete = True

    def _wait_for_execution_complete(
        self,
        timeout_s: float = 60.0,
    ) -> None:
        """
        Tick orchestrator until COMPLETE, ERROR, interrupt, or timeout.
        Polls terminal and browser input between ticks so "stop" can halt
        execution before the full plan finishes.
        """
        deadline = time.monotonic() + timeout_s

        while time.monotonic() < deadline:
            interrupt = self._poll_input_during_execution()
            if interrupt is not None:
                self._handle_execution_interrupt(interrupt)
                return

            self._orch.tick()
            self._monitor_orchestrator_update()
            status = self._orch.get_status()
            for node in status.get("task_graph", []):
                node_id = node.get("node_id", "")
                node_status = node.get("status", "")
                action_type = node.get("action_type", "")
                if node_status == "DONE" and node_id not in self._completed_node_ids:
                    self._completed_node_ids.add(node_id)
                    node_params = dict(node.get("parameters", {}))
                    if action_type == "move" and "object_id" not in node_params:
                        object_id = self._infer_moved_object_id(
                            node,
                            status.get("task_graph", []),
                        )
                        if object_id is not None:
                            node_params["object_id"] = object_id
                    if action_type == "move":
                        if node_params.get("target") == "tray":
                            self._tray_count += 1
                        else:
                            self._bin_count += 1
                            self._session_bin_count += 1
                        moved_object_id = node_params.get("object_id")
                        if moved_object_id is not None:
                            self._moved_object_ids.add(moved_object_id)
                            self._mark_planner_object_moved(moved_object_id)
                    if self._bridge_monitor is not None:
                        self._bridge_monitor.on_node_complete(
                            node_id=node_id,
                            action_type=action_type,
                            success=True,
                            parameters=node_params,
                        )
                        if action_type == "move":
                            completed_moves = sum(
                                1 for nid in self._completed_node_ids
                                if "move" in nid
                            )
                            remaining = max(
                                0,
                                self._orch.get_status().get("nodes_total", 0) // 4
                                - completed_moves,
                            )
                            if remaining > 0:
                                self._bridge_monitor.on_system_response(
                                    f"✓ Item {completed_moves} moved. "
                                    f"{remaining} still to go…"
                                )
                            else:
                                self._bridge_monitor.on_system_response(
                                    "✓ Last item moved."
                                )
            state = status.get("intentos_state")

            if state == "COMPLETE":
                duration_s = time.monotonic() - self._task_start_time
                table_remaining = max(
                    0,
                    len(self._preset_objects) - self._bin_count - self._tray_count,
                )
                scene = SceneDescription(
                    objects=self._preset_objects,
                    arm_position="home",
                    bin_count=self._bin_count,
                    tray_count=self._tray_count,
                    table_count=table_remaining,
                )
                msg = self._presenter.present_completion(
                    goal=status.get("goal", "that task"),
                    nodes_done=status.get("nodes_complete", 0),
                    duration_s=duration_s,
                    final_scene=scene,
                )
                print(f"\n  {msg}", flush=True)
                self._monitor_execution_complete(self._session_bin_count)
                self._monitor_system_response(msg)
                self._last_reported_complete = True
                return

            elif state == "ERROR":
                print(
                    "\n  Something went wrong. Say 'explain' for details.",
                    flush=True,
                )
                self._last_reported_error = True
                return

            elif state == "AWAITING_CONFIRM":
                print(
                    "\n  Paused for confirmation.",
                    flush=True,
                )
                return

            time.sleep(1.0 / self._tick_rate_hz)

        print(
            "\n  Still working... say 'explain' to check status.",
            flush=True,
        )

    @staticmethod
    def _infer_moved_object_id(
        move_node: dict, graph: list[dict]
    ) -> Optional[int]:
        """
        Find object_id for a move node by looking at the
        corresponding reach node (same numeric suffix).

        move_0 -> reach_0
        move_1 -> reach_1
        move_N -> reach_N
        """
        move_id = move_node.get("node_id", "")

        suffix = None
        if "_" in move_id:
            parts = move_id.rsplit("_", 1)
            if parts[1].isdigit():
                suffix = parts[1]

        if suffix is not None:
            reach_id = f"reach_{suffix}"
            for node in graph:
                if node.get("node_id") == reach_id:
                    obj_id = node.get("parameters", {}).get("object_id")
                    if obj_id is not None:
                        return int(obj_id)

        for node in graph:
            if node.get("action_type") == "reach":
                obj_id = node.get("parameters", {}).get("object_id")
                if obj_id is not None:
                    return int(obj_id)

        return None

    def _wait_for_phase2_idle(self, timeout_s: float = 10.0) -> bool:
        """
        Tick until Phase 2 returns to a safe state for a new goal.
        DONE/COMPLETE means Phase 2 finished its last execution cleanly.
        EXECUTING is tolerated here after IntentOS has reached a terminal state.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            self._orch.tick()
            self._monitor_orchestrator_update()
            kernel_state = self._orch.get_status().get("kernel_state", "")
            if kernel_state.upper() in (
                "IDLE",
                "SELECTING",
                "DONE",
                "COMPLETE",
                "EXECUTING",
            ):
                return True
            time.sleep(0.2)
        return False

    def _tick_until_state(self, target_state: str, timeout_s: float = 10.0) -> None:
        """Tick until orchestrator reaches target state or times out."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            self._orch.tick()
            self._monitor_orchestrator_update()
            status = self._orch.get_status()
            if status.get("intentos_state") == target_state:
                return
            time.sleep(1.0 / self._tick_rate_hz)

    def _signal_confirm(self):
        result = self._bridge.confirm()
        if not result.success:
            print(f"\n{result.reason}")
        return result

    def _monitor_user_input(self, text: str) -> None:
        if self._bridge_monitor is not None:
            self._bridge_monitor.on_user_input(text)

    def _monitor_system_response(self, text: str) -> None:
        if self._bridge_monitor is not None:
            self._bridge_monitor.on_system_response(text)

    def _monitor_orchestrator_update(self) -> None:
        if self._bridge_monitor is not None:
            self._bridge_monitor.on_orchestrator_update(self._orch.get_status())

    def _monitor_goal_submitted(self, goal: str) -> None:
        if self._bridge_monitor is not None:
            self._bridge_monitor.on_goal_submitted(goal)

    def _monitor_execution_start(self) -> None:
        if self._bridge_monitor is not None:
            self._bridge_monitor.on_execution_start(
                object_label=self._get_current_target_label()
            )

    def _get_current_target_label(self) -> Optional[str]:
        status = self._orch.get_status()
        for node in status.get("task_graph", []):
            if node.get("action_type") != "reach":
                continue
            target = node.get("parameters", {}).get("target", "")
            if not target.startswith("object_"):
                continue
            try:
                body_id = int(target.split("_", 1)[1])
            except (IndexError, ValueError):
                continue
            for label, mapped_body_id in self._label_map.items():
                if mapped_body_id == body_id:
                    return label.replace("_", " ")
        return None

    def _monitor_execution_complete(self, bin_count: int) -> None:
        if self._bridge_monitor is not None:
            self._bridge_monitor.on_execution_complete(bin_count)

    def _get_scene(self) -> SceneDescription:
        """Query the v1 preset scene description."""
        if self._preset_objects:
            table_items = [
                o
                for o in self._preset_objects
                if not o.get("in_bin", False) and not o.get("in_tray", False)
            ]
            actual_table = max(
                0,
                len(table_items) - self._bin_count - self._tray_count,
            )
            return SceneDescription(
                objects=self._preset_objects,
                arm_position="home",
                bin_count=self._bin_count,
                tray_count=self._tray_count,
                table_count=actual_table,
            )
        return self._empty_scene()

    @staticmethod
    def _empty_scene() -> SceneDescription:
        return SceneDescription(
            objects=[],
            arm_position="home",
            bin_count=0,
            tray_count=0,
            table_count=0,
        )

    @staticmethod
    def _build_scene_summary(scene: SceneDescription) -> str:
        """Build a text scene summary for the planner."""
        if scene.table_count == 0:
            return "Table is clear."
        return (
            f"{scene.table_count} objects on table. "
            f"{scene.bin_count} in bin. {scene.tray_count} in tray."
        )

    def _present_current_proposal(
        self,
        goal: str,
        scene: SceneDescription,
        status: dict,
    ) -> str:
        """Build the human-readable proposal from current orchestrator status."""
        nodes = status.get("task_graph", [])
        uncertainty_max = status.get("uncertainty_max", 0.3)
        plan_source = status.get("plan_source", "heuristic")
        duration_s = status.get("nodes_total", 4) * 2.0

        return self._presenter.present_proposal(
            goal=goal,
            scene=scene,
            plan_nodes=nodes,
            uncertainty_max=uncertainty_max,
            plan_source=plan_source,
            estimated_duration_s=duration_s,
        )

    def _print_welcome(self) -> None:
        print("\n" + "=" * 60)
        print("  Smart Workspace v1")
        print("=" * 60)
        print("  Type a goal to get started.")
        print('  Examples: "clean the table", "move the red block to the bin"')
        print('  Commands: yes · no · pause · stop · retry · explain · show debug')
        print("=" * 60)
