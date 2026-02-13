"""
Keyboard decision source.

Reports raw key state. Does NOT debounce or edge-detect.
Those are the filter's responsibility.
"""
import logging
from src.input.source_base import DecisionSourceBase
from src.input.types import RawSourceReading, DecisionIntent, SourceType

logger = logging.getLogger(__name__)


class KeyboardSource(DecisionSourceBase):
    """
    Keyboard input source.
    
    Reports raw pressed state every frame.
    Quality is always 1.0 (keyboard is deterministic).
    """
    
    def __init__(self, config: dict):
        kb_cfg = config.get('keyboard', {})
        self.confirm_key = kb_cfg.get('confirm_key', 'c')
        self.cancel_key = kb_cfg.get('cancel_key', 'x')
        
        # Raw state (updated externally by event loop)
        self._confirm_pressed: bool = False
        self._cancel_pressed: bool = False
    
    def read_raw(self) -> RawSourceReading:
        """Read current keyboard state"""
        if self._cancel_pressed:
            return RawSourceReading(
                intent=DecisionIntent.CANCEL,
                source_type=SourceType.KEYBOARD,
                quality=1.0,
                raw_pressed=True,
                metadata={'key': self.cancel_key}
            )
        
        if self._confirm_pressed:
            return RawSourceReading(
                intent=DecisionIntent.CONFIRM,
                source_type=SourceType.KEYBOARD,
                quality=1.0,
                raw_pressed=True,
                metadata={'key': self.confirm_key}
            )
        
        return RawSourceReading(
            intent=DecisionIntent.NONE,
            source_type=SourceType.KEYBOARD,
            quality=1.0,
            raw_pressed=False,
        )
    
    def source_type(self) -> SourceType:
        return SourceType.KEYBOARD
    
    def name(self) -> str:
        return "keyboard"
    
    # Called by event loop / PyBullet key handler
    def set_key_state(self, confirm: bool, cancel: bool):
        """Update raw key pressed state (called by event loop)"""
        self._confirm_pressed = confirm
        self._cancel_pressed = cancel



