"""Intent Visualizer - Shows system reasoning in real-time."""

import tkinter as tk
from typing import Dict, Optional

class VisualConfig:
    """Visual styling configuration."""
    panel_width = 450
    font_mono = ("Consolas", 9)
    font_header = ("Arial", 11, "bold")
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

class IntentVisualizer:
    """
    Read-only visualization panel showing system reasoning.
    
    Makes trust visible by showing WHY decisions were made.
    """
    
    def __init__(self, parent: tk.Widget, config: Optional[VisualConfig] = None):
        self.config = config or VisualConfig()
        
        # Create main panel
        self.panel = tk.Frame(
            parent,
            width=self.config.panel_width,
            bg=self.config.color_bg,
            relief=tk.SUNKEN,
            borderwidth=2
        )
        self.panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=False)
        self.panel.pack_propagate(False)
        
        # Create scrollable canvas
        self.canvas = tk.Canvas(
            self.panel,
            bg=self.config.color_bg,
            highlightthickness=0,
            width=self.config.panel_width
        )
        self.scrollbar = tk.Scrollbar(
            self.panel,
            orient="vertical",
            command=self.canvas.yview
        )
        
        self.scrollable_frame = tk.Frame(
            self.canvas,
            bg=self.config.color_bg
        )
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
    
    def render(self, snapshot: Dict):
        """
        Render complete system state (ENHANCED for Week 7)
        
        Section order:
        1. System state
        2. Scene status (NEW Week 7)
        3. Recovery/pause (NEW Week 7)
        4. Intent timeline
        5. Authority gates
        6. Multi-object state
        7. Multi-user state
        8. Prediction/proposal
        9. State inference
        10. Affordances
        11. Gestures
        12. Execution
        13. Undo
        """
        # Clear previous content
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        # Render all sections
        self._render_system_status(snapshot)
        self._render_separator()
        
        # Multi-object scene status (NEW - Week 7)
        self._draw_multi_object_section(snapshot)
        self._render_separator()
        
        # Recovery/pause status (NEW - Week 7)
        self._draw_recovery_section(snapshot)
        
        self._render_intent_timeline(snapshot)
        self._render_separator()
        
        self._render_authority_gates(snapshot)
        self._render_separator()
        
        self._render_multi_object_state(snapshot)
        self._render_separator()
        
        self._render_multi_user_state(snapshot)
        self._render_separator()
        
        self._render_prediction_proposal(snapshot)
        self._render_separator()
        
        self._draw_state_inference_section(snapshot)  # Week 6
        self._render_separator()
        
        self._render_affordances(snapshot)  # Week 3
        self._render_separator()
        
        self._render_gesture_confirmation(snapshot)  # NEW - Week 4
        self._render_separator()
        
        self._draw_execution_section(snapshot)  # NEW - Week 5
        self._render_separator()
        
        self._draw_undo_section(snapshot)  # NEW - Week 5
        self._render_separator()
        
        self._render_recovery_undo(snapshot)
    
    def _create_section(self, title: str) -> tk.Frame:
        """Create section with header."""
        section = tk.Frame(
            self.scrollable_frame,
            bg=self.config.color_bg,
            pady=8,
            padx=12
        )
        section.pack(fill=tk.X)
        
        header = tk.Label(
            section,
            text=title.upper(),
            font=self.config.font_header,
            fg=self.config.color_header,
            bg=self.config.color_bg,
            anchor="w"
        )
        header.pack(fill=tk.X, pady=(0, 5))
        
        return section
    
    def _render_separator(self):
        """Render visual separator."""
        sep = tk.Frame(
            self.scrollable_frame,
            height=1,
            bg=self.config.color_border
        )
        sep.pack(fill=tk.X, pady=3)
    
    def _render_system_status(self, snapshot: Dict):
        """Section: System Status (ENHANCED Week 8)."""
        section = self._create_section("System Status")
        
        system_status = snapshot.get("system_status", "UNKNOWN")
        current_user = snapshot.get("current_user", "None")
        
        # Get emoji and label for state (ENHANCED Week 8)
        state_str = str(system_status).lower()
        
        if state_str == 'paused':
            emoji = "⏸"
            label_text = "PAUSED"
        elif state_str == 'recovering':
            emoji = "🔄"
            label_text = "RECOVERING"
        elif state_str == 'undo_confirming':
            emoji = "↩️"
            label_text = "UNDO CONFIRMING"
        elif state_str == 'executing':
            emoji = "▶️"
            label_text = "EXECUTING"
        elif state_str == 'confirming':
            emoji = "✓"
            label_text = "CONFIRMING"
        elif state_str == 'scoped':
            emoji = "🎯"
            label_text = "SCOPED"
        elif state_str == 'idle':
            emoji = "⭘"
            label_text = "IDLE"
        else:
            emoji = "?"
            label_text = system_status.upper()
        
        state_text = f"{emoji} {label_text}"
        if current_user != "None":
            state_text += f" ({current_user})"
        
        state_label = tk.Label(
            section,
            text=state_text,
            font=("Arial", 18, "bold"),
            fg=self._get_state_color(system_status),
            bg=self.config.color_bg
        )
        state_label.pack(pady=5)
        
        # Show context if available (NEW Week 8)
        context = snapshot.get('context', {})
        
        if context.get('pause_reason'):
            reason_label = tk.Label(
                section,
                text=f"⚠️ {context['pause_reason']}",
                font=self.config.font_small,
                fg=self.config.color_error,
                bg=self.config.color_bg,
                wraplength=self.config.panel_width - 40
            )
            reason_label.pack(pady=2)
        
        if context.get('recovery_required'):
            recovery_label = tk.Label(
                section,
                text="→ Recovery required",
                font=self.config.font_small,
                fg=self.config.color_warning,
                bg=self.config.color_bg
            )
            recovery_label.pack(pady=2)
        
        # Legacy why_nothing support
        why_nothing = snapshot.get("why_nothing_happened")
        if why_nothing and not context.get('pause_reason'):
            reason_label = tk.Label(
                section,
                text=f"→ {why_nothing}",
                font=self.config.font_small,
                fg=self.config.color_warning,
                bg=self.config.color_bg,
                wraplength=self.config.panel_width - 40
            )
            reason_label.pack(pady=2)
    
    def _get_state_color(self, state: str) -> str:
        """Get color for system state (ENHANCED Week 8)."""
        state_str = str(state).lower()
        
        # Critical states (red)
        if "paused" in state_str:
            return self.config.color_error
        
        # Warning states (yellow/orange)
        elif "recovering" in state_str:
            return self.config.color_warning
        elif "confirming" in state_str:
            return self.config.color_warning
        elif "undo_confirming" in state_str:
            return self.config.color_warning
        elif "scoped" in state_str:
            return self.config.color_warning
        
        # Active states (green)
        elif "executing" in state_str:
            return self.config.color_success
        
        # Neutral states (default)
        else:
            return self.config.color_text
    
    def _render_intent_timeline(self, snapshot: Dict):
        """Section: Intent Timeline (CRITICAL - shows decision flow)."""
        section = self._create_section("Intent Timeline (Last 5)")
        
        timeline = snapshot.get("recent_timeline", [])
        
        if not timeline:
            no_events = tk.Label(
                section,
                text="(No recent events)",
                font=self.config.font_mono,
                fg=self.config.color_muted,
                bg=self.config.color_bg
            )
            no_events.pack()
            return
        
        for event in timeline[-5:]:
            self._render_timeline_event(section, event)
    
    def _render_timeline_event(self, parent: tk.Frame, event: Dict):
        """Render single timeline event."""
        timestamp = event.get("timestamp", 0.0)
        intent_type = event.get("intent_type", "UNKNOWN")
        target = event.get("target", "")
        confidence = event.get("confidence", 0.0)
        result = event.get("result", "")
        
        if target:
            event_text = f"t={timestamp:5.1f} | {intent_type:10s} ({target:10s}) | c={confidence:.2f}"
        else:
            event_text = f"t={timestamp:5.1f} | {intent_type:10s} | c={confidence:.2f}"
        
        if result:
            event_text += f" → {result}"
        
        fg_color = self.config.color_text
        if "BLOCKED" in str(result) or "REFUSED" in str(result):
            fg_color = self.config.color_error
        elif "EXECUTE" in str(result):
            fg_color = self.config.color_success
        
        event_label = tk.Label(
            parent,
            text=event_text,
            font=self.config.font_mono,
            fg=fg_color,
            bg=self.config.color_bg,
            anchor="w"
        )
        event_label.pack(fill=tk.X)
    
    def _render_authority_gates(self, snapshot: Dict):
        """Section: Authority Gates (TRUST VISUALIZATION)."""
        section = self._create_section("Authority Gates")
        
        gates = snapshot.get("authority_gates", {})
        
        gate_checks = [
            ("Scope present", gates.get("scope_present", False)),
            ("Confirmation received", gates.get("confirmation_received", False)),
            ("Ambiguity clear", not gates.get("ambiguity_detected", True)),
            ("Identity valid", gates.get("identity_valid", False)),
            ("Lock acquired", gates.get("lock_acquired", False)),
            ("Confidence stable", gates.get("confidence_stable", False)),
            ("Execution allowed", gates.get("execution_allowed", False)),
        ]
        
        for gate_name, passed in gate_checks:
            icon = "✅" if passed else "❌"
            color = self.config.color_success if passed else self.config.color_error
            
            gate_label = tk.Label(
                section,
                text=f"{icon} {gate_name}",
                font=self.config.font_mono,
                fg=color,
                bg=self.config.color_bg,
                anchor="w"
            )
            gate_label.pack(fill=tk.X)
    
    def _render_multi_object_state(self, snapshot: Dict):
        """Section: Multi-Object Awareness."""
        section = self._create_section("Multi-Object (Week 6)")
        
        multi_context = snapshot.get("multi_object_context", {})
        
        self._render_info_line(section, "Candidates tracked", str(multi_context.get("active_candidates", 0)))
        self._render_info_line(section, "Primary focus", str(multi_context.get("primary_focus") or "NONE"))
        
        ambiguity = multi_context.get("ambiguity_detected", False)
        self._render_info_line(
            section,
            "Ambiguity",
            "YES ⚠️" if ambiguity else "NO",
            self.config.color_warning if ambiguity else self.config.color_success
        )
    
    def _render_multi_user_state(self, snapshot: Dict):
        """Section: Multi-User/Ownership."""
        section = self._create_section("Multi-User (Week 7)")
        
        active_user = snapshot.get("current_user", "None")
        self._render_info_line(section, "Active user", active_user)
        
        user_states = snapshot.get("user_states", {})
        for user_id, state_info in user_states.items():
            state = state_info.get("state", "UNKNOWN")
            scope = state_info.get("scope") or "None"
            
            user_text = f"{user_id}: {state} (scope: {scope})"
            
            user_label = tk.Label(
                section,
                text=f"  • {user_text}",
                font=self.config.font_mono,
                fg=self.config.color_text,
                bg=self.config.color_bg,
                anchor="w"
            )
            user_label.pack(fill=tk.X)
    
    def _render_prediction_proposal(self, snapshot: Dict):
        """Section: Prediction & Proposal."""
        section = self._create_section("Prediction & Proposal")
        
        readonly_label = tk.Label(
            section,
            text="⚠️ READ-ONLY - Does NOT execute",
            font=self.config.font_small,
            fg=self.config.color_warning,
            bg=self.config.color_bg
        )
        readonly_label.pack(pady=2)
        
        prediction = snapshot.get("prediction")
        if prediction:
            pred_type = prediction.get("predicted_type", "UNKNOWN")
            pred_prob = prediction.get("probability", 0.0)
            
            pred_label = tk.Label(
                section,
                text=f"Prediction: {pred_type} ({pred_prob:.0%})",
                font=self.config.font_mono,
                fg=self.config.color_muted,
                bg=self.config.color_bg
            )
            pred_label.pack(fill=tk.X)
        
        proposal = snapshot.get("proposal")
        if proposal:
            prop_type = proposal.get("type", "UNKNOWN")
            
            prop_label = tk.Label(
                section,
                text=f"Proposal: {prop_type}",
                font=self.config.font_mono,
                fg=self.config.color_muted,
                bg=self.config.color_bg
            )
            prop_label.pack(fill=tk.X)
        
        if not prediction and not proposal:
            none_label = tk.Label(
                section,
                text="(None active)",
                font=self.config.font_mono,
                fg=self.config.color_muted,
                bg=self.config.color_bg
            )
            none_label.pack()
    
    def _draw_state_inference_section(self, snapshot: Dict):
        """
        Draw state inference section (NEW Week 6)
        
        Shows:
        - Object category
        - Estimated state + confidence
        - Inference method
        - Evidence/reason
        """
        section = self._create_section("STATE INFERENCE (READ-ONLY)")
        
        if not snapshot.get('state_estimate'):
            self.add_line("No state inference available", color='gray', parent=section)
            return
        
        state_est = snapshot['state_estimate']
        
        # Category
        category = state_est.get('category', 'unknown')
        self.add_line(f"Category: {category.upper()}", parent=section)
        
        # State
        state = state_est.get('state', 'unknown')
        confidence = state_est.get('confidence', 0.0)
        method = state_est.get('method', 'unknown')
        
        # Color code by confidence
        if confidence >= 0.7:
            conf_color = 'green'
            conf_label = "HIGH"
        elif confidence >= 0.4:
            conf_color = 'yellow'
            conf_label = "MEDIUM"
        else:
            conf_color = 'red'
            conf_label = "LOW"
        
        self.add_line(f"State: {state.upper()} (conf={confidence:.2f})", color=conf_color, parent=section)
        self.add_line(f"Confidence: {conf_label}", color=conf_color, parent=section)
        
        # Method
        if method == 'world_state_hint':
            method_label = "🌐 Simulator State"
        elif method == 'visual_heuristic':
            method_label = "👁 Visual Analysis"
        else:
            method_label = f"❓ {method}"
        
        self.add_line(f"Method: {method_label}", color='gray', parent=section)
        
        # Reason
        reason = state_est.get('reason', '')
        if reason:
            self.add_line(f"Why: {reason}", color='gray', parent=section)
        
        # Show if fallback used
        if snapshot.get('affordances'):
            aff_reasoning = snapshot['affordances'].get('reasoning', {})
            if not aff_reasoning.get('state_aware', False):
                self.add_line("", parent=section)
                self.add_line("⚠️ State uncertain → using TOGGLE", color='yellow', parent=section)
    
    def _render_affordances(self, snapshot: Dict):
        """
        Section: Affordances (MODIFIED for Week 6)
        
        Shows:
        - Object category + confidence
        - 1-3 affordance options (or blocked reason)
        - State-aware vs toggle distinction
        - Clear "READ-ONLY" label
        """
        section = self._create_section("AFFORDANCES (READ-ONLY)")
        
        # Warning label
        readonly_label = tk.Label(
            section,
            text="⚠️ These are suggestions only - Confirmation required to execute",
            font=self.config.font_small,
            fg=self.config.color_warning,
            bg=self.config.color_bg
        )
        readonly_label.pack(pady=2)
        
        affordances = snapshot.get('affordances')
        
        if not affordances:
            no_aff = tk.Label(
                section,
                text="(No affordances available)",
                font=self.config.font_mono,
                fg=self.config.color_muted,
                bg=self.config.color_bg
            )
            no_aff.pack()
            return
        
        # Show category
        category = affordances.get('category', 'unknown')
        category_conf = affordances.get('category_confidence', 0.0)
        
        category_label = tk.Label(
            section,
            text=f"Object: {category.upper()} (confidence: {category_conf:.2f})",
            font=self.config.font_mono,
            fg=self.config.color_text,
            bg=self.config.color_bg,
            anchor="w"
        )
        category_label.pack(fill=tk.X, pady=(5, 2))
        
        # Show state-aware indicator (NEW Week 6)
        reasoning = affordances.get('reasoning', {})
        if reasoning.get('state_aware'):
            state_aware_label = tk.Label(
                section,
                text="✓ State-aware action",
                font=self.config.font_small,
                fg=self.config.color_success,
                bg=self.config.color_bg,
                anchor="w"
            )
            state_aware_label.pack(fill=tk.X, pady=2)
        else:
            state_uncertain_label = tk.Label(
                section,
                text="⚠️ State uncertain",
                font=self.config.font_small,
                fg=self.config.color_warning,
                bg=self.config.color_bg,
                anchor="w"
            )
            state_uncertain_label.pack(fill=tk.X, pady=2)
        
        # Check if blocked
        if affordances.get('blocked'):
            reason = affordances.get('block_reason', 'unknown reason')
            blocked_label = tk.Label(
                section,
                text=f"❌ BLOCKED: {reason}",
                font=self.config.font_mono,
                fg=self.config.color_error,
                bg=self.config.color_bg,
                anchor="w",
                wraplength=self.config.panel_width - 40
            )
            blocked_label.pack(fill=tk.X, pady=2)
            return
        
        # Show options
        options = affordances.get('options', [])
        
        if len(options) == 0:
            no_options = tk.Label(
                section,
                text="(No actions available)",
                font=self.config.font_mono,
                fg=self.config.color_muted,
                bg=self.config.color_bg
            )
            no_options.pack()
            return
        
        options_header = tk.Label(
            section,
            text=f"Options ({len(options)}):",
            font=self.config.font_mono,
            fg=self.config.color_text,
            bg=self.config.color_bg,
            anchor="w"
        )
        options_header.pack(fill=tk.X, pady=(5, 2))
        
        for i, opt in enumerate(options, 1):
            title = opt.get('title', 'Unknown')
            description = opt.get('description', '')
            risk = opt.get('risk', 'unknown')
            conf = opt.get('confidence', 0.0)
            aff_type = opt.get('affordance_type', 'unknown')
            
            # Color code by risk
            if risk == 'low':
                risk_color = self.config.color_success
            elif risk == 'medium':
                risk_color = self.config.color_warning
            else:
                risk_color = self.config.color_error
            
            # Format option line
            opt_frame = tk.Frame(section, bg=self.config.color_bg)
            opt_frame.pack(fill=tk.X, pady=1)
            
            opt_title = tk.Label(
                opt_frame,
                text=f"  {i}. {title}",
                font=self.config.font_mono,
                fg=self.config.color_text,
                bg=self.config.color_bg,
                anchor="w"
            )
            opt_title.pack(fill=tk.X)
            
            # Risk and confidence
            risk_label = tk.Label(
                opt_frame,
                text=f"     Risk: {risk.upper()} | Confidence: {conf:.2f}",
                font=self.config.font_small,
                fg=risk_color,
                bg=self.config.color_bg,
                anchor="w"
            )
            risk_label.pack(fill=tk.X)
            
            # Description if available
            if description:
                desc_label = tk.Label(
                    opt_frame,
                    text=f"     {description}",
                    font=self.config.font_small,
                    fg=self.config.color_muted,
                    bg=self.config.color_bg,
                    anchor="w",
                    wraplength=self.config.panel_width - 60
                )
                desc_label.pack(fill=tk.X)
    
    def _render_gesture_confirmation(self, snapshot: Dict):
        """
        Section: Gesture Confirmation (Week 4)
        
        Shows:
        - Hand detection status
        - Pinch progress (frames held / required)
        - Confirmation status
        - Block reasons (if any)
        """
        section = self._create_section("GESTURE CONFIRMATION")
        
        gesture = snapshot.get('gesture')
        
        if not gesture:
            disabled_label = tk.Label(
                section,
                text="Gesture detection disabled",
                font=self.config.font_mono,
                fg=self.config.color_muted,
                bg=self.config.color_bg
            )
            disabled_label.pack()
            return
        
        # Hand detection
        hand_detected = gesture.get('hand_detected', False)
        if hand_detected:
            hand_label = tk.Label(
                section,
                text="✓ Hand detected",
                font=self.config.font_mono,
                fg=self.config.color_success,
                bg=self.config.color_bg,
                anchor="w"
            )
            hand_label.pack(fill=tk.X, pady=2)
        else:
            no_hand_label = tk.Label(
                section,
                text="✗ No hand detected",
                font=self.config.font_mono,
                fg=self.config.color_muted,
                bg=self.config.color_bg,
                anchor="w"
            )
            no_hand_label.pack(fill=tk.X, pady=2)
            return
        
        # Pinch state
        frames_held = gesture.get('frames_held', 0)
        pinching = gesture.get('pinching', False)
        confirmed = gesture.get('confirmed', False)
        just_confirmed = gesture.get('just_confirmed', False)
        reason = gesture.get('reason', '')
        
        if confirmed:
            if just_confirmed:
                confirm_label = tk.Label(
                    section,
                    text="✓ CONFIRMED",
                    font=self.config.font_mono,
                    fg=self.config.color_success,
                    bg=self.config.color_bg,
                    anchor="w"
                )
                confirm_label.pack(fill=tk.X, pady=2)
            else:
                holding_label = tk.Label(
                    section,
                    text=f"✓ Holding: {frames_held} frames",
                    font=self.config.font_mono,
                    fg=self.config.color_success,
                    bg=self.config.color_bg,
                    anchor="w"
                )
                holding_label.pack(fill=tk.X, pady=2)
        elif pinching:
            # Show progress
            progress_label = tk.Label(
                section,
                text=f"⏳ Pinching... {frames_held}/6",
                font=self.config.font_mono,
                fg=self.config.color_warning,
                bg=self.config.color_bg,
                anchor="w"
            )
            progress_label.pack(fill=tk.X, pady=2)
            
            if reason:
                reason_label = tk.Label(
                    section,
                    text=f"  {reason}",
                    font=self.config.font_small,
                    fg=self.config.color_muted,
                    bg=self.config.color_bg,
                    anchor="w"
                )
                reason_label.pack(fill=tk.X)
        else:
            if reason:
                reason_label = tk.Label(
                    section,
                    text=f"  {reason}",
                    font=self.config.font_mono,
                    fg=self.config.color_muted,
                    bg=self.config.color_bg,
                    anchor="w"
                )
                reason_label.pack(fill=tk.X, pady=2)
        
        # Block warning
        gesture_blocked = snapshot.get('gesture_blocked')
        if gesture_blocked:
            block_reason = gesture_blocked.get('reason', 'Unknown reason')
            
            separator = tk.Frame(section, height=1, bg=self.config.color_border)
            separator.pack(fill=tk.X, pady=5)
            
            blocked_label = tk.Label(
                section,
                text="❌ Pinch ignored:",
                font=self.config.font_mono,
                fg=self.config.color_error,
                bg=self.config.color_bg,
                anchor="w"
            )
            blocked_label.pack(fill=tk.X, pady=2)
            
            reason_blocked_label = tk.Label(
                section,
                text=f"   {block_reason}",
                font=self.config.font_small,
                fg=self.config.color_error,
                bg=self.config.color_bg,
                anchor="w",
                wraplength=self.config.panel_width - 40
            )
            reason_blocked_label.pack(fill=tk.X)
    
    def _render_recovery_undo(self, snapshot: Dict):
        """Section: Recovery & Undo."""
        section = self._create_section("Recovery & Undo (Week 8)")
        
        paused_users = snapshot.get("paused_users", [])
        if paused_users:
            pause_label = tk.Label(
                section,
                text=f"⏸️ PAUSED: {', '.join(paused_users)}",
                font=self.config.font_mono,
                fg=self.config.color_error,
                bg=self.config.color_bg
            )
            pause_label.pack(fill=tk.X)
            
            pause_reason = snapshot.get("pause_reason")
            if pause_reason:
                reason_label = tk.Label(
                    section,
                    text=f"  Reason: {pause_reason}",
                    font=self.config.font_small,
                    fg=self.config.color_muted,
                    bg=self.config.color_bg
                )
                reason_label.pack(fill=tk.X)
        
        undo_available = snapshot.get("undo_available", {})
        for user_id, available in undo_available.items():
            if available:
                undo_label = tk.Label(
                    section,
                    text=f"↩️ Undo available for {user_id}",
                    font=self.config.font_mono,
                    fg=self.config.color_warning,
                    bg=self.config.color_bg
                )
                undo_label.pack(fill=tk.X)
    
    def _render_info_line(self, parent: tk.Frame, label: str, value: str, color: Optional[str] = None):
        """Render key-value info line."""
        text = f"{label}: {value}"
        
        info_label = tk.Label(
            parent,
            text=text,
            font=self.config.font_mono,
            fg=color or self.config.color_text,
            bg=self.config.color_bg,
            anchor="w"
        )
        info_label.pack(fill=tk.X)
    
    def _draw_multi_object_section(self, snapshot: Dict):
        """
        Draw multi-object scene status (NEW Week 7)
        
        Shows:
        - Number of tracked objects
        - Primary focus
        - Ambiguity state
        - Oscillation warnings
        """
        section = self._create_section("SCENE STATUS (Week 7)")
        
        if not snapshot.get('multi_object'):
            label = tk.Label(
                section,
                text="Single object mode",
                font=self.config.font_mono,
                fg=self.config.color_muted,
                bg=self.config.color_bg,
                anchor="w"
            )
            label.pack(fill=tk.X)
            return
        
        mo = snapshot['multi_object']
        
        # Candidate count
        num_candidates = mo.get('num_candidates', 0)
        if num_candidates == 0:
            label = tk.Label(
                section,
                text="No objects detected",
                font=self.config.font_mono,
                fg=self.config.color_muted,
                bg=self.config.color_bg,
                anchor="w"
            )
            label.pack(fill=tk.X)
            return
        elif num_candidates == 1:
            label = tk.Label(
                section,
                text="✓ 1 object in scene",
                font=self.config.font_mono,
                fg=self.config.color_success,
                bg=self.config.color_bg,
                anchor="w"
            )
            label.pack(fill=tk.X)
        else:
            label = tk.Label(
                section,
                text=f"👁 {num_candidates} objects in scene",
                font=self.config.font_mono,
                fg=self.config.color_warning,
                bg=self.config.color_bg,
                anchor="w"
            )
            label.pack(fill=tk.X)
        
        # Primary focus
        primary_id = mo.get('primary_id')
        primary_label = mo.get('primary_label')
        
        if primary_id:
            focus_text = f"Focus: {primary_label} ({primary_id[-4:]})" if len(primary_id) >= 4 else f"Focus: {primary_label}"
            label = tk.Label(
                section,
                text=focus_text,
                font=self.config.font_mono,
                fg=self.config.color_success,
                bg=self.config.color_bg,
                anchor="w"
            )
            label.pack(fill=tk.X)
        else:
            label = tk.Label(
                section,
                text="Focus: None",
                font=self.config.font_mono,
                fg=self.config.color_muted,
                bg=self.config.color_bg,
                anchor="w"
            )
            label.pack(fill=tk.X)
        
        # Ambiguity
        ambiguity = mo.get('ambiguity_detected', False)
        margin = mo.get('margin', 0.0)
        reason = mo.get('reason', '')
        
        if ambiguity:
            # Spacing
            tk.Label(section, text="", bg=self.config.color_bg).pack()
            
            label = tk.Label(
                section,
                text="⚠️ AMBIGUITY DETECTED",
                font=self.config.font_mono,
                fg=self.config.color_warning,
                bg=self.config.color_bg,
                anchor="w"
            )
            label.pack(fill=tk.X)
            
            label = tk.Label(
                section,
                text="  Multiple objects competing",
                font=self.config.font_small,
                fg=self.config.color_warning,
                bg=self.config.color_bg,
                anchor="w"
            )
            label.pack(fill=tk.X)
            
            label = tk.Label(
                section,
                text=f"  Margin: {margin:.3f}",
                font=self.config.font_small,
                fg=self.config.color_muted,
                bg=self.config.color_bg,
                anchor="w"
            )
            label.pack(fill=tk.X)
            
            label = tk.Label(
                section,
                text="  Waiting for clarity...",
                font=self.config.font_small,
                fg=self.config.color_warning,
                bg=self.config.color_bg,
                anchor="w"
            )
            label.pack(fill=tk.X)
        elif margin > 0 and margin < 0.3:
            # Close but not ambiguous
            label = tk.Label(
                section,
                text=f"  Margin: {margin:.3f} (close)",
                font=self.config.font_small,
                fg=self.config.color_warning,
                bg=self.config.color_bg,
                anchor="w"
            )
            label.pack(fill=tk.X)
        
        # Oscillation
        if snapshot.get('oscillation'):
            osc = snapshot['oscillation']
            if osc.get('oscillating'):
                # Spacing
                tk.Label(section, text="", bg=self.config.color_bg).pack()
                
                label = tk.Label(
                    section,
                    text="⚠️ OSCILLATION DETECTED",
                    font=self.config.font_mono,
                    fg=self.config.color_error,
                    bg=self.config.color_bg,
                    anchor="w"
                )
                label.pack(fill=tk.X)
                
                label = tk.Label(
                    section,
                    text="  Rapid attention switching",
                    font=self.config.font_small,
                    fg=self.config.color_error,
                    bg=self.config.color_bg,
                    anchor="w"
                )
                label.pack(fill=tk.X)
                
                suppressed_count = len(osc.get('suppressed_ids', []))
                label = tk.Label(
                    section,
                    text=f"  Suppressing {suppressed_count} objects",
                    font=self.config.font_small,
                    fg=self.config.color_error,
                    bg=self.config.color_bg,
                    anchor="w"
                )
                label.pack(fill=tk.X)
                
                if osc.get('suppressed_until'):
                    remaining = osc['suppressed_until'] - snapshot.get('timestamp', 0)
                    if remaining > 0:
                        label = tk.Label(
                            section,
                            text=f"  Cooldown: {remaining:.1f}s",
                            font=self.config.font_small,
                            fg=self.config.color_error,
                            bg=self.config.color_bg,
                            anchor="w"
                        )
                        label.pack(fill=tk.X)
    
    def _draw_recovery_section(self, snapshot: Dict):
        """
        Draw recovery/pause status (ENHANCED Week 8)
        
        Shows:
        - Pause state and trigger
        - What happened (detailed explanation)
        - What was cleared
        - Recovery steps (numbered)
        - Current progress
        - Evidence (if debug mode)
        """
        if not snapshot.get('recovery'):
            return
        
        recovery = snapshot['recovery']
        
        if not recovery.get('paused'):
            return
        
        section = self._create_section("⏸ SYSTEM PAUSED")
        
        # Spacing
        tk.Label(section, text="", bg=self.config.color_bg).pack()
        
        # === TRIGGER ===
        trigger = recovery.get('trigger', 'unknown')
        trigger_label = trigger.replace('_', ' ').title()
        
        label = tk.Label(
            section,
            text=f"Trigger: {trigger_label}",
            font=self.config.font_mono,
            fg=self.config.color_error,
            bg=self.config.color_bg,
            anchor="w",
            wraplength=self.config.panel_width - 40
        )
        label.pack(fill=tk.X, pady=2)
        
        # === REASON ===
        reason = recovery.get('reason', 'Unknown reason')
        
        label = tk.Label(
            section,
            text=f"Reason: {reason}",
            font=self.config.font_mono,
            fg=self.config.color_error,
            bg=self.config.color_bg,
            anchor="w",
            wraplength=self.config.panel_width - 40
        )
        label.pack(fill=tk.X, pady=(0, 5))
        
        # Spacing
        tk.Label(section, text="", bg=self.config.color_bg).pack()
        
        # === WHAT HAPPENED ===
        label = tk.Label(
            section,
            text="What happened:",
            font=self.config.font_mono,
            fg=self.config.color_warning,
            bg=self.config.color_bg,
            anchor="w"
        )
        label.pack(fill=tk.X)
        
        # Derive what was cleared from trigger
        happened_text = []
        if 'object_loss' in trigger:
            happened_text = [
                "  • Scoped object disappeared",
                "  • Confirmation was cancelled",
                "  • No action was executed"
            ]
        elif 'hand_loss' in trigger:
            happened_text = [
                "  • Hand tracking lost",
                "  • Confirmation was cancelled",
                "  • No action was executed"
            ]
        elif 'ambiguity' in trigger:
            happened_text = [
                "  • Multiple objects detected",
                "  • Unclear which to act on",
                "  • Confirmation was cancelled"
            ]
        elif 'confidence' in trigger:
            happened_text = [
                "  • Detection confidence dropped",
                "  • Object state uncertain",
                "  • Confirmation was cancelled"
            ]
        elif 'attention' in trigger:
            happened_text = [
                "  • User attention timeout",
                "  • No interaction detected",
                "  • System paused for safety"
            ]
        elif 'state_uncertainty' in trigger:
            happened_text = [
                "  • Object state became uncertain",
                "  • Cannot proceed safely",
                "  • Confirmation was cancelled"
            ]
        else:
            happened_text = [
                "  • System detected unsafe condition",
                "  • Confirmation was cancelled"
            ]
        
        for text in happened_text:
            label = tk.Label(
                section,
                text=text,
                font=self.config.font_small,
                fg=self.config.color_muted,
                bg=self.config.color_bg,
                anchor="w",
                wraplength=self.config.panel_width - 40
            )
            label.pack(fill=tk.X, pady=1)
        
        # Spacing
        tk.Label(section, text="", bg=self.config.color_bg).pack()
        
        # === RECOVERY STEPS ===
        label = tk.Label(
            section,
            text="How to recover:",
            font=self.config.font_mono,
            fg=self.config.color_warning,
            bg=self.config.color_bg,
            anchor="w"
        )
        label.pack(fill=tk.X)
        
        # Get recovery explanation (NEW Week 8)
        recovery_explanation = recovery.get('recovery_explanation', '')
        recovery_actions = recovery.get('recovery_actions', [])
        
        if recovery_explanation:
            # Display explanation
            for line in recovery_explanation.split('\n'):
                if line.strip():
                    label = tk.Label(
                        section,
                        text=f"  {line.strip()}",
                        font=self.config.font_small,
                        fg=self.config.color_muted,
                        bg=self.config.color_bg,
                        anchor="w",
                        wraplength=self.config.panel_width - 50
                    )
                    label.pack(fill=tk.X, pady=1)
        elif recovery_actions:
            # Display actions as numbered steps
            for i, action in enumerate(recovery_actions, 1):
                action_label = action.replace('_', ' ').title()
                label = tk.Label(
                    section,
                    text=f"  {i}. {action_label}",
                    font=self.config.font_small,
                    fg=self.config.color_muted,
                    bg=self.config.color_bg,
                    anchor="w",
                    wraplength=self.config.panel_width - 50
                )
                label.pack(fill=tk.X, pady=1)
        else:
            # Fallback generic steps based on trigger
            if 'object_loss' in trigger:
                instructions = [
                    "  1. Re-establish object in view",
                    "  2. Wait for stable scope",
                    "  3. Confirm action again"
                ]
            elif 'hand_loss' in trigger:
                instructions = [
                    "  1. Ensure hand is visible",
                    "  2. System will resume",
                    "  3. Re-confirm action"
                ]
            elif 'ambiguity' in trigger:
                instructions = [
                    "  1. Wait for clarity",
                    "  2. Move other objects away",
                    "  3. Re-confirm when clear"
                ]
            else:
                instructions = [
                    "  1. Address the issue above",
                    "  2. Re-focus on object",
                    "  3. Confirm action again"
                ]
            
            for instruction in instructions:
                label = tk.Label(
                    section,
                    text=instruction,
                    font=self.config.font_small,
                    fg=self.config.color_muted,
                    bg=self.config.color_bg,
                    anchor="w"
                )
                label.pack(fill=tk.X, pady=1)
        
        # === EVIDENCE (for debugging) ===
        # Check if debug mode enabled
        context = snapshot.get('context', {})
        debug_mode = snapshot.get('debug_mode', False)
        
        if debug_mode or evidence := recovery.get('evidence'):
            # Spacing
            tk.Label(section, text="", bg=self.config.color_bg).pack()
            
            label = tk.Label(
                section,
                text="Debug Evidence:",
                font=self.config.font_small,
                fg=self.config.color_muted,
                bg=self.config.color_bg,
                anchor="w"
            )
            label.pack(fill=tk.X)
            
            if isinstance(evidence, dict):
                for key, value in evidence.items():
                    label = tk.Label(
                        section,
                        text=f"  {key}: {value}",
                        font=self.config.font_small,
                        fg=self.config.color_muted,
                        bg=self.config.color_bg,
                        anchor="w",
                        wraplength=self.config.panel_width - 50
                    )
                    label.pack(fill=tk.X, pady=1)
        
        self._render_separator()
    
    def add_section_header(self, title: str):
        """Add section header (helper for execution/undo sections)."""
        section = self._create_section(title)
        return section
    
    def add_line(self, text: str, color: str = None, parent: Optional[tk.Frame] = None):
        """Add a line of text (helper for execution/undo sections)."""
        if parent is None:
            # Use last created section if parent not specified
            parent = self.scrollable_frame.winfo_children()[-1] if self.scrollable_frame.winfo_children() else self.scrollable_frame
        
        color_map = {
            'yellow': self.config.color_warning,
            'green': self.config.color_success,
            'red': self.config.color_error,
            'gray': self.config.color_muted,
            'white': self.config.color_text
        }
        
        fg_color = color_map.get(color, self.config.color_text)
        
        label = tk.Label(
            parent,
            text=text,
            font=self.config.font_mono,
            fg=fg_color,
            bg=self.config.color_bg,
            anchor="w"
        )
        label.pack(fill=tk.X, pady=1)
    
    def _draw_execution_section(self, snapshot: Dict):
        """
        Draw execution status section (Week 5)
        
        Shows:
        - Highlighted option (what will execute)
        - Execution status
        - Last action result
        """
        section = self.add_section_header("EXECUTION")
        
        # Highlighted option
        highlighted_option = snapshot.get('highlighted_option')
        if highlighted_option:
            if isinstance(highlighted_option, dict):
                opt = highlighted_option
                title = opt.get('title', 'Unknown')
                risk = opt.get('risk', 'unknown')
            else:
                # Handle HighlightedOption object
                title = getattr(highlighted_option, 'option', {}).title if hasattr(highlighted_option, 'option') else 'Unknown'
                risk = getattr(highlighted_option, 'option', {}).risk.value if hasattr(highlighted_option, 'option') else 'unknown'
            
            self.add_line(f"► {title}", color='yellow', parent=section)
            self.add_line(f"  Risk: {risk}", color='gray', parent=section)
            self.add_line(f"  Pinch to execute", color='yellow', parent=section)
        else:
            self.add_line("No option highlighted", color='gray', parent=section)
        
        # Last execution result
        last_execution = snapshot.get('last_execution')
        if last_execution:
            result = last_execution
            if result.get('ok'):
                self.add_line("", parent=section)
                self.add_line(f"✓ Executed: {result.get('reason', 'Unknown')}", color='green', parent=section)
                if result.get('before_state') and result.get('after_state'):
                    before = result.get('before_state')
                    after = result.get('after_state')
                    # Format state dictionaries nicely
                    before_str = str(before) if isinstance(before, dict) else before
                    after_str = str(after) if isinstance(after, dict) else after
                    self.add_line(f"  {before_str} → {after_str}", color='gray', parent=section)
            else:
                self.add_line("", parent=section)
                self.add_line(f"✗ Refused: {result.get('reason', 'Unknown')}", color='red', parent=section)
    
    def _draw_undo_section(self, snapshot: Dict):
        """
        Draw undo section (ENHANCED Week 8)
        
        Shows:
        - Undo availability (state-aware)
        - What will be undone
        - Time remaining
        - Instructions
        - Blocking reasons (if any)
        """
        section = self.add_section_header("UNDO")
        
        undo_info = snapshot.get('undo_info')
        context = snapshot.get('context', {})
        system_state = snapshot.get('system_state', 'unknown')
        
        # Check if undo blocked by state (NEW Week 8)
        state_str = str(system_state).lower()
        blocked_by_state = state_str in ['paused', 'recovering', 'executing', 'confirming']
        
        if blocked_by_state:
            # Show why undo is blocked
            if state_str == 'paused':
                self.add_line("❌ Blocked: System paused", color='red', parent=section)
                self.add_line("  Recovery required first", color='gray', parent=section)
            elif state_str == 'recovering':
                self.add_line("❌ Blocked: System recovering", color='red', parent=section)
                self.add_line("  Complete recovery first", color='gray', parent=section)
            elif state_str == 'executing':
                self.add_line("❌ Blocked: Action executing", color='red', parent=section)
                self.add_line("  Wait for completion", color='gray', parent=section)
            elif state_str == 'confirming':
                self.add_line("❌ Blocked: Action confirming", color='red', parent=section)
                self.add_line("  Complete or cancel first", color='gray', parent=section)
            return
        
        if not undo_info or not undo_info.get('available'):
            self.add_line("Not available", color='gray', parent=section)
            
            # Show context-aware reason (NEW Week 8)
            if context.get('undo_available') is False:
                self.add_line("  No recent action", color='gray', parent=section)
            return
        
        # Extract undo info
        action_type = undo_info.get('action_type', 'unknown')
        action_label = undo_info.get('object_label', 'unknown')
        object_id = undo_info.get('object_id', 'unknown')
        time_remaining = undo_info.get('time_remaining', 0)
        confirming = undo_info.get('confirming', False)
        expired = undo_info.get('expired', False)
        
        # Check if expired
        if expired:
            self.add_line("⏱ Expired", color='red', parent=section)
            self.add_line(f"  Action: {action_type} on {action_label}", color='gray', parent=section)
            return
        
        # Show status based on state
        if confirming:
            self.add_line(f"⚠️ CONFIRMING", color='yellow', parent=section)
            self.add_line(f"  Action: {action_type}", color='gray', parent=section)
            self.add_line(f"  Object: {action_label}", color='gray', parent=section)
            self.add_line(f"  Pinch to undo", color='yellow', parent=section)
            
            # Time remaining with urgency
            if time_remaining < 2.0:
                self.add_line(f"  Expires: {time_remaining:.1f}s ⚠️", color='red', parent=section)
            else:
                self.add_line(f"  Expires: {time_remaining:.1f}s", color='yellow', parent=section)
        else:
            self.add_line(f"✓ Available", color='green', parent=section)
            self.add_line(f"  Action: {action_type}", color='gray', parent=section)
            self.add_line(f"  Object: {action_label}", color='gray', parent=section)
            self.add_line(f"  Press 'U' to request", color='gray', parent=section)
            
            # Time remaining
            if time_remaining < 3.0:
                self.add_line(f"  Expires: {time_remaining:.1f}s", color='red', parent=section)
            else:
                self.add_line(f"  Expires: {time_remaining:.1f}s", color='yellow', parent=section)

