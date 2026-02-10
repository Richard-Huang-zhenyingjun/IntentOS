from dataclasses import dataclass
from typing import List, Optional, Tuple
import numpy as np
from src.robot.world_state import WorldState
from src.worlds.world_artifacts import WorldArtifacts

@dataclass
class ObjectInfo:
    """Minimal object description for scene understanding"""
    object_id: int
    pos_xyz: Tuple[float, float, float]
    on_table: bool

@dataclass
class SceneSummary:
    """Pure computation - no side effects"""
    table_id: Optional[int]
    bin_zone_center: Tuple[float, float, float]
    bin_zone_radius: float
    objects: List[ObjectInfo]
    objects_on_table: List[ObjectInfo]  # Filtered subset
    clutter_score: float  # 0.0 (clean) to 1.0 (very messy)
    is_messy: bool

def summarize(world_state: WorldState, artifacts: WorldArtifacts, config: dict) -> SceneSummary:
    """
    Compute scene summary from world state.
    Deterministic - same world state always produces same summary.
    """
    # Get config thresholds
    messy_cfg = config['scene_understanding']['messy_detection']
    min_objects = messy_cfg['min_objects']
    spread_thresh = messy_cfg['spread_threshold']
    z_eps = messy_cfg['z_on_table_eps']
    
    # Assume table is at z=0.6 (or get from artifacts if you track it)
    table_z = 0.6  # TODO: Get from actual table position
    
    # Identify objects on table
    objects_info = []
    objects_on_table = []
    
    # Check if WorldState has objects field (contract interface)
    if hasattr(world_state, 'objects') and world_state.objects:
        # Use WorldState.objects if available (contract-compliant path)
        for obj in world_state.objects:
            # Contract expects obj.id and obj.position
            obj_id = obj.id if hasattr(obj, 'id') else getattr(obj, 'object_id', None)
            obj_pos = obj.position if hasattr(obj, 'position') else None
            
            if obj_pos is None or obj_id is None:
                continue
                
            obj_z = obj_pos[2]
            on_table = abs(obj_z - table_z) < z_eps and obj_z > table_z
            
            info = ObjectInfo(
                object_id=obj_id,
                pos_xyz=tuple(obj_pos),
                on_table=on_table
            )
            objects_info.append(info)
            
            if on_table:
                objects_on_table.append(info)
    else:
        # Fallback: Use artifacts and query PyBullet directly (current implementation)
        import pybullet as p
        if artifacts and artifacts.object_ids:
            for obj_id in artifacts.object_ids:
                try:
                    pos, _ = p.getBasePositionAndOrientation(obj_id)
                    obj_z = pos[2]
                    on_table = abs(obj_z - table_z) < z_eps and obj_z > table_z
                    
                    info = ObjectInfo(
                        object_id=obj_id,
                        pos_xyz=tuple(pos),
                        on_table=on_table
                    )
                    objects_info.append(info)
                    
                    if on_table:
                        objects_on_table.append(info)
                except:
                    # Object may have been removed
                    continue
    
    # Compute clutter score (spread-based heuristic)
    if len(objects_on_table) < 2:
        clutter_score = 0.0
    else:
        # Get XY positions
        positions = np.array([obj.pos_xyz[:2] for obj in objects_on_table])
        
        # Compute bounding box area
        mins = positions.min(axis=0)
        maxs = positions.max(axis=0)
        bbox_area = (maxs[0] - mins[0]) * (maxs[1] - mins[1])
        
        # Normalize to 0-1 (larger spread = higher score)
        # Assume table is ~0.6m x 0.5m = 0.3 sq m max area
        max_area = 0.3
        clutter_score = min(1.0, bbox_area / max_area)
    
    # Determine if messy
    is_messy = (
        len(objects_on_table) >= min_objects and
        clutter_score >= spread_thresh
    )
    
    return SceneSummary(
        table_id=artifacts.table_id if artifacts else None,
        bin_zone_center=artifacts.bin_zone_center if artifacts else (0.0, 0.0, 0.0),
        bin_zone_radius=artifacts.bin_zone_radius if artifacts else 0.0,
        objects=objects_info,
        objects_on_table=objects_on_table,
        clutter_score=clutter_score,
        is_messy=is_messy
    )
