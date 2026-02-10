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
        self.highlight_items: List[int] = []
        self.builder = OverlayBuilder()

    def _draw_object_highlight(self, object_id: int, color: List[float]) -> List[int]:
        """Draw a wireframe AABB highlight around a selected object."""
        line_ids: List[int] = []
        try:
            aabb_min, aabb_max = p.getAABB(object_id)
        except Exception:
            return line_ids

        corners = [
            [aabb_min[0], aabb_min[1], aabb_min[2]],
            [aabb_max[0], aabb_min[1], aabb_min[2]],
            [aabb_max[0], aabb_max[1], aabb_min[2]],
            [aabb_min[0], aabb_max[1], aabb_min[2]],
            [aabb_min[0], aabb_min[1], aabb_max[2]],
            [aabb_max[0], aabb_min[1], aabb_max[2]],
            [aabb_max[0], aabb_max[1], aabb_max[2]],
            [aabb_min[0], aabb_max[1], aabb_max[2]],
        ]
        edges = [
            (0, 1), (1, 2), (2, 3), (3, 0),
            (4, 5), (5, 6), (6, 7), (7, 4),
            (0, 4), (1, 5), (2, 6), (3, 7),
        ]
        for start_idx, end_idx in edges:
            line_ids.append(
                p.addUserDebugLine(
                    lineFromXYZ=corners[start_idx],
                    lineToXYZ=corners[end_idx],
                    lineColorRGB=color,
                    lineWidth=3,
                    lifeTime=0,
                )
            )
        return line_ids
    
    def render(self, snapshot: UISnapshot):
        """Render a compact, readable overlay and current target highlight."""
        # Clear old text
        for item_id in self.text_items:
            try:
                p.removeUserDebugItem(item_id)
            except:
                pass
        self.text_items.clear()

        # Clear old highlight lines
        for line_id in self.highlight_items:
            try:
                p.removeUserDebugItem(line_id)
            except Exception:
                pass
        self.highlight_items.clear()

        # Highlight current target for fast visual confirmation.
        if snapshot.target_id is not None:
            color = [0.0, 1.0, 0.0] if snapshot.target_locked else [1.0, 1.0, 0.0]
            self.highlight_items = self._draw_object_highlight(snapshot.target_id, color)

        proposal = snapshot.current_proposal if snapshot.current_proposal else snapshot.proposal
        lines: List[str] = []
        lines.append("=" * 40)
        lines.append(f"STATE: {snapshot.state.value.upper()}")
        if snapshot.autonomy_level:
            lines.append(f"AUTONOMY: {snapshot.autonomy_level}")
        if snapshot.task_trust is not None:
            trust_bar = self._render_week7_info(snapshot)
            lines.extend(trust_bar)
        lines.append("=" * 40)

        if proposal is not None:
            action = getattr(getattr(proposal, "action", None), "value", str(getattr(proposal, "action", "unknown")))
            lines.append(f"PROPOSAL: {action}")
            if hasattr(proposal, "confidence") and proposal.confidence is not None:
                lines.append(f"CONFIDENCE: {proposal.confidence:.2f}")

        if snapshot.executor_status and snapshot.executor_status != ExecutorStatus.IDLE:
            lines.append("EXECUTING...")
            lines.append(f"STEP: {snapshot.primitive_index + 1}")

        if snapshot.what_happened:
            lines.append(f"LAST: {self.builder._truncate(snapshot.what_happened)}")

        # Render to PyBullet screen
        base_y = 1.5
        line_spacing = 0.06
        for i, line in enumerate(lines):
            text_id = p.addUserDebugText(
                line,
                textPosition=[-0.9, 0.0, base_y - i * line_spacing],
                textColorRGB=[1, 1, 1],
                textSize=1.2,
                lifeTime=0
            )
            self.text_items.append(text_id)
    
    def _render_week7_info(self, snapshot: UISnapshot):
        """Week 7: Render trust, autonomy, and authorization info"""
        lines = []

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
            lines.append(f"TRUST: [{bar}] {trust:.2f}/1.00")
        
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
