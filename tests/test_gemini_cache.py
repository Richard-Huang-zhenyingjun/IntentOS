"""
Tests for Gemini scene cache and rate limiting.
"""
import pytest
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.interfaces.scene_summary import SceneSummary, ObjectInfo
from src.interfaces.intent_proposal import IntentProposal, ActionType
from src.external.gemini.cache import GeminiCache


@pytest.fixture
def config():
    return {
        'gemini': {
            'cache': {
                'min_interval_sec': 0.5,
                'max_entries': 10,
            }
        }
    }


@pytest.fixture
def scene_a():
    objects = tuple(
        ObjectInfo(object_id=i, pos_xyz=(0.1*i, 0.0, 0.65), on_table=True)
        for i in range(3)
    )
    return SceneSummary(
        table_id=1, table_position=(0, 0, 0.3),
        bin_zone_center=(0.4, 0, 0.75), bin_zone_radius=0.12,
        objects=objects, objects_on_table=objects,
        clutter_score=0.4, is_messy=True, timestamp_frame=1,
    )


@pytest.fixture
def scene_b():
    """Different scene (different objects)"""
    objects = tuple(
        ObjectInfo(object_id=i+10, pos_xyz=(0.2*i, 0.1, 0.65), on_table=True)
        for i in range(4)
    )
    return SceneSummary(
        table_id=1, table_position=(0, 0, 0.3),
        bin_zone_center=(0.4, 0, 0.75), bin_zone_radius=0.12,
        objects=objects, objects_on_table=objects,
        clutter_score=0.6, is_messy=True, timestamp_frame=2,
    )


def test_cache_miss_then_hit(config, scene_a):
    cache = GeminiCache(config)
    
    # First access = miss
    assert cache.get_cached(scene_a) is None
    assert cache.cache_misses == 1
    
    # Store result
    proposal = IntentProposal(action=ActionType.CLEAN_TABLE, description="test", source="gemini")
    cache.store(scene_a, proposal)
    
    # Second access = hit
    cached = cache.get_cached(scene_a)
    assert cached is not None
    assert cached.source == "gemini"
    assert cache.cache_hits == 1


def test_different_scenes_different_keys(config, scene_a, scene_b):
    cache = GeminiCache(config)
    
    proposal_a = IntentProposal(action=ActionType.CLEAN_TABLE, description="a", source="gemini")
    cache.store(scene_a, proposal_a)
    
    # Different scene = miss
    assert cache.get_cached(scene_b) is None


def test_rate_limiting(config, scene_a):
    cache = GeminiCache(config)  # min_interval_sec=0.5
    
    proposal = IntentProposal(action=ActionType.CLEAN_TABLE, description="test", source="gemini")
    cache.store(scene_a, proposal)  # Sets last_call_time
    
    # Immediately after store → rate limited
    assert cache.is_rate_limited() == True
    
    # Wait past interval
    time.sleep(0.6)
    assert cache.is_rate_limited() == False


def test_invalidate_clears_cache(config, scene_a):
    cache = GeminiCache(config)
    
    proposal = IntentProposal(action=ActionType.CLEAN_TABLE, description="test", source="gemini")
    cache.store(scene_a, proposal)
    
    assert cache.get_cached(scene_a) is not None
    
    cache.invalidate()
    
    assert cache.get_cached(scene_a) is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])



