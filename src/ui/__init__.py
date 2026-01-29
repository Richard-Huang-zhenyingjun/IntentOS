"""
UI module - visual feedback and overlays.
Week 3: Selection overlay with PyBullet debug drawing.
Week 4: Intent overlay with state machine visualization.
Week 9: Professional 7-panel grid overlay (refactored).
"""

from .selection_overlay import SelectionOverlay
from .arm_intent_overlay import ArmIntentOverlay
from .overlay_layout import OverlayLayout, PanelRegion
from .text_panel import TextPanel

__all__ = [
    'SelectionOverlay',
    'ArmIntentOverlay',
    'OverlayLayout',
    'PanelRegion',
    'TextPanel',
]
