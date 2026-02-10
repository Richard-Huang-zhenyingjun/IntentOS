from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class WorldArtifacts:
    """Tracks everything created in the world for cleanup/validation"""
    table_id: int
    object_ids: List[int]
    bin_zone_center: Tuple[float, float, float]
    bin_zone_radius: float
    seed: int


