"""
Tests that Gemini failures correctly trigger heuristic fallback.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.interfaces.scene_summary import SceneSummary, ObjectInfo
from src.interfaces.intent_proposal import ActionType
from src.intelligence.proposer_registry import ProposerRegistry
from src.intelligence.proposer_heuristic import HeuristicProposer
from src.intelligence.proposer_gemini import GeminiProposer
from src.external.gemini.client_fake import FakeGeminiClient


@pytest.fixture
def config():
    return {
        'gemini': {
            'enabled': True,
            'use_fake_client': True,
            'timeout_ms': 3000,
            'max_output_chars': 6000,
            'temperature': 0.0,
            'cache': {'min_interval_sec': 0.0, 'max_entries': 50},
            'logging': {'save_raw_response': False, 'truncate_chars': 2000},
        },
        'scene_understanding': {
            'messy_detection': {
                'min_objects': 3,
                'spread_threshold': 0.18,
                'z_on_table_eps': 0.04,
            },
        },
        'proposers': {
            'blocked_states': ['executing'],
        },
    }


@pytest.fixture
def messy_scene():
    objects = tuple(
        ObjectInfo(object_id=i, pos_xyz=(0.1*i, 0.05*i, 0.65), on_table=True)
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


def _build_registry(config, fake_client):
    """Helper to build registry with Gemini + heuristic"""
    registry = ProposerRegistry()
    heuristic = HeuristicProposer(config)
    registry.register("heuristic", heuristic, priority=0, is_fallback=True)
    
    gemini = GeminiProposer(client=fake_client, config=config)
    registry.register("gemini", gemini, priority=10)
    
    registry.set_blocked_states({'executing'})
    
    return registry


def test_gemini_success_uses_gemini(config, messy_scene):
    """When Gemini works, its proposal is used"""
    fake = FakeGeminiClient()
    fake.set_response('{"proposal_type": "CLEAN_TABLE", "object_ids": [0, 1], "rationale": "messy table"}')
    
    registry = _build_registry(config, fake)
    proposal = registry.propose(messy_scene)
    
    assert proposal.source == "gemini"
    assert proposal.action == ActionType.CLEAN_TABLE
    assert fake.get_call_count() == 1


def test_gemini_api_error_falls_back(config, messy_scene):
    """API error triggers heuristic fallback"""
    fake = FakeGeminiClient()
    fake.set_exception(ConnectionError("API unreachable"))
    
    registry = _build_registry(config, fake)
    proposal = registry.propose(messy_scene)
    
    assert proposal.source == "heuristic"
    assert proposal.action == ActionType.CLEAN_TABLE


def test_gemini_timeout_falls_back(config, messy_scene):
    """Timeout triggers heuristic fallback"""
    fake = FakeGeminiClient()
    fake.set_exception(TimeoutError("Request timed out"))
    
    registry = _build_registry(config, fake)
    proposal = registry.propose(messy_scene)
    
    assert proposal.source == "heuristic"
    assert proposal.action == ActionType.CLEAN_TABLE


def test_gemini_garbage_falls_back(config, messy_scene):
    """Invalid JSON triggers heuristic fallback"""
    fake = FakeGeminiClient()
    fake.set_response("This is not JSON, just random text from the model.")
    
    registry = _build_registry(config, fake)
    proposal = registry.propose(messy_scene)
    
    assert proposal.source == "heuristic"


def test_gemini_invalid_schema_falls_back(config, messy_scene):
    """Valid JSON but wrong schema triggers fallback"""
    fake = FakeGeminiClient()
    fake.set_response('{"action": "EXPLODE", "target": "everything"}')
    
    registry = _build_registry(config, fake)
    proposal = registry.propose(messy_scene)
    
    assert proposal.source == "heuristic"


def test_gemini_unavailable_falls_back(config, messy_scene):
    """Unavailable client triggers fallback without API call"""
    fake = FakeGeminiClient()
    fake.set_available(False)
    
    registry = _build_registry(config, fake)
    proposal = registry.propose(messy_scene)
    
    assert proposal.source == "heuristic"
    assert fake.get_call_count() == 0  # Never called


if __name__ == '__main__':
    pytest.main([__file__, '-v'])



