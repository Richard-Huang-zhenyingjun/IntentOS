"""
Overlay layout manager - spatial positioning for panels.
Week 9 Enhanced: Professional grid layout for demo overlay.
"""

from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class PanelRegion:
    """Panel spatial region in world coordinates."""
    name: str
    position: Tuple[float, float, float]  # (x, y, z)
    width: float  # For text wrapping hints
    
    def anchor_offset(self, line: int) -> Tuple[float, float, float]:
        """Get position for line N within panel."""
        line_height = 0.04  # World units between lines
        x, y, z = self.position
        return (x, y, z - line * line_height)


class OverlayLayout:
    """
    7-panel grid layout for overlay.
    
    Layout (world space, anchored to table):
    - Left column (x=-0.5): System, Proposal, Execution
    - Right column (x=0.5): Target, EEG, Recovery
    - Footer (x=0, z=0.1): Trust metrics
    
    Panel structure:
    ┌─────────────────────┬─────────────────────┐
    │ [1. SYSTEM]         │ [2. TARGET & SCENE] │
    ├─────────────────────┼─────────────────────┤
    │ [3. PROPOSAL]       │ [4. EEG STATUS]     │
    ├─────────────────────┼─────────────────────┤
    │ [5. EXECUTION]      │ [6. RECOVERY]       │
    ├─────────────────────┴─────────────────────┤
    │ [7. TRUST METRICS]                        │
    └───────────────────────────────────────────┘
    """
    
    def __init__(self, table_center: Tuple[float, float, float] = (0.4, 0, 0.6)):
        """
        Initialize layout.
        
        Args:
            table_center: World position of table center (anchor point)
        """
        tx, ty, tz = table_center
        
        # Top row (z offset +0.5 from table)
        top_z = tz + 0.5
        
        # Middle row (z offset +0.3)
        mid_z = tz + 0.3
        
        # Bottom row (z offset +0.1)
        bot_z = tz + 0.1
        
        # Footer (z at table level)
        footer_z = tz
        
        # Left/right column x positions
        left_x = tx - 0.5
        right_x = tx + 0.5
        center_x = tx
        
        self.panels = {
            "system": PanelRegion("SYSTEM", (left_x, ty, top_z), width=0.4),
            "target": PanelRegion("TARGET", (right_x, ty, top_z), width=0.4),
            "proposal": PanelRegion("PROPOSAL", (left_x, ty, mid_z), width=0.4),
            "eeg": PanelRegion("EEG", (right_x, ty, mid_z), width=0.4),
            "execution": PanelRegion("EXECUTION", (left_x, ty, bot_z), width=0.4),
            "recovery": PanelRegion("RECOVERY", (right_x, ty, bot_z), width=0.4),
            "trust": PanelRegion("TRUST", (center_x, ty, footer_z), width=1.0),
        }
    
    def get_panel(self, name: str) -> PanelRegion:
        """Get panel region by name."""
        return self.panels[name]
    
    def list_panels(self) -> List[str]:
        """Get list of panel names."""
        return list(self.panels.keys())
    
    def render_panel_header(self, panel_name: str, p) -> int:
        """
        Render panel header (title bar).
        
        Args:
            panel_name: Panel name (e.g., "system")
            p: PyBullet instance
            
        Returns:
            Debug item ID for cleanup
        """
        panel = self.get_panel(panel_name)
        pos = panel.position
        
        # Panel header with brackets
        header_text = f"[{panel.name}]"
        
        item_id = p.addUserDebugText(
            header_text,
            pos,
            textColorRGB=[0.8, 0.8, 0.8],
            textSize=1.0
        )
        return item_id
    
    def render_panel_line(self, panel_name: str, line_num: int, text: str, 
                          color: Tuple[float, float, float], p) -> int:
        """
        Render a line within a panel.
        
        Args:
            panel_name: Panel name
            line_num: Line number (0 = header, 1 = first content line, etc.)
            text: Text content
            color: RGB color (0-1 range)
            p: PyBullet instance
            
        Returns:
            Debug item ID for cleanup
        """
        panel = self.get_panel(panel_name)
        pos = panel.anchor_offset(line_num)
        
        item_id = p.addUserDebugText(
            text,
            pos,
            textColorRGB=color,
            textSize=0.9
        )
        return item_id




