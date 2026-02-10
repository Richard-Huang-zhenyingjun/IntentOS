"""
Test that no Gemini calls occur during EXECUTING state.
This is a critical safety invariant.
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


def test_no_gemini_calls_during_executing(config, messy_scene):
    """
    Gemini must NEVER be called while FSM is in EXECUTING state.
    Registry should skip external proposers and use fallback only.
    """
    fake = FakeGeminiClient()
    fake.set_response('{"proposal_type": "CLEAN_TABLE", "object_ids": [0]}')
    
    registry = ProposerRegistry()
    heuristic = HeuristicProposer(config)
    gemini = GeminiProposer(client=fake, config=config)
    
    registry.register("heuristic", heuristic, priority=0, is_fallback=True)
    registry.register("gemini", gemini, priority=10)
    registry.set_blocked_states({'executing'})  # Use lowercase
    
    # Simulate IDLE state → Gemini should be called
    registry.update_fsm_state("idle")
    proposal_idle = registry.propose(messy_scene)
    calls_after_idle = fake.get_call_count()
    assert calls_after_idle >= 1, "Gemini should be called in IDLE state"
    
    # Simulate EXECUTING state → Gemini must NOT be called
    registry.update_fsm_state("executing")
    
    for _ in range(100):  # Simulate 100 frames of execution
        proposal_exec = registry.propose(messy_scene)
    
    calls_after_executing = fake.get_call_count()
    
    # Gemini call count should NOT increase during EXECUTING
    assert calls_after_executing == calls_after_idle, (
        f"Gemini called {calls_after_executing - calls_after_idle} times during EXECUTING!"
    )
    
    # Proposals during EXECUTING should come from heuristic
    registry.update_fsm_state("executing")
    proposal = registry.propose(messy_scene)
    assert proposal.source == "heuristic"


def test_gemini_resumes_after_executing(config, messy_scene):
    """Gemini should work again after EXECUTING ends"""
    fake = FakeGeminiClient()
    fake.set_response('{"proposal_type": "CLEAN_TABLE", "object_ids": [0]}')
    
    registry = ProposerRegistry()
    heuristic = HeuristicProposer(config)
    gemini = GeminiProposer(client=fake, config=config)
    
    registry.register("heuristic", heuristic, priority=0, is_fallback=True)
    registry.register("gemini", gemini, priority=10)
    registry.set_blocked_states({'executing'})
    
    # EXECUTING → blocked
    registry.update_fsm_state("executing")
    registry.propose(messy_scene)
    calls_during = fake.get_call_count()
    
    # Back to IDLE → unblocked
    registry.update_fsm_state("idle")
    fake.reset()  # Reset counter
    
    # Invalidate cache to force fresh call
    gemini.cache.invalidate()
    
    registry.propose(messy_scene)
    
    assert fake.get_call_count() >= 1, "Gemini should resume after EXECUTING ends"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])


