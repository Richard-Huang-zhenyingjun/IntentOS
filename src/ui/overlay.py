"""Minimal debug overlay - displays state on screen."""

import pybullet as p
from typing import List
from src.core.schema import UISnapshot


class DebugOverlay:
    """Minimal on-screen debug info."""
    
    def __init__(self):
        self.text_items: List[int] = []
    
    def render(self, snapshot: UISnapshot):
        """Render debug info from snapshot."""
        # Clear old text
        for item_id in self.text_items:
            try:
                p.removeUserDebugItem(item_id)
            except:
                pass
        self.text_items.clear()
        
        # Build status text
        lines = [
            f"State: {snapshot.state.value}",
            f"Frame: {snapshot.frame_count}",
            f"Target: {snapshot.target_id} {'🔒' if snapshot.target_locked else ''}",
            f"Holding: {'✓' if snapshot.holding_object else '✗'} ({snapshot.attached_id})",
            f"False executions: {snapshot.false_executions} {'❌' if snapshot.false_executions > 0 else '✓'}",
        ]
        
        if snapshot.proposal:
            lines.append(f"Proposal: {snapshot.proposal.action.value}")
            lines.append(f"  {snapshot.proposal.reason}")
        
        if snapshot.paused:
            lines.append(f"⏸ PAUSED: {snapshot.pause_reason}")
        
        lines.append(f"Event: {snapshot.what_happened}")
        
        # Render text
        base_y = 0.8
        for i, line in enumerate(lines):
            text_id = p.addUserDebugText(
                line,
                textPosition=[0.1, 0.0, base_y - i * 0.05],
                textColorRGB=[1, 1, 1],
                textSize=1.2
            )
            self.text_items.append(text_id)

