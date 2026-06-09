"""
Scene summarizer - computes SceneSummary from world state.
Extracted as a class for injectable dependency.
"""
import numpy as np
from src.interfaces.scene_summary import SceneSummary, ObjectInfo
from src.interfaces.world_artifacts import WorldArtifacts
from src.robot.world_state import WorldState


class SceneSummarizer:
    """
    Computes scene summary from world state.
    
    Deterministic, no external dependencies.
    Week 4+: May accept optional camera renderer for rgb_snapshot.
    """
    
    def __init__(self, config: dict):
        messy_cfg = config.get('scene_understanding', {}).get('messy_detection', {})
        self.min_objects = messy_cfg.get('min_objects', 3)
        self.spread_threshold = messy_cfg.get('spread_threshold', 0.18)
        self.z_on_table_eps = messy_cfg.get('z_on_table_eps', 0.04)
        self.object_height = messy_cfg.get('object_height', 0.06)
        self.table_top_z = 0.6  # TODO: get from world artifacts
    
    def summarize(
        self,
        world_state: WorldState,
        artifacts: WorldArtifacts,
        rgb_snapshot: np.ndarray = None,  # Week 4+
        timestamp_frame: int = 0
    ) -> SceneSummary:
        """
        Compute frozen scene summary.
        
        Same logic as Week 2 but returns frozen dataclass from interfaces.
        
        Args:
            world_state: Current world state with objects
            artifacts: World artifacts (table, objects, bin zone)
            rgb_snapshot: Optional RGB image (Week 4+)
            timestamp_frame: Frame number for timestamping
            
        Returns:
            Frozen SceneSummary from interfaces
        """
        # Identify objects on table
        all_objects = []
        on_table = []
        
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
                is_on_table = self._is_on_table_z(obj_z)
                
                info = ObjectInfo(
                    object_id=obj_id,
                    pos_xyz=tuple(obj_pos),
                    on_table=is_on_table
                )
                all_objects.append(info)
                if is_on_table:
                    on_table.append(info)
        else:
            # Fallback: Use artifacts and query PyBullet directly
            import pybullet as p
            if artifacts and artifacts.object_ids:
                for obj_id in artifacts.object_ids:
                    try:
                        pos, _ = p.getBasePositionAndOrientation(obj_id)
                        obj_z = pos[2]
                        is_on_table = self._is_on_table_z(obj_z)
                        
                        info = ObjectInfo(
                            object_id=obj_id,
                            pos_xyz=tuple(pos),
                            on_table=is_on_table
                        )
                        all_objects.append(info)
                        if is_on_table:
                            on_table.append(info)
                    except:
                        # Object may have been removed
                        continue
        
        # Compute clutter score
        clutter_score = self._compute_clutter(on_table)
        
        # Determine messy
        is_messy = (
            len(on_table) >= self.min_objects
            and clutter_score >= self.spread_threshold
        )
        
        # Return FROZEN summary (using interfaces)
        return SceneSummary(
            table_id=artifacts.table_id if artifacts else None,
            table_position=(0.0, 0.0, 0.3),  # TODO: from artifacts
            bin_zone_center=artifacts.bin_zone_center if artifacts else (0.0, 0.0, 0.0),
            bin_zone_radius=artifacts.bin_zone_radius if artifacts else 0.0,
            objects=tuple(all_objects),  # Frozen requires tuple
            objects_on_table=tuple(on_table),  # Frozen requires tuple
            clutter_score=clutter_score,
            is_messy=is_messy,
            timestamp_frame=timestamp_frame,
            rgb_snapshot=rgb_snapshot,
        )
    
    def _compute_clutter(self, objects_on_table) -> float:
        """Same algorithm as Week 2"""
        if len(objects_on_table) < 2:
            return 0.0
        
        positions = np.array([obj.pos_xyz[:2] for obj in objects_on_table])
        mins = positions.min(axis=0)
        maxs = positions.max(axis=0)
        bbox_area = (maxs[0] - mins[0]) * (maxs[1] - mins[1])
        max_area = 0.3
        return min(1.0, bbox_area / max_area)

    def _is_on_table_z(self, obj_z: float) -> bool:
        """Return True when an object's center is resting above the tabletop."""
        return (
            obj_z > self.table_top_z
            and obj_z <= self.table_top_z + self.object_height + self.z_on_table_eps
        )


