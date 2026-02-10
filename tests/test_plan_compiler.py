import pytest
import numpy as np
import sys
from pathlib import Path

# Add parent directory so src can be imported as a package
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.planning.plan_compiler import PlanCompiler
from src.interfaces.primitive import PrimitiveType
from src.interfaces.intent_proposal import IntentProposal, ActionType
from src.interfaces.scene_summary import SceneSummary, ObjectInfo


@pytest.fixture
def config():
    """Test configuration"""
    return {
        'planning': {
            'clean_table': {
                'approach_height': 0.10,
                'grasp_height_offset': 0.02,
                'bin_hover_height': 0.12,
                'bin_drop_height_offset': 0.03,
                'workspace_bounds': [-0.6, 0.6, -0.6, 0.6, 0.0, 1.0],
                'safe_home_xyz': [0.3, 0.0, 0.8]
            }
        }
    }


@pytest.fixture
def world_with_objects():
    """World state with objects on table (not used by compiler anymore)"""
    # Week 3: Compiler no longer needs WorldState, only SceneSummary
    return None


@pytest.fixture
def scene_with_objects():
    """Scene summary with objects on table (frozen, uses tuples)"""
    objects = (
        ObjectInfo(object_id=10, pos_xyz=(0.2, 0.1, 0.65), on_table=True),
        ObjectInfo(object_id=11, pos_xyz=(0.1, -0.1, 0.65), on_table=True),
    )
    return SceneSummary(
        table_id=1,
        table_position=(0.0, 0.0, 0.3),
        bin_zone_center=(0.4, 0.0, 0.75),
        bin_zone_radius=0.12,
        objects=objects,
        objects_on_table=objects,
        clutter_score=0.4,
        is_messy=True,
        timestamp_frame=0
    )


def test_compile_clean_table_generates_primitives(config, world_with_objects, scene_with_objects):
    """CLEAN_TABLE proposal should generate primitive sequence"""
    
    compiler = PlanCompiler(config)
    
    proposal = IntentProposal(
        action=ActionType.CLEAN_TABLE,
        description="Clean the table",
        source="test",
        confidence=1.0
    )
    
    plan = compiler.compile(proposal, scene_with_objects)
    
    # Should generate 8 primitives (approach, pre-grasp, grasp, lift, move, lower, release, home)
    assert len(plan) == 8
    
    # Check primitive sequence
    assert plan[0].type == PrimitiveType.REACH  # Approach
    assert plan[1].type == PrimitiveType.REACH  # Pre-grasp
    assert plan[2].type == PrimitiveType.GRASP
    assert plan[3].type == PrimitiveType.MOVE_TO  # Lift
    assert plan[4].type == PrimitiveType.MOVE_TO  # Move to bin
    assert plan[5].type == PrimitiveType.MOVE_TO  # Lower
    assert plan[6].type == PrimitiveType.RELEASE
    assert plan[7].type == PrimitiveType.MOVE_TO  # Home
    
    # Check GRASP has object_id (should be nearest object to robot base)
    assert plan[2].object_id is not None
    assert plan[2].object_id in [10, 11]  # One of the two objects


def test_compile_rejects_out_of_bounds_object(config):
    """Objects outside workspace should be rejected"""
    
    compiler = PlanCompiler(config)
    
    # Object WAY outside workspace
    objects = (
        ObjectInfo(object_id=99, pos_xyz=(10.0, 10.0, 0.65), on_table=True),
    )
    scene = SceneSummary(
        table_id=1,
        table_position=(0.0, 0.0, 0.3),
        bin_zone_center=(0.4, 0.0, 0.75),
        bin_zone_radius=0.12,
        objects=objects,
        objects_on_table=objects,
        clutter_score=0.4,
        is_messy=True,
        timestamp_frame=0
    )
    
    proposal = IntentProposal(
        action=ActionType.CLEAN_TABLE,
        description="Clean the table",
        source="test",
        confidence=1.0
    )
    
    plan = compiler.compile(proposal, scene)
    
    # Should return empty plan (validation failed)
    assert len(plan) == 0


def test_compile_idle_returns_empty_plan(config, world_with_objects, scene_with_objects):
    """IDLE proposal should return empty plan"""
    
    compiler = PlanCompiler(config)
    
    proposal = IntentProposal(
        action=ActionType.IDLE,
        description="Do nothing",
        source="test",
        confidence=1.0
    )
    
    plan = compiler.compile(proposal, scene_with_objects)
    
    assert len(plan) == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
