"""
Intent Visualizer - Week 9 Complete Visual Embodiment

Clean 7-section layout for maximum transparency and demo readiness.
Makes every decision visible and explainable.
"""

import tkinter as tk
from typing import Dict, Optional, List
from intent_core.ui_snapshot import UISnapshot


class VisualConfig:
    """Visual styling configuration"""
    panel_width = 500
    font_mono = ("Consolas", 9)
    font_header = ("Arial", 11, "bold")
    font_normal = ("Arial", 9)
    font_small = ("Arial", 8)
    
    # Colors (VS Code Dark+ theme)
    color_bg = "#1e1e1e"
    color_text = "#d4d4d4"
    color_header = "#569cd6"
    color_success = "#4ec9b0"
    color_warning = "#ce9178"
    color_error = "#f48771"
    color_muted = "#808080"
    color_border = "#3e3e3e"
    color_cyan = "#4ec9b0"


class IntentVisualizerWeek9:
    """
    Complete visual embodiment panel (FINALIZED Week 9)
    
    Shows everything needed to understand system decisions.
    Fixed 7-section layout (always in same order).
    
    Design principles:
    - Transparency first
    - Refusals are features
    - ONE decision at a time
    - Predictions labeled as read-only
    - PAUSED is success state
    """
    
    def __init__(self, parent: tk.Widget, config: Optional[Dict] = None):
        """
        Initialize visualizer
        
        Args:
            parent: Tkinter parent widget
            config: Configuration dict
        """
        self.visual_config = VisualConfig()
        self.config = config or {}
        
        # Display settings
        self.max_narrative_events = self.config.get('max_narrative_events', 5)
        self.show_debug_info = self.config.get('show_debug_info', False)
        
        # Create main panel
        self.panel = tk.Frame(
            parent,
            width=self.visual_config.panel_width,
            bg=self.visual_config.color_bg,
            relief=tk.SUNKEN,
            borderwidth=2
        )
        self.panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=False)
        self.panel.pack_propagate(False)
        
        # Create scrollable canvas
        self.canvas = tk.Canvas(
            self.panel,
            bg=self.visual_config.color_bg,
            highlightthickness=0,
            width=self.visual_config.panel_width
        )
        self.scrollbar = tk.Scrollbar(
            self.panel,
            orient="vertical",
            command=self.canvas.yview
        )
        
        self.scrollable_frame = tk.Frame(
            self.canvas,
            bg=self.visual_config.color_bg
        )
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        self.snapshot: Optional[UISnapshot] = None
    
    def render(self, snapshot: UISnapshot):
        """
        Render complete visualization (FINALIZED Week 9)
        
        7-section fixed layout:
        1. System Status
        2. Intent Timeline (narrative events)
        3. Authority Gates (checklist)
        4. Multi-Object Scene
        5. Affordances (read-only predictions)
        6. Confirmation State
        7. Recovery & Undo
        
        Args:
            snapshot: Complete UI snapshot
        """
        self.snapshot = snapshot
        
        # Clear previous content
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        # Render all 7 sections
        self._draw_system_status()
        self._render_separator()
        
        self._draw_intent_timeline()
        self._render_separator()
        
        self._draw_authority_gates()
        self._render_separator()
        
        self._draw_multi_object_scene()
        self._render_separator()
        
        self._draw_affordances()
        self._render_separator()
        
        self._draw_confirmation_state()
        self._render_separator()
        
        self._draw_recovery_and_undo()
        
        # Optional debug info
        if self.show_debug_info:
            self._render_separator()
            self._draw_debug_info()
    
    def _create_section(self, title: str) -> tk.Frame:
        """Create section with header"""
        section = tk.Frame(
            self.scrollable_frame,
            bg=self.visual_config.color_bg,
            pady=8,
            padx=12
        )
        section.pack(fill=tk.X)
        
        header = tk.Label(
            section,
            text=title.upper(),
            font=self.visual_config.font_header,
            fg=self.visual_config.color_header,
            bg=self.visual_config.color_bg,
            anchor="w"
        )
        header.pack(fill=tk.X, pady=(0, 5))
        
        return section
    
    def _add_label(self, parent: tk.Frame, text: str, color: str = None, font=None):
        """Add text label to section"""
        label = tk.Label(
            parent,
            text=text,
            font=font or self.visual_config.font_normal,
            fg=color or self.visual_config.color_text,
            bg=self.visual_config.color_bg,
            anchor="w",
            justify=tk.LEFT,
            wraplength=self.visual_config.panel_width - 40
        )
        label.pack(fill=tk.X, pady=1)
        return label
    
    def _render_separator(self):
        """Render visual separator"""
        sep = tk.Frame(
            self.scrollable_frame,
            height=1,
            bg=self.visual_config.color_border
        )
        sep.pack(fill=tk.X, pady=3)
    
    # === SECTION 1: SYSTEM STATUS ===
    
    def _draw_system_status(self):
        """
        Section 1: System Status
        
        Shows:
        - Current state with color coding
        - State reason
        - Current narrative (one-sentence status)
        """
        section = self._create_section("System Status")
        
        state = self.snapshot.system_state
        reason = self.snapshot.system_state_reason
        narrative = self.snapshot.current_narrative
        
        # State icons and colors
        state_config = {
            'idle': {'icon': '⭘', 'color': self.visual_config.color_muted},
            'scoped': {'icon': '🎯', 'color': self.visual_config.color_success},
            'confirming': {'icon': '✓', 'color': self.visual_config.color_warning},
            'executing': {'icon': '▶️', 'color': self.visual_config.color_success},
            'paused': {'icon': '⏸', 'color': self.visual_config.color_error},
            'recovering': {'icon': '🔄', 'color': self.visual_config.color_warning},
            'undo_confirming': {'icon': '↩️', 'color': self.visual_config.color_warning}
        }
        
        config = state_config.get(state, {'icon': '?', 'color': self.visual_config.color_muted})
        
        # Large state display
        state_label = tk.Label(
            section,
            text=f"{config['icon']} {state.upper()}",
            font=("Arial", 20, "bold"),
            fg=config['color'],
            bg=self.visual_config.color_bg
        )
        state_label.pack(pady=8)
        
        # State reason
        if reason:
            self._add_label(section, f"Why: {reason}", color=self.visual_config.color_muted)
        
        # Current narrative
        if narrative:
            self._add_label(section, "", color=self.visual_config.color_text)  # Spacer
            self._add_label(section, f"Status: {narrative}", color=self.visual_config.color_text)
    
    # === SECTION 2: INTENT TIMELINE ===
    
    def _draw_intent_timeline(self):
        """
        Section 2: Intent Timeline
        
        Shows last N narrative events with:
        - Timestamp
        - Icon
        - Human-readable description
        """
        section = self._create_section("Recent Events")
        
        events = self.snapshot.recent_events[-self.max_narrative_events:]
        
        if not events:
            self._add_label(section, "No recent events", color=self.visual_config.color_muted)
            return
        
        # Severity colors
        severity_colors = {
            'info': self.visual_config.color_muted,
            'success': self.visual_config.color_success,
            'warning': self.visual_config.color_warning,
            'error': self.visual_config.color_error
        }
        
        for event in events:
            timestamp = event.get('timestamp', 0.0)
            icon = event.get('icon', '•')
            narrative = event.get('narrative', 'Event')
            severity = event.get('severity', 'info')
            
            color = severity_colors.get(severity, self.visual_config.color_muted)
            
            # Format: t=12.3  🎯  Focused on lamp
            time_str = f"t={timestamp:.1f}".ljust(8)
            self._add_label(section, f"{time_str} {icon}  {narrative}", color=color)
    
    # === SECTION 3: AUTHORITY GATES ===
    
    def _draw_authority_gates(self):
        """
        Section 3: Authority Gates Checklist
        
        Shows why execution is or isn't allowed.
        Critical for transparency.
        """
        section = self._create_section("Authority Gates")
        
        gates = self.snapshot.authority_gates
        reasons = self.snapshot.authority_gate_reasons
        
        # Gate order (importance hierarchy)
        gate_order = [
            ('scope_present', 'Scope Present'),
            ('scope_stable', 'Scope Stable'),
            ('no_ambiguity', 'No Ambiguity'),
            ('affordances_available', 'Actions Available'),
            ('confirmation_valid', 'Confirmation Valid'),
            ('not_paused', 'System Active'),
            ('execution_allowed', 'Execution Allowed')
        ]
        
        for gate_key, gate_label in gate_order:
            passed = gates.get(gate_key, False)
            reason = reasons.get(gate_key, '')
            
            if passed:
                icon = "✓"
                color = self.visual_config.color_success
            else:
                icon = "✗"
                color = self.visual_config.color_error
            
            self._add_label(section, f"{icon} {gate_label}", color=color)
            
            if not passed and reason:
                self._add_label(section, f"    → {reason}", color=self.visual_config.color_muted)
        
        # Summary
        self._add_label(section, "")  # Spacer
        
        if self.snapshot.all_gates_passed:
            self._add_label(section, "✓ All gates passed - execution permitted", 
                          color=self.visual_config.color_success)
        else:
            blocking = self.snapshot.blocking_gates
            self._add_label(section, f"✗ Blocked by: {', '.join(blocking)}", 
                          color=self.visual_config.color_error)
    
    # === SECTION 4: MULTI-OBJECT SCENE ===
    
    def _draw_multi_object_scene(self):
        """Section 4: Multi-Object Scene Status"""
        section = self._create_section("Scene Status")
        
        num_tracked = self.snapshot.num_tracked_objects
        primary_id = self.snapshot.primary_object_id
        ambiguity = self.snapshot.ambiguity_detected
        oscillation = self.snapshot.oscillation_detected
        
        # Object count
        if num_tracked == 0:
            self._add_label(section, "No objects detected", color=self.visual_config.color_muted)
        elif num_tracked == 1:
            self._add_label(section, f"✓ 1 object tracked", color=self.visual_config.color_success)
        else:
            self._add_label(section, f"👁 {num_tracked} objects tracked", color=self.visual_config.color_warning)
        
        # Primary focus
        if primary_id:
            label = self.snapshot.scoped_object_label or 'unknown'
            self._add_label(section, f"Focus: {label}", color=self.visual_config.color_success)
        else:
            self._add_label(section, "Focus: None", color=self.visual_config.color_muted)
        
        # Warnings
        if ambiguity:
            self._add_label(section, "")  # Spacer
            self._add_label(section, "⚠️ AMBIGUITY", color=self.visual_config.color_warning)
            self._add_label(section, f"  {self.snapshot.ambiguity_reason}", 
                          color=self.visual_config.color_muted)
        
        if oscillation:
            self._add_label(section, "")  # Spacer
            self._add_label(section, "⚠️ OSCILLATION", color=self.visual_config.color_error)
            self._add_label(section, f"  {self.snapshot.oscillation_reason}", 
                          color=self.visual_config.color_muted)
    
    # === SECTION 5: AFFORDANCES (READ-ONLY) ===
    
    def _draw_affordances(self):
        """
        Section 5: Affordances (Read-Only Predictions)
        
        CRITICAL: Labeled as READ-ONLY
        Shows system understanding, not decisions
        """
        section = self._create_section("Affordances (READ-ONLY)")
        
        if self.snapshot.affordances_blocked:
            reason = self.snapshot.affordances_block_reason
            self._add_label(section, f"❌ Blocked: {reason}", color=self.visual_config.color_error)
            return
        
        if not self.snapshot.affordances_available:
            self._add_label(section, "No affordances available", color=self.visual_config.color_muted)
            return
        
        # Show state inference context
        if self.snapshot.state_estimate:
            state = self.snapshot.state_estimate.get('state', 'unknown')
            confidence = self.snapshot.state_confidence
            method = self.snapshot.state_method
            
            self._add_label(section, f"Object State: {state.upper()} (conf={confidence:.2f})", 
                          color=self.visual_config.color_cyan)
            self._add_label(section, f"Method: {method}", color=self.visual_config.color_muted)
            self._add_label(section, "")  # Spacer
        
        # Show options
        options = self.snapshot.affordance_options
        highlighted_idx = self.snapshot.highlighted_option_index
        
        self._add_label(section, f"Predicted Actions ({len(options)}):", 
                      color=self.visual_config.color_cyan)
        
        for i, option in enumerate(options):
            title = option.get('title', 'Unknown')
            confidence = option.get('confidence', 0.0)
            
            # Highlight selected option
            marker = "►" if i == highlighted_idx else " "
            
            self._add_label(section, f"{marker} {i+1}. {title} (conf={confidence:.2f})", 
                          color=self.visual_config.color_cyan)
        
        self._add_label(section, "")  # Spacer
        self._add_label(section, "⚠️ These are predictions, not decisions", 
                      color=self.visual_config.color_warning)
        self._add_label(section, "   Execution requires explicit confirmation", 
                      color=self.visual_config.color_muted)
    
    # === SECTION 6: CONFIRMATION STATE ===
    
    def _draw_confirmation_state(self):
        """Section 6: Confirmation State"""
        section = self._create_section("Confirmation")
        
        # Hand detection
        if self.snapshot.hand_detected:
            conf = self.snapshot.hand_confidence
            self._add_label(section, f"✓ Hand detected (conf={conf:.2f})", 
                          color=self.visual_config.color_success)
        else:
            self._add_label(section, "✗ Hand not detected", color=self.visual_config.color_error)
        
        # Pinch state
        if self.snapshot.pinch_detected:
            held = self.snapshot.pinch_stable_frames
            required = self.snapshot.pinch_required_frames
            percentage = (held / required) * 100 if required > 0 else 0
            
            self._add_label(section, f"👆 Pinch: {held}/{required} ({percentage:.0f}%)", 
                          color=self.visual_config.color_warning)
            
            # Progress bar
            progress_bar = self._create_progress_bar(held, required, width=20)
            self._add_label(section, f"   {progress_bar}", color=self.visual_config.color_warning)
        else:
            self._add_label(section, "  No pinch detected", color=self.visual_config.color_muted)
        
        # Confirmation state
        conf_state = self.snapshot.confirmation_state
        if conf_state == 'confirmed':
            self._add_label(section, "✓ CONFIRMED", color=self.visual_config.color_success)
        elif conf_state == 'confirming':
            self._add_label(section, "⏳ CONFIRMING...", color=self.visual_config.color_warning)
        else:
            self._add_label(section, "  Waiting for confirmation", color=self.visual_config.color_muted)
    
    # === SECTION 7: RECOVERY & UNDO ===
    
    def _draw_recovery_and_undo(self):
        """Section 7: Recovery & Undo"""
        section = self._create_section("Recovery & Undo")
        
        # Pause/Recovery
        if self.snapshot.paused:
            trigger = self.snapshot.pause_trigger or 'unknown'
            reason = self.snapshot.pause_reason
            
            self._add_label(section, "⏸ SYSTEM PAUSED", color=self.visual_config.color_error)
            self._add_label(section, f"  Trigger: {trigger}", color=self.visual_config.color_error)
            self._add_label(section, f"  Reason: {reason}", color=self.visual_config.color_muted)
            
            if self.snapshot.recovery_required:
                self._add_label(section, "")  # Spacer
                self._add_label(section, "Recovery Steps:", color=self.visual_config.color_warning)
                
                explanation = self.snapshot.recovery_explanation
                for line in explanation.split('\n'):
                    if line.strip():
                        self._add_label(section, f"  {line.strip()}", 
                                      color=self.visual_config.color_muted)
        else:
            self._add_label(section, "✓ System active", color=self.visual_config.color_success)
        
        self._add_label(section, "")  # Spacer
        
        # Undo
        if self.snapshot.undo_available:
            action = self.snapshot.undo_action_type or 'action'
            obj = self.snapshot.undo_object_label or 'object'
            time_left = self.snapshot.undo_time_remaining or 0
            
            self._add_label(section, f"↩️ Undo available: {action} on {obj}", 
                          color=self.visual_config.color_cyan)
            self._add_label(section, f"   Expires in {time_left:.1f}s", 
                          color=self.visual_config.color_muted)
            
            if self.snapshot.undo_confirming:
                self._add_label(section, "   ⏳ CONFIRMING UNDO...", 
                              color=self.visual_config.color_warning)
        else:
            self._add_label(section, "No undo available", color=self.visual_config.color_muted)
    
    # === HELPER METHODS ===
    
    def _create_progress_bar(self, current: int, total: int, width: int = 20) -> str:
        """Create ASCII progress bar"""
        if total == 0:
            return "[" + " " * width + "]"
        
        filled = int((current / total) * width)
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}]"
    
    def _draw_debug_info(self):
        """Optional debug section"""
        section = self._create_section("Debug Info")
        
        self._add_label(section, f"Frame: {self.snapshot.frame_id}", 
                      color=self.visual_config.color_muted)
        self._add_label(section, f"Time: {self.snapshot.system_time_ms:.0f}ms", 
                      color=self.visual_config.color_muted)
        self._add_label(section, f"Timestamp: {self.snapshot.timestamp:.3f}", 
                      color=self.visual_config.color_muted)

