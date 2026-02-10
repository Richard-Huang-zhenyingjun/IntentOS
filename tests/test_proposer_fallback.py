"""
Test that proposer registry correctly falls back when external proposer fails.
"""
import pytest
import sys
from pathlib import Path

# Add parent directory so src can be imported as a package
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.interfaces.scene_summary import SceneSummary, ObjectInfo
from src.interfaces.intent_proposal import ActionType
from src.intelligence.proposer_registry import ProposerRegistry
from src.intelligence.proposer_heuristic import HeuristicProposer
from src.intelligence.proposer_fake_external import FakeExternalProposer


@pytest.fixture
def config():
    return {
        'scene_understanding': {
            'messy_detection': {
                'min_objects': 3,
                'spread_threshold': 0.18,
                'z_on_table_eps': 0.04
            }
        }
    }


@pytest.fixture
def messy_scene():
    objects = tuple(
        ObjectInfo(object_id=i, pos_xyz=(0.1 * i, 0.05 * i, 0.65), on_table=True)
        for i in range(5)
    )
    return SceneSummary(
        table_id=1,
        table_position=(0.0, 0.0, 0.3),
        bin_zone_center=(0.4, 0.0, 0.75),
        bin_zone_radius=0.12,
        objects=objects,
        objects_on_table=objects,
        clutter_score=0.5,
        is_messy=True,
        timestamp_frame=100,
    )


def test_registry_uses_highest_priority(config, messy_scene):
    """Higher priority proposer is used when available"""
    registry = ProposerRegistry()
    heuristic = HeuristicProposer(config)
    fake_external = FakeExternalProposer()
    
    registry.register("heuristic", heuristic, priority=0, is_fallback=True)
    registry.register("fake_external", fake_external, priority=10)
    
    proposal = registry.propose(messy_scene)
    
    # Should use fake_external (higher priority)
    assert proposal.source == "fake_external"
    assert fake_external.get_call_count() == 1


def test_registry_falls_back_on_unavailable(config, messy_scene):
    """Falls back to heuristic when external proposer unavailable"""
    registry = ProposerRegistry()
    heuristic = HeuristicProposer(config)
    fake_external = FakeExternalProposer()
    
    registry.register("heuristic", heuristic, priority=0, is_fallback=True)
    registry.register("fake_external", fake_external, priority=10)
    
    # Make external unavailable
    fake_external.set_available(False)
    
    proposal = registry.propose(messy_scene)
    
    # Should fall back to heuristic
    assert proposal.source == "heuristic"
    assert proposal.action == ActionType.CLEAN_TABLE
    assert fake_external.get_call_count() == 0  # Never called


def test_registry_falls_back_on_exception(config, messy_scene):
    """Falls back to heuristic when external proposer throws"""
    registry = ProposerRegistry()
    heuristic = HeuristicProposer(config)
    fake_external = FakeExternalProposer()
    
    registry.register("heuristic", heuristic, priority=0, is_fallback=True)
    registry.register("fake_external", fake_external, priority=10)
    
    # Make external throw on next call
    fake_external.set_fail_on_next()
    
    proposal = registry.propose(messy_scene)
    
    # Should fall back to heuristic (external threw)
    assert proposal.source == "heuristic"
    assert proposal.action == ActionType.CLEAN_TABLE
    
    # Should have logged the failure (but fallback_count only increments when ALL fail)
    stats = registry.get_stats()
    assert len(stats['recent_failures']) == 1
    assert stats['recent_failures'][0]['proposer'] == 'fake_external'
    # Note: fallback_count is 0 because heuristic succeeded (not a true "all failed" fallback)


def test_registry_tracks_fallback_rate(config, messy_scene):
    """Registry tracks failures and fallback usage"""
    registry = ProposerRegistry()
    heuristic = HeuristicProposer(config)
    fake_external = FakeExternalProposer()
    
    registry.register("heuristic", heuristic, priority=0, is_fallback=True)
    registry.register("fake_external", fake_external, priority=10)
    
    # 3 successful calls (fake_external works)
    for _ in range(3):
        registry.propose(messy_scene)
    
    # 2 failed calls (fake_external throws, falls back to heuristic)
    for _ in range(2):
        fake_external.set_fail_on_next()
        registry.propose(messy_scene)
    
    stats = registry.get_stats()
    assert stats['total_proposals'] == 5
    # fallback_count is 0 because heuristic succeeded (not "all failed" scenario)
    # But failures are logged
    assert len(stats['recent_failures']) == 2
    assert all(f['proposer'] == 'fake_external' for f in stats['recent_failures'])


def test_heuristic_alone_always_works(config, messy_scene):
    """System works with ONLY heuristic registered (no external)"""
    registry = ProposerRegistry()
    heuristic = HeuristicProposer(config)
    registry.register("heuristic", heuristic, priority=0, is_fallback=True)
    
    proposal = registry.propose(messy_scene)
    
    assert proposal.source == "heuristic"
    assert proposal.action == ActionType.CLEAN_TABLE


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

