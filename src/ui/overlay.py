"""Minimal debug overlay - displays state on screen - Enhanced for Week 1."""

import pybullet as p
from typing import List
from types import SimpleNamespace
from src.core.schema import UISnapshot

# Week 1 imports
from src.execution.primitive_executor import ExecutorStatus


class OverlayBuilder:
    """Build human-readable overlay text blocks from current system state."""

    def __init__(self, max_line_len: int = 40):
        self.max_line_len = max_line_len

    def _truncate(self, text: str) -> str:
        if len(text) <= self.max_line_len:
            return text
        return text[: self.max_line_len - 3] + "..."

    def build(
        self,
        state,
        scene_summary=None,
        proposal=None,
        trust: float | None = None,
        autonomy_level: str | None = None,
        last_event: str | None = None,
    ) -> List[str]:
        lines: List[str] = []

        lines.append(self._truncate(f"SYSTEM STATE: {state.value if hasattr(state, 'value') else state}"))
        if autonomy_level is not None:
            lines.append(self._truncate(f"Autonomy: {autonomy_level}"))
        if trust is not None:
            lines.append(self._truncate(f"Trust: {trust:.2f} / 1.00"))

        lines.append("SCENE")
        if scene_summary is not None:
            objects_on_table = getattr(scene_summary, "objects_on_table", []) or []
            bin_zone_center = getattr(scene_summary, "bin_zone_center", None)
            clutter = getattr(scene_summary, "clutter_score", None)
            lines.append(self._truncate(f"Objects on table: {len(objects_on_table)}"))
            lines.append(self._truncate(f"Bin zone: {'defined' if bin_zone_center is not None else 'missing'}"))
            if clutter is not None:
                lines.append(self._truncate(f"Clutter score: {clutter:.2f}"))

        lines.append("PROPOSAL")
        if proposal is not None:
            source = getattr(proposal, "source", "unknown")
            action = getattr(getattr(proposal, "action", None), "value", getattr(proposal, "action", "unknown"))
            confidence = getattr(proposal, "confidence", None)
            rationale = getattr(proposal, "description", None) or getattr(proposal, "reason", "")
            lines.append(self._truncate(f"Intent: {action} ({source})"))
            if confidence is not None:
                lines.append(self._truncate(f"Confidence: {confidence:.2f}"))
            if rationale:
                lines.append(self._truncate(f"Rationale: {rationale}"))

        if last_event:
            lines.append("LAST EVENT")
            lines.append(self._truncate(last_event))

        return lines


class DebugOverlay:
    """Minimal on-screen debug info."""
    
    def __init__(self):
        self.text_items: List[int] = []
        self.builder = OverlayBuilder()
    
    def render(self, snapshot: UISnapshot):
        """Enhanced overlay with scene understanding (Week 1)"""
        # Clear old text
        for item_id in self.text_items:
            try:
                p.removeUserDebugItem(item_id)
            except:
                pass
        self.text_items.clear()
        
        proposal = snapshot.current_proposal if snapshot.current_proposal else snapshot.proposal
        lines = self.builder.build(
            state=snapshot.state,
            scene_summary=snapshot.scene_summary,
            proposal=proposal,
            trust=snapshot.task_trust,
            autonomy_level=snapshot.autonomy_level,
            last_event=snapshot.what_happened if hasattr(snapshot, "what_happened") else "",
        )
        lines = ["=" * 60, "INTENT INTERFACE - Week 1", "=" * 60] + lines
        
        # NEW: Scene summary (verbose block retained for compatibility)
        if snapshot.scene_summary:
            scene = snapshot.scene_summary
            lines.append("")
            lines.append("SCENE:")
            lines.append(f"  Objects on table: {len(scene.objects_on_table)}")
            lines.append(f"  Clutter score: {scene.clutter_score:.2f}")
            lines.append(f"  Is messy: {'YES' if scene.is_messy else 'NO'}")
        
        # Proposal (verbose block retained for compatibility)
        if snapshot.current_proposal:
            prop = snapshot.current_proposal
            lines.append("")
            lines.append("PROPOSAL:")
            lines.append(f"  Action: {prop.action.value}")
            
            # Week 4: Show proposer source and confidence
            if hasattr(prop, 'source'):
                lines.append(f"  Source: {prop.source}")  # Shows "heuristic" or "gemini"
            if hasattr(prop, 'confidence'):
                lines.append(f"  Confidence: {prop.confidence:.2f}")
            
            # Description/reason (different field names in different types)
            if hasattr(prop, 'description'):
                lines.append(f"  Description: {prop.description}")
            elif hasattr(prop, 'reason'):
                lines.append(f"  Reason: {prop.reason}")
            
            # Metadata if available
            if hasattr(prop, 'metadata') and prop.metadata:
                lines.append(f"  Metadata: {prop.metadata}")
        
        # NEW: Executor status
        if snapshot.executor_status and snapshot.executor_status != ExecutorStatus.IDLE:
            lines.append("")
            lines.append("EXECUTION:")
            lines.append(f"  Status: {snapshot.executor_status.value}")
            lines.append(f"  Primitive: {snapshot.primitive_index + 1}")
        
        # Week 4: Proposer stats
        if hasattr(snapshot, 'proposer_stats') and snapshot.proposer_stats:
            stats = snapshot.proposer_stats
            lines.append("")
            lines.append("PROPOSER STATS:")
            lines.append(f"  Active: {stats.get('active_proposer', 'unknown')}")
            fallback_rate = stats.get('fallback_rate', 0.0)
            lines.append(f"  Fallback rate: {fallback_rate*100:.0f}%")
            total_proposals = stats.get('total_proposals', 0)
            if total_proposals > 0:
                lines.append(f"  Total proposals: {total_proposals}")
        
        # Week 7: Trust + Autonomy display
        week7_lines = self._render_week7_info(snapshot)
        if week7_lines:
            lines.append("")
            lines.extend(week7_lines)
        
        # Controls
        lines.append("")
        lines.append("CONTROLS:")
        lines.append("  L - Lock/Select target")
        lines.append("  C - Confirm action")
        lines.append("  X - Cancel action")
        lines.append("  R - Reset system")
        lines.append("  Q - Quit")
        lines.append("="*60)
        
        # Render to PyBullet screen
        base_y = 0.95
        for i, line in enumerate(lines):
            text_id = p.addUserDebugText(
                line,
                textPosition=[-0.9, 0.0, base_y - i * 0.04],
                textColorRGB=[1, 1, 1],
                textSize=1.2,
                lifeTime=0
            )
            self.text_items.append(text_id)
        
        # Also print to console (matching contract)
        overlay_text = "\n".join(lines)
        print(overlay_text)
    
    def _render_week7_info(self, snapshot: UISnapshot):
        """Week 7: Render trust, autonomy, and authorization info"""
        lines = []
        
        # Autonomy level
        if snapshot.autonomy_level:
            lines.append(f"AUTONOMY: {snapshot.autonomy_level}")
        
        # Trust bar
        if snapshot.task_trust is not None:
            trust = snapshot.task_trust
            bar_len = 20
            filled = int(trust * bar_len)
            # Note: PyBullet doesn't support colors in text, so we'll use symbols
            # Green: █, Yellow: ▓, Red: ▒
            if trust > 0.7:
                bar_symbol = '█'
            elif trust > 0.5:
                bar_symbol = '▓'
            else:
                bar_symbol = '▒'
            bar = bar_symbol * filled + '░' * (bar_len - filled)
            lines.append(f"TRUST: [{bar}] {trust:.2f}")
        
        # Authorization token
        if snapshot.auth_token_id:
            token_id = snapshot.auth_token_id
            lines.append(f"AUTH: {token_id[:12]}... ✓")
        elif snapshot.task_trust is not None:  # Only show if Week 7 is active
            lines.append("AUTH: None")
        
        # Re-auth status
        if snapshot.awaiting_reauth:
            lines.append("⚠️  RE-AUTH REQUIRED — Press C to confirm")
        elif snapshot.awaiting_object_confirm:
            lines.append("⏳ OBJECT CONFIRM — Press C for next object")
        
        return lines
