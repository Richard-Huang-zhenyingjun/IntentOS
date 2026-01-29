"""
Arm intent overlay - professional 7-panel layout.
Week 9: Production-grade visualization with structured grid.
"""

from typing import Dict, Any, List, Optional
import pybullet as p
from intent_core.arm_ui_snapshot import ArmUISnapshot
from .overlay_layout import OverlayLayout
from .text_panel import TextPanel


class ArmIntentOverlay:
    """
    7-panel overlay for arm control system.
    
    Layout:
    ┌─────────────────┬─────────────────┐
    │  1. System      │  2. Target      │
    ├─────────────────┼─────────────────┤
    │  3. Proposal    │  4. EEG         │
    ├─────────────────┼─────────────────┤
    │  5. Execution   │  6. Recovery    │
    ├─────────────────┴─────────────────┤
    │  7. Trust Metrics                 │
    └───────────────────────────────────┘
    
    Week 9: Professional grid layout, consistent formatting.
    """
    
    def __init__(self, table_center: tuple = (0.4, 0, 0.6), use_borders: bool = False, minimal_mode: bool = True):
        """
        Initialize overlay.
        
        Args:
            table_center: World position of table (anchor point)
            use_borders: If True, draw ASCII borders around panels
            minimal_mode: If True, use single minimal text block (performance mode)
        """
        self.layout = OverlayLayout(table_center)
        self.use_borders = use_borders
        
        # FIX 3: Minimal mode flag
        self._minimal_mode = minimal_mode
        
        # Debug item IDs (keyed by panel name)
        self.panel_ids: Dict[str, int] = {}
        
        # Pause banner ID (separate from panels)
        self.pause_banner_id: Optional[int] = None
        
        # Fault banner ID
        self.fault_banner_id: Optional[int] = None
        
        # PATCH 1: Visual heartbeat - frame counter
        self.frame_count: int = 0
        
        # Diagnostic banner ID (top-left corner)
        self.diagnostic_banner_id: Optional[int] = None
        
        # STEP 1: Minimal truth panel (updates every 6-10 frames)
        self.truth_panel_id: Optional[int] = None
        self.truth_panel_update_counter: int = 0
        self.TRUTH_PANEL_UPDATE_INTERVAL = 6  # Update every 6 frames (~5 Hz at 30fps)
        
        # FIX 3: Minimal mode text block
        self._minimal_text_id: Optional[int] = None
        self._update_counter: int = 0
    
    def render(self, p_inst=None, snapshot: ArmUISnapshot = None) -> None:
        """
        Render overlay from snapshot.
        
        Args:
            p_inst: PyBullet module or client ID (optional, uses global p if None or int)
            snapshot: Complete UI state snapshot (required if p_inst is None)
        """
        # Support both calling conventions:
        # 1. render(snapshot) - uses global p module
        # 2. render(p_inst, snapshot) - uses provided p_inst
        if snapshot is None and p_inst is not None:
            # Called as render(snapshot) where p_inst is actually snapshot
            snapshot = p_inst
            p_inst = p
        elif p_inst is None or isinstance(p_inst, int):
            # p_inst is None or a client ID (int) - use global p module
            p_inst = p
        
        # FIX 3: Minimal mode - single text block, 10Hz update
        if self._minimal_mode:
            self._render_minimal_overlay(p_inst, snapshot)
            return
        
        # PATCH 1: Increment frame counter (visual heartbeat)
        self.frame_count += 1
        
        # PATCH 2: Render diagnostic banner (top-left, very prominent)
        self._render_diagnostic_banner(p_inst, snapshot)
        
        # STEP 1: Render minimal truth panel (low frequency update)
        self._render_truth_panel(p_inst, snapshot)
        
        # Render each panel
        self._render_system_panel(p_inst, snapshot)
        self._render_target_panel(p_inst, snapshot)
        self._render_proposal_panel(p_inst, snapshot)
        self._render_eeg_panel(p_inst, snapshot)
        self._render_execution_panel(p_inst, snapshot)
        self._render_recovery_panel(p_inst, snapshot)
        self._render_trust_panel(p_inst, snapshot)
        
        # Overlays (if active)
        if snapshot.paused:
            self._render_pause_banner(p_inst, snapshot)
        else:
            self._clear_pause_banner(p_inst)
        
        if snapshot.active_faults:
            self._render_fault_banner(p_inst, snapshot)
        else:
            self._clear_fault_banner(p_inst)
    
    def _render_diagnostic_banner(self, p_inst, snapshot: ArmUISnapshot) -> None:
        """
        PATCH 1 & 2: Diagnostic banner - visual heartbeat + prominent state display.
        
        Position: Top-left corner of view (world coords: -0.8, 0, 1.2)
        Shows: Frame count, FPS, current state (VERY prominent if AWAITING_CONFIRM)
        """
        # Build diagnostic text
        lines = []
        
        # PATCH 1: Visual heartbeat
        lines.append(f"FRAME: {self.frame_count} | FPS: {snapshot.fps:.1f}")
        lines.append("─" * 40)
        
        # PATCH 2: State visibility (VERY prominent)
        state_display = snapshot.state.upper().replace('_', ' ')
        
        # Special highlighting for AWAITING_CONFIRM
        if snapshot.state == "awaiting_confirm":
            lines.append("")
            lines.append("╔═══════════════════════════════════╗")
            lines.append(f"║  STATE: {state_display:<25} ║")
            lines.append("╚═══════════════════════════════════╝")
            lines.append("")
            lines.append(">>> PRESS C TO CONFIRM OR X TO CANCEL <<<")
            
            # Show active proposal prominently
            if snapshot.proposed_action:
                action_display = snapshot.proposed_action.replace('_', ' ').title()
                lines.append("")
                lines.append(f"PROPOSAL: {action_display}")
                if snapshot.proposal_reason:
                    reason_short = TextPanel.truncate(snapshot.proposal_reason, 35)
                    lines.append(f"Reason: {reason_short}")
        
        # PATCH 6: Execution visibility (show what controller is doing)
        elif snapshot.state == "executing":
            lines.append("")
            lines.append("╔═══════════════════════════════════╗")
            lines.append(f"║  STATE: {state_display:<25} ║")
            lines.append("╚═══════════════════════════════════╝")
            lines.append("")
            
            if snapshot.executing_action:
                action_display = snapshot.executing_action.replace('_', ' ').title()
                progress_pct = int(snapshot.execution_progress * 100)
                steps = snapshot.execution_steps
                
                # Format: "EXECUTING: {action} | {progress}% | Step {current}"
                exec_line = f"EXECUTING: {action_display} | {progress_pct}% | Step {steps}"
                lines.append(exec_line)
                
                # Show phase if available
                if snapshot.execution_phase:
                    phase_display = snapshot.execution_phase.replace('_', ' ').title()
                    lines.append(f"Phase: {phase_display}")
        else:
            lines.append(f"STATE: {state_display}")
        
        # Cooldown warning
        if snapshot.cooldown_frames > 0:
            lines.append(f"⚠️  Cooldown: {snapshot.cooldown_frames} frames")
        
        # PATCH 4: Joint state display (proves robot is moving)
        if snapshot.joint_angles and len(snapshot.joint_angles) >= 3:
            j0, j1, j2 = snapshot.joint_angles[0], snapshot.joint_angles[1], snapshot.joint_angles[2]
            lines.append("")
            lines.append(f"J0: {j0:.2f} | J1: {j1:.2f} | J2: {j2:.2f}")
        
        # PATCH 8: Mouse mode instructions (if using mouse)
        if snapshot.cursor_source == "mouse" and not snapshot.selection_locked:
            lines.append("")
            lines.append("─" * 40)
            lines.append("MOUSE MODE: Click & hold on cube for 0.6s to lock")
            if snapshot.hover_object_id and snapshot.hover_progress > 0:
                hover_pct = int(snapshot.hover_progress * 100)
                lines.append(f"HOVER: {hover_pct}%")
        
        text = "\n".join(lines)
        
        # Position: top-left corner (world coordinates)
        # Adjust based on table center - position relative to camera view
        position = (-0.8, 0.0, 1.2)
        
        # Color: bright yellow for AWAITING_CONFIRM, cyan otherwise
        if snapshot.state == "awaiting_confirm":
            color = [1.0, 1.0, 0.0]  # Bright yellow
            text_size = 1.3  # Larger text
        else:
            color = [0.0, 1.0, 1.0]  # Cyan
            text_size = 1.0
        
        # Render (with replacement for efficiency)
        if self.diagnostic_banner_id is not None:
            self.diagnostic_banner_id = p_inst.addUserDebugText(
                text,
                position,
                textColorRGB=color,
                textSize=text_size,
                replaceItemUniqueId=self.diagnostic_banner_id
            )
        else:
            self.diagnostic_banner_id = p_inst.addUserDebugText(
                text,
                position,
                textColorRGB=color,
                textSize=text_size
            )
    
    def _render_system_panel(self, p_inst, snapshot: ArmUISnapshot) -> None:
        """Panel 1: System state + narrative."""
        panel = TextPanel("SYSTEM", self.use_borders)
        
        # State (color-coded)
        state_display = snapshot.state.upper().replace('_', ' ')
        panel.add_kv("State", state_display)
        
        # Last event
        if snapshot.last_event:
            event_short = TextPanel.truncate(snapshot.last_event, 30)
            panel.add_kv("Event", event_short)
        
        # Cooldown (if active)
        if snapshot.cooldown_frames > 0:
            panel.add_kv("Cooldown", f"{snapshot.cooldown_frames} frames")
        
        # FPS
        panel.add_metric("FPS", snapshot.fps, decimals=1)
        
        # Render
        self._render_panel(p_inst, "system", panel.build(), snapshot)
    
    def _render_truth_panel(self, p_inst, snapshot: ArmUISnapshot) -> None:
        """
        STEP 1: Minimal truth panel - shows critical state at low frequency.
        
        Updates every 6-10 frames to avoid performance impact.
        Shows: STATE, LOCKED_TARGET, PROPOSAL
        """
        # Only update every N frames
        self.truth_panel_update_counter += 1
        if self.truth_panel_update_counter < self.TRUTH_PANEL_UPDATE_INTERVAL:
            return  # Skip this frame
        self.truth_panel_update_counter = 0
        
        # Build truth panel text
        state_display = snapshot.state.upper().replace('_', ' ')
        locked_target = str(snapshot.locked_object_id) if snapshot.locked_object_id is not None else "None"
        proposal = snapshot.proposed_action.replace('_', ' ').upper() if snapshot.proposed_action else "None"
        
        lines = [
            f"STATE: {state_display}",
            f"LOCKED_TARGET: {locked_target}",
            f"PROPOSAL: {proposal}"
        ]
        text = "\n".join(lines)
        
        # Position: top-left, below diagnostic banner
        position = (-0.8, 0.0, 0.9)
        
        # Render with ID reuse
        if self.truth_panel_id is not None:
            self.truth_panel_id = p_inst.addUserDebugText(
                text,
                position,
                textColorRGB=[1.0, 1.0, 1.0],  # White
                textSize=1.0,
                replaceItemUniqueId=self.truth_panel_id
            )
        else:
            self.truth_panel_id = p_inst.addUserDebugText(
                text,
                position,
                textColorRGB=[1.0, 1.0, 1.0],  # White
                textSize=1.0
            )
    
    def _render_target_panel(self, p_inst, snapshot: ArmUISnapshot) -> None:
        """Panel 2: Target selection state."""
        panel = TextPanel("TARGET", self.use_borders)
        
        # PATCH 8: Mouse mode instructions
        if snapshot.cursor_source == "mouse":
            panel.add_line("MOUSE MODE")
            if not snapshot.selection_locked:
                panel.add_line("Click & hold on cube")
                panel.add_line("for 0.6s to lock")
        
        # Hover/Lock
        if snapshot.selection_locked and snapshot.locked_object_id:
            panel.add_success(f"Locked: Object {snapshot.locked_object_id}")
        elif snapshot.hover_object_id:
            pct = int(snapshot.hover_progress * 100)
            panel.add_kv("Hover", f"Object {snapshot.hover_object_id} ({pct}%)")
            if snapshot.hover_progress > 0:
                panel.add_progress_bar("Dwell", snapshot.hover_progress, width=12)
            # PATCH 8: Show hover progress prominently in mouse mode
            if snapshot.cursor_source == "mouse":
                panel.add_line(f"HOVER: {pct}%")
        else:
            panel.add_line("No target")
        
        # Cursor source
        panel.add_kv("Input", snapshot.cursor_source)
        
        # Render
        self._render_panel(p_inst, "target", panel.build(), snapshot)
    
    def _render_proposal_panel(self, p_inst, snapshot: ArmUISnapshot) -> None:
        """Panel 3: Action proposal."""
        panel = TextPanel("PROPOSAL", self.use_borders)
        
        if snapshot.proposed_action:
            # Proposed action
            action_display = snapshot.proposed_action.replace('_', ' ').title()
            panel.add_kv("Action", action_display)
            
            # Reason
            if snapshot.proposal_reason:
                reason = TextPanel.truncate(snapshot.proposal_reason, 35)
                panel.add_kv("Reason", reason)
            
            # Available count
            panel.add_kv("Available", f"{len(snapshot.available_actions)} actions")
        else:
            panel.add_line("No proposal")
        
        # Render
        self._render_panel(p_inst, "proposal", panel.build(), snapshot)
    
    def _render_eeg_panel(self, p_inst, snapshot: ArmUISnapshot) -> None:
        """Panel 4: EEG/decision status."""
        panel = TextPanel("EEG", self.use_borders)
        
        # Source
        panel.add_kv("Source", snapshot.decision_source)
        
        # Signal
        panel.add_kv("Signal", snapshot.eeg_signal)
        
        # Metrics (if available)
        if snapshot.eeg_attention is not None:
            panel.add_metric("Attention", snapshot.eeg_attention, decimals=0)
        if snapshot.eeg_meditation is not None:
            panel.add_metric("Meditation", snapshot.eeg_meditation, decimals=0)
        
        # Stability
        panel.add_status("Stable", snapshot.eeg_stable)
        
        # Blocked reason
        if snapshot.eeg_blocked and snapshot.eeg_blocked_reason:
            reason = TextPanel.truncate(snapshot.eeg_blocked_reason, 30)
            panel.add_warning(reason)
        
        # Cooldown
        if snapshot.cooldown_remaining_s > 0:
            panel.add_kv("Cooldown", f"{snapshot.cooldown_remaining_s:.1f}s")
        
        # Render
        color = [0.7, 1.0, 0.7] if snapshot.eeg_stable else [1.0, 0.7, 0.0]
        self._render_panel(p_inst, "eeg", panel.build(), snapshot, color=color)
    
    def _render_execution_panel(self, p_inst, snapshot: ArmUISnapshot) -> None:
        """Panel 5: Execution progress."""
        panel = TextPanel("EXECUTION", self.use_borders)
        
        if snapshot.executing_action:
            # Action name
            action_display = snapshot.executing_action.replace('_', ' ').title()
            panel.add_kv("Action", action_display)
            
            # Progress bar
            panel.add_progress_bar("Progress", snapshot.execution_progress, width=15)
            
            # Steps
            panel.add_kv("Steps", f"{snapshot.execution_steps}")
            
            # Phase (if available)
            if snapshot.execution_phase:
                panel.add_kv("Phase", snapshot.execution_phase)
        else:
            panel.add_line("Idle")
        
        # Gripper state
        panel.add_kv("Gripper", snapshot.gripper_state.upper())
        
        # Holding object
        if snapshot.holding_object_id:
            panel.add_success(f"Holding: Object {snapshot.holding_object_id}")
        
        # Render
        self._render_panel(p_inst, "execution", panel.build(), snapshot)
    
    def _render_recovery_panel(self, p_inst, snapshot: ArmUISnapshot) -> None:
        """Panel 6: Recovery state."""
        panel = TextPanel("RECOVERY", self.use_borders)
        
        if snapshot.paused:
            panel.add_warning("SYSTEM PAUSED")
            
            if snapshot.pause_trigger:
                trigger = snapshot.pause_trigger.replace('_', ' ').title()
                panel.add_kv("Trigger", trigger)
            
            if snapshot.pause_duration > 0:
                duration_str = TextPanel.format_duration(snapshot.pause_duration)
                panel.add_kv("Duration", duration_str)
            
            # Recovery steps (truncate to first 2)
            if snapshot.recovery_steps:
                panel.add_separator()
                panel.add_line("Steps:")
                for step in snapshot.recovery_steps[:2]:
                    step_short = TextPanel.truncate(step, 28)
                    panel.add_list([step_short], prefix="→")
        else:
            panel.add_status("Paused", False)
            if snapshot.pauses_triggered > 0:
                panel.add_kv("Total pauses", str(snapshot.pauses_triggered))
        
        # Render
        color = [1.0, 0.6, 0.0] if snapshot.paused else [0.7, 0.7, 0.7]
        self._render_panel(p_inst, "recovery", panel.build(), snapshot, color=color)
    
    def _render_trust_panel(self, p_inst, snapshot: ArmUISnapshot) -> None:
        """Panel 7: Trust metrics footer."""
        panel = TextPanel("TRUST", self.use_borders)
        
        # Critical metric
        if snapshot.false_executions == 0:
            panel.add_success("False Executions: 0 ✓ PASS")
        else:
            panel.add_error(f"False Executions: {snapshot.false_executions} ✗ FAIL")
        
        # Compact stats line
        stats = (
            f"Started: {snapshot.executions_started} | "
            f"Completed: {snapshot.executions_completed} | "
            f"Blocked: {snapshot.executions_blocked_unstable} | "
            f"Pauses: {snapshot.pauses_triggered}"
        )
        panel.add_line(stats)
        
        # Render
        color = [0.5, 1.0, 0.5] if snapshot.false_executions == 0 else [1.0, 0.0, 0.0]
        self._render_panel(p_inst, "trust", panel.build(), snapshot, color=color, size=1.0)
    
    def _render_pause_banner(self, p_inst, snapshot: ArmUISnapshot) -> None:
        """Render large pause banner (center-top)."""
        lines = [
            "═══════════════════════════════════",
            "         ⚠️  SYSTEM PAUSED ⚠️        ",
            "═══════════════════════════════════",
            f"Trigger: {snapshot.pause_trigger or 'unknown'}",
            f"Reason: {snapshot.pause_explanation}",
            "═══════════════════════════════════",
        ]
        
        text = "\n".join(lines)
        
        # Position: center-top of scene
        position = (0.4, 0.0, 1.0)
        
        if self.pause_banner_id is not None:
            # Update existing
            self.pause_banner_id = p_inst.addUserDebugText(
                text,
                position,
                textColorRGB=[1.0, 0.5, 0.0],
                textSize=1.4,
                replaceItemUniqueId=self.pause_banner_id
            )
        else:
            # Create new
            self.pause_banner_id = p_inst.addUserDebugText(
                text,
                position,
                textColorRGB=[1.0, 0.5, 0.0],
                textSize=1.4
            )
    
    def _render_fault_banner(self, p_inst, snapshot: ArmUISnapshot) -> None:
        """Render fault injection banner."""
        lines = [
            "⚡ FAULT INJECTION ACTIVE ⚡",
            "Active Faults:",
        ]
        
        for fault in snapshot.active_faults[:3]:  # Max 3
            lines.append(f"  • {fault}")
        
        text = "\n".join(lines)
        
        # Position: top-right
        position = (0.8, 0.0, 1.2)
        
        if self.fault_banner_id is not None:
            self.fault_banner_id = p_inst.addUserDebugText(
                text,
                position,
                textColorRGB=[1.0, 0.0, 1.0],
                textSize=1.2,
                replaceItemUniqueId=self.fault_banner_id
            )
        else:
            self.fault_banner_id = p_inst.addUserDebugText(
                text,
                position,
                textColorRGB=[1.0, 0.0, 1.0],
                textSize=1.2
            )
    
    def _render_panel(self, p_inst, panel_name: str, text: str, snapshot: ArmUISnapshot, 
                      color: List[float] = None, size: float = 0.85) -> None:
        """
        Render panel at grid position.
        
        Args:
            p_inst: PyBullet client
            panel_name: Panel identifier
            text: Formatted text
            snapshot: UI snapshot (for context)
            color: RGB color (default gray)
            size: Text size
        """
        if color is None:
            color = [0.8, 0.8, 0.8]
        
        # Get panel region
        region = self.layout.get_panel(panel_name)
        
        # Render (with replacement for efficiency)
        if panel_name in self.panel_ids:
            # Update existing
            self.panel_ids[panel_name] = p_inst.addUserDebugText(
                text,
                region.position,
                textColorRGB=color,
                textSize=size,
                replaceItemUniqueId=self.panel_ids[panel_name]
            )
        else:
            # Create new
            self.panel_ids[panel_name] = p_inst.addUserDebugText(
                text,
                region.position,
                textColorRGB=color,
                textSize=size
            )
    
    def _clear_pause_banner(self, p_inst) -> None:
        """Clear pause banner."""
        if self.pause_banner_id is not None:
            try:
                p_inst.removeUserDebugItem(self.pause_banner_id)
            except:
                pass
            self.pause_banner_id = None
    
    def _clear_fault_banner(self, p_inst) -> None:
        """Clear fault banner."""
        if self.fault_banner_id is not None:
            try:
                p_inst.removeUserDebugItem(self.fault_banner_id)
            except:
                pass
            self.fault_banner_id = None
    
    def clear(self, p_inst) -> None:
        """Clear all overlay items (on reset)."""
        # Clear panels
        for item_id in self.panel_ids.values():
            try:
                p_inst.removeUserDebugItem(item_id)
            except:
                pass
        self.panel_ids.clear()
        
        # Clear banners
        self._clear_pause_banner(p_inst)
        self._clear_fault_banner(p_inst)
        
        # Clear diagnostic banner
        if self.diagnostic_banner_id is not None:
            try:
                p_inst.removeUserDebugItem(self.diagnostic_banner_id)
            except:
                pass
            self.diagnostic_banner_id = None
        
        # Clear truth panel
        if self.truth_panel_id is not None:
            try:
                p_inst.removeUserDebugItem(self.truth_panel_id)
            except:
                pass
            self.truth_panel_id = None
        
        # Reset frame counter (optional - may want to keep for session tracking)
        # self.frame_count = 0
        
        # Clear minimal text
        if self._minimal_text_id is not None:
            try:
                p_inst.removeUserDebugItem(self._minimal_text_id)
            except:
                pass
            self._minimal_text_id = None
    
    def _render_minimal_overlay(self, p_inst, snapshot: ArmUISnapshot) -> None:
        """
        FIX 3: Minimal mode - single text block, updated at 10Hz.
        
        Reduces API calls from 10-11 per frame to 1 call every 3 frames.
        """
        self._update_counter += 1
        
        # Update every 3 frames (assuming 30 FPS = 10Hz)
        if self._update_counter % 3 != 0:
            return
        
        # Build single text block
        text_lines = []
        
        # Core state
        state_display = snapshot.state.upper().replace('_', ' ')
        text_lines.append(f"STATE: {state_display}")
        
        # Target
        target_display = str(snapshot.locked_object_id) if snapshot.locked_object_id is not None else "None"
        text_lines.append(f"TARGET: {target_display}")
        
        # Proposal
        if snapshot.proposed_action:
            proposal_display = snapshot.proposed_action.replace('_', ' ').upper()
            text_lines.append(f"PROPOSAL: {proposal_display}")
        else:
            text_lines.append("PROPOSAL: None")
        
        # FPS and frame count
        text_lines.append(f"FPS: {snapshot.fps:.1f}")
        text_lines.append(f"FRAME: {snapshot.frame_count}")
        
        # Add execution info if executing
        if snapshot.executing_action:
            action_display = snapshot.executing_action.replace('_', ' ').upper()
            progress_pct = int(snapshot.execution_progress * 100)
            text_lines.append(f"EXEC: {action_display} ({progress_pct}%)")
        
        # Add pause warning if paused
        if snapshot.paused:
            trigger_display = snapshot.pause_trigger.replace('_', ' ').upper() if snapshot.pause_trigger else "UNKNOWN"
            text_lines.append(f"⚠️ PAUSED: {trigger_display}")
        
        text = "\n".join(text_lines)
        
        # Position: top-left corner (world coordinates)
        position = (-0.8, 0.0, 1.2)
        
        # Render single text block
        if self._minimal_text_id is None:
            self._minimal_text_id = p_inst.addUserDebugText(
                text,
                position,
                textColorRGB=[1.0, 1.0, 1.0],  # White
                textSize=1.5,
                lifeTime=0
            )
        else:
            self._minimal_text_id = p_inst.addUserDebugText(
                text,
                position,
                textColorRGB=[1.0, 1.0, 1.0],  # White
                textSize=1.5,
                lifeTime=0,
                replaceItemUniqueId=self._minimal_text_id
            )
