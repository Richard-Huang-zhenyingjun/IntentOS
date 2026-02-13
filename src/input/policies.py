"""
Decision routing policies.
Config-driven, determines how multiple sources are combined.
"""
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class RoutingMode(Enum):
    """How to combine multiple decision sources"""
    KEYBOARD_ONLY = "KEYBOARD_ONLY"  # Only keyboard (default)
    EEG_ONLY = "EEG_ONLY"            # Only EEG source
    ANY = "ANY"                       # Confirm if any source confirms
    DUAL = "DUAL"                     # Both sources must confirm within window


@dataclass
class DecisionPolicy:
    """Parsed decision policy from config"""
    mode: RoutingMode
    min_quality: float
    debounce_frames: int
    confirm_hold_frames: int
    dual_window_ms: float          # For DUAL mode
    dual_sources: List[str]        # For DUAL mode: ["keyboard", "eeg"]
    allowed_sources: List[str]     # Active sources
    
    @staticmethod
    def from_config(config: dict) -> 'DecisionPolicy':
        input_cfg = config.get('input', {})
        dual_cfg = input_cfg.get('dual', {})
        
        mode_str = input_cfg.get('mode', 'KEYBOARD_ONLY')
        try:
            mode = RoutingMode(mode_str)
        except ValueError:
            mode = RoutingMode.KEYBOARD_ONLY
        
        return DecisionPolicy(
            mode=mode,
            min_quality=input_cfg.get('min_quality', 0.65),
            debounce_frames=input_cfg.get('debounce_frames', 6),
            confirm_hold_frames=input_cfg.get('confirm_hold_frames', 1),
            dual_window_ms=dual_cfg.get('window_ms', 900),
            dual_sources=dual_cfg.get('sources', ['keyboard', 'eeg']),
            allowed_sources=input_cfg.get('sources_enabled', ['keyboard']),
        )



