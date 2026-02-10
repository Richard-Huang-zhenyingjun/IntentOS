"""
Test that interface contracts are correctly frozen and typed.
"""
import pytest
import numpy as np
import sys
from pathlib import Path

# Add parent directory so src can be imported as a package
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.interfaces.scene_summary import SceneSummary, ObjectInfo
from src.interfaces.intent_proposal import IntentProposal, ActionType
from src.interfaces.primitive import Primitive, PrimitiveType


def test_scene_summary_is_frozen():
    """SceneSummary should be immutable"""
    scene = SceneSummary(
        table_id=1,
        table_position=(0.0, 0.0, 0.3),
        bin_zone_center=(0.4, 0.0, 0.75),
        bin_zone_radius=0.12,
        objects=(),
        objects_on_table=(),
        clutter_score=0.5,
        is_messy=True,
    )
    
    with pytest.raises(AttributeError):
        scene.clutter_score = 0.9  # Should fail - frozen


def test_object_info_is_frozen():
    """ObjectInfo should be immutable"""
    obj = ObjectInfo(object_id=1, pos_xyz=(0.1, 0.2, 0.6), on_table=True)
    
    with pytest.raises(AttributeError):
        obj.on_table = False  # Should fail - frozen


def test_intent_proposal_is_frozen():
    """IntentProposal should be immutable"""
    proposal = IntentProposal(
        action=ActionType.CLEAN_TABLE,
        description="Test"
    )
    
    with pytest.raises(AttributeError):
        proposal.action = ActionType.IDLE  # Should fail - frozen


def test_scene_summary_optional_fields_default():
    """Optional fields should have sensible defaults"""
    scene = SceneSummary(
        table_id=1,
        table_position=(0.0, 0.0, 0.3),
        bin_zone_center=(0.4, 0.0, 0.75),
        bin_zone_radius=0.12,
        objects=(),
        objects_on_table=(),
        clutter_score=0.0,
        is_messy=False,
    )
    
    assert scene.rgb_snapshot is None
    assert scene.eeg_quality is None
    assert scene.timestamp_frame == 0


def test_intent_proposal_default_fields():
    """IntentProposal optional fields"""
    proposal = IntentProposal(
        action=ActionType.IDLE,
        description="Nothing to do"
    )
    
    assert proposal.source == "unknown"
    assert proposal.confidence == 1.0
    assert proposal.suggested_object_ids is None
    assert proposal.risk_flags is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

