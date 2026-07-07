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


# --- Assistive-reach (CLEAR_SPECIFIC) scope gate ---------------------------
#
# Mirrors the adversarial shape of tests/test_objective_authorization.py's
# scope checks (wrong object / out-of-zone / extra objects / missing scope),
# but exercised directly against PlanCompiler.compile() in isolation - no
# orchestrator, no kernel, no continuation loop.

@pytest.fixture
def reach_config():
    """Config with a valid, in-bounds delivery zone."""
    return {
        'planning': {
            'clean_table': {
                'approach_height': 0.10,
                'grasp_height_offset': 0.02,
                'bin_hover_height': 0.12,
                'bin_drop_height_offset': 0.03,
                'workspace_bounds': [-0.6, 0.6, -0.6, 0.6, 0.0, 1.0],
                'safe_home_xyz': [0.3, 0.0, 0.8]
            },
            'assistive_reach': {
                'delivery_zone_name': 'user_delivery_zone',
                'delivery_zone_center_xyz': [0.15, 0.0, 0.65],
                'delivery_zone_radius': 0.12,
                'delivery_hover_height': 0.05,
            }
        }
    }


@pytest.fixture
def reach_scene():
    objects = (
        ObjectInfo(object_id=42, pos_xyz=(0.2, 0.1, 0.65), on_table=True),
        ObjectInfo(object_id=43, pos_xyz=(0.1, -0.1, 0.65), on_table=True),
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


def _reach_proposal(target_object_id, suggested_object_ids=None):
    return IntentProposal(
        action=ActionType.CLEAR_SPECIFIC,
        description=f"bring object {target_object_id} closer",
        source="reach_intent",
        confidence=0.85,
        suggested_object_ids=(
            suggested_object_ids if suggested_object_ids is not None else [target_object_id]
        ),
        metadata={
            "assist_action": "bring_closer",
            "target_object_id": target_object_id,
            # Deliberately wrong/attacker-controlled coordinates: the compiler
            # must never read these - only its own config.
            "delivery_zone_name": "attacker_zone",
            "delivery_zone_xyz": (99.0, 99.0, 99.0),
        },
    )


def test_compile_assistive_reach_generates_primitives(reach_config, reach_scene):
    """Valid target + valid zone should compile a full reach-deliver plan."""
    compiler = PlanCompiler(reach_config)
    proposal = _reach_proposal(target_object_id=42)

    plan = compiler.compile(proposal, reach_scene)

    assert len(plan) == 5
    assert [p.type for p in plan] == [
        PrimitiveType.REACH,
        PrimitiveType.REACH,
        PrimitiveType.GRASP,
        PrimitiveType.MOVE_TO,
        PrimitiveType.MOVE_TO,
    ]
    assert plan[2].object_id == 42
    # Final MOVE_TO must land inside the CONFIGURED zone, never the
    # proposer's attacker-controlled (99, 99, 99) metadata.
    final = plan[-1].target_xyz
    zone_center = np.array([0.15, 0.0, 0.65])
    assert np.linalg.norm(final - zone_center) <= 0.12
    assert plan[-1].metadata["zone_name"] == "user_delivery_zone"
    assert compiler.last_scope_rejection is None


def test_compile_assistive_reach_rejects_wrong_object(reach_config, reach_scene):
    """Target object not present in the live scene must be rejected."""
    compiler = PlanCompiler(reach_config)
    proposal = _reach_proposal(target_object_id=404)  # not in reach_scene

    plan = compiler.compile(proposal, reach_scene)

    assert plan == []
    assert "not a live table object" in compiler.last_scope_rejection


def test_compile_assistive_reach_rejects_extra_objects(reach_config, reach_scene):
    """suggested_object_ids touching more than the declared target must be rejected."""
    compiler = PlanCompiler(reach_config)
    proposal = _reach_proposal(target_object_id=42, suggested_object_ids=[42, 43])

    plan = compiler.compile(proposal, reach_scene)

    assert plan == []
    assert "may only touch object 42" in compiler.last_scope_rejection


def test_compile_assistive_reach_rejects_out_of_zone(reach_config, reach_scene):
    """A configured destination outside the zone radius must be rejected."""
    reach_config['planning']['assistive_reach']['delivery_hover_height'] = 5.0
    compiler = PlanCompiler(reach_config)
    proposal = _reach_proposal(target_object_id=42)

    plan = compiler.compile(proposal, reach_scene)

    assert plan == []
    assert "outside the" in compiler.last_scope_rejection
    assert "zone" in compiler.last_scope_rejection


def test_compile_assistive_reach_rejects_missing_zone(reach_config, reach_scene):
    """No assistive_reach config at all must reject, not crash."""
    del reach_config['planning']['assistive_reach']
    compiler = PlanCompiler(reach_config)
    proposal = _reach_proposal(target_object_id=42)

    plan = compiler.compile(proposal, reach_scene)

    assert plan == []
    assert compiler.last_scope_rejection == "delivery zone is not configured"


def test_compile_assistive_reach_rejects_no_target_specified(reach_config, reach_scene):
    """Missing target_object_id in metadata must reject."""
    compiler = PlanCompiler(reach_config)
    proposal = IntentProposal(
        action=ActionType.CLEAR_SPECIFIC,
        description="bring something closer",
        source="reach_intent",
        confidence=0.85,
        suggested_object_ids=[42],
        metadata={"assist_action": "bring_closer"},
    )

    plan = compiler.compile(proposal, reach_scene)

    assert plan == []
    assert compiler.last_scope_rejection == "no target object specified"


def test_compile_assistive_reach_false_executions_zero(reach_config, reach_scene):
    """
    Every rejection path must yield zero primitives - i.e. there is nothing
    for an executor to run. This is the compiler-level analog of
    false_executions == 0: no primitive is ever emitted for a rejected scope,
    so no execution can occur downstream regardless of what runs the plan.
    """
    bad_proposals = [
        _reach_proposal(target_object_id=404),               # wrong object
        _reach_proposal(target_object_id=42, suggested_object_ids=[42, 43]),  # extra objects
    ]
    compiler = PlanCompiler(reach_config)
    for proposal in bad_proposals:
        assert compiler.compile(proposal, reach_scene) == []

    out_of_zone_cfg = {
        'planning': {
            **reach_config['planning'],
            'assistive_reach': {
                **reach_config['planning']['assistive_reach'],
                'delivery_hover_height': 5.0,
            },
        }
    }
    assert PlanCompiler(out_of_zone_cfg).compile(
        _reach_proposal(target_object_id=42), reach_scene
    ) == []

    missing_zone_cfg = {'planning': {'clean_table': reach_config['planning']['clean_table']}}
    assert PlanCompiler(missing_zone_cfg).compile(
        _reach_proposal(target_object_id=42), reach_scene
    ) == []


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
