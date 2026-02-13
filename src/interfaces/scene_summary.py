"""
Frozen scene summary contract.
All proposers, compilers, and executors depend on this shape.
DO NOT MODIFY after Week 3 without updating all consumers.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import numpy as np


@dataclass(frozen=True)
class ObjectInfo:
    """Immutable object description for scene understanding"""
    object_id: int
    pos_xyz: Tuple[float, float, float]
    on_table: bool
    # Week 5+: optional category, confidence
    category: Optional[str] = None
    confidence: float = 1.0


@dataclass(frozen=True)
class SceneSummary:
    """
    Immutable scene snapshot.
    
    Frozen: prevents accidental mutation mid-pipeline.
    All fields available from Week 1 heuristics.
    Optional fields added for future consumers (Gemini, MNE).
    
    Why frozen=True:
    - Prevents scene.clutter_score = 999 bugs
    - Forces you to create new SceneSummary each frame (which you should anyway)
    - Tuples instead of Lists for immutability
    
    Why Tuple[ObjectInfo, ...] not List[ObjectInfo]:
    - Frozen dataclass can't contain mutable fields
    - Tuples are hashable (useful for caching later)
    """
    # Core (always populated)
    table_id: Optional[int]
    table_position: Tuple[float, float, float]
    bin_zone_center: Tuple[float, float, float]
    bin_zone_radius: float
    objects: Tuple[ObjectInfo, ...]          # All objects in scene
    objects_on_table: Tuple[ObjectInfo, ...]  # Filtered subset
    clutter_score: float                      # 0.0 (clean) to 1.0 (very messy)
    is_messy: bool
    
    # Timing
    timestamp_frame: int = 0
    
    # Week 4+: Camera data (Gemini needs this)
    rgb_snapshot: Optional[np.ndarray] = field(default=None, repr=False)
    
    # Week 6+: EEG quality context
    eeg_quality: Optional[float] = None



