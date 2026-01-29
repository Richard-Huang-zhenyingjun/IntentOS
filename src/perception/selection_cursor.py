"""
Selection cursor - unified representation of gaze/mouse pointing.
Week 3: Abstract input source (gaze or mouse) into normalized 2D cursor.
"""

from dataclasses import dataclass
import time


def clamp01(x: float) -> float:
    """Clamp value to [0, 1] range."""
    return max(0.0, min(1.0, x))


@dataclass
class SelectionCursor:
    """
    Normalized 2D cursor representing user's pointing direction.
    
    Attributes:
        u: Horizontal position [0, 1] (0=left, 1=right)
        v: Vertical position [0, 1] (0=top, 1=bottom)
        confidence: Cursor quality [0, 1] (low confidence → use fallback)
        source: Input method ("gaze" or "mouse")
        timestamp: Unix timestamp of cursor reading
    """
    u: float              # Normalized [0, 1]
    v: float              # Normalized [0, 1]
    confidence: float     # [0, 1]
    source: str           # "gaze" or "mouse"
    timestamp: float      # time.time()
    
    def __post_init__(self):
        """Clamp u/v to valid range."""
        self.u = clamp01(self.u)
        self.v = clamp01(self.v)
        self.confidence = clamp01(self.confidence)
    
    def __repr__(self) -> str:
        """Human-readable summary."""
        return (
            f"SelectionCursor(source={self.source}, "
            f"pos=({self.u:.2f}, {self.v:.2f}), "
            f"conf={self.confidence:.2f})"
        )
    
    @staticmethod
    def from_mouse(u: float, v: float) -> 'SelectionCursor':
        """Create cursor from mouse position."""
        return SelectionCursor(
            u=u,
            v=v,
            confidence=1.0,  # Mouse is always reliable
            source="mouse",
            timestamp=time.time()
        )
    
    @staticmethod
    def from_gaze(u: float, v: float, confidence: float) -> 'SelectionCursor':
        """Create cursor from gaze estimate."""
        return SelectionCursor(
            u=u,
            v=v,
            confidence=confidence,
            source="gaze",
            timestamp=time.time()
        )




