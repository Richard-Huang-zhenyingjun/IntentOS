import pytest
import numpy as np
import sys
from pathlib import Path

# Add parent directory so src can be imported as a package
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.intelligence.proposer_heuristic import HeuristicProposer
from src.interfaces.scene_summary import SceneSummary, ObjectInfo
from src.interfaces.intent_proposal import ActionType


def test_messy_table_triggers_clean_proposal():
    """Messy scene should propose CLEAN_TABLE"""
    
    # Create messy scene
    objects_on_table = [
        ObjectInfo(object_id=i, pos_xyz=(0.1*i, 0.1*i, 0.6), on_table=True)
        for i in range(5)  # 5 objects
    ]
    
    scene = SceneSummary(
        table_id=1,
        table_position=(0, 0, 0.3),
        bin_zone_center=(0.4, 0.0, 0.75),
        bin_zone_radius=0.12,
        objects=tuple(objects_on_table),
        objects_on_table=tuple(objects_on_table),
        clutter_score=0.5,  # High clutter
        is_messy=True,
        timestamp_frame=1
    )
    
    # Test proposer (Week 3: requires config)
    config = {
        'scene_understanding': {
            'messy_detection': {
                'min_objects': 3,
                'spread_threshold': 0.10,
                'z_on_table_eps': 0.04,
            }
        }
    }
    proposer = HeuristicProposer(config)
    proposal = proposer.propose(scene)  # Week 3: only takes scene, not world
    
    assert proposal is not None
    assert proposal.action == ActionType.CLEAN_TABLE
    # Check description contains relevant info
    assert proposal.description is not None
    assert proposal.source == "heuristic"


def test_clean_table_proposes_idle():
    """Clean scene should propose IDLE"""
    
    scene = SceneSummary(
        table_id=1,
        table_position=(0, 0, 0.3),
        bin_zone_center=(0.4, 0.0, 0.75),
        bin_zone_radius=0.12,
        objects=tuple(),
        objects_on_table=tuple(),  # No objects
        clutter_score=0.0,
        is_messy=False,
        timestamp_frame=1
    )
    
    # Test proposer (Week 3: requires config)
    config = {
        'scene_understanding': {
            'messy_detection': {
                'min_objects': 3,
                'spread_threshold': 0.10,
                'z_on_table_eps': 0.04,
            }
        }
    }
    proposer = HeuristicProposer(config)
    proposal = proposer.propose(scene)  # Week 3: only takes scene, not world
    
    assert proposal is not None
    assert proposal.action == ActionType.IDLE
    assert proposal.source == "heuristic"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
