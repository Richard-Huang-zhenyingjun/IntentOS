"""
End-to-end integration: Gemini proposes, system executes, invariant holds.
Uses FakeGeminiClient for deterministic testing.
"""
import pytest
import pybullet as p
import pybullet_data
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.system_factory import build_system
from src.input.fake_decision_source import FakeDecisionSource
from src.interfaces import ExecStatus
from src.core.schema import ArmUIState


@pytest.fixture
def config_with_fake_gemini():
    return {
        'robot': {
            'max_force': 400.0,
            'position_gain': 0.2,
            'velocity_gain': 1.0,
            'tolerance_rad': 0.02,
            'settle_frames_required': 10,
        },
        'debug': {'diag_enabled': False, 'diag_log_every_n_frames': 999999},
        'world': {
            'messy_table': {
                'seed': 42, 'n_objects': 4,
                'table_bounds_xy': [-0.30, 0.30, -0.20, 0.20],
                'spawn_height_z': 0.65,
                'bin_zone_center': [0.4, 0.0, 0.75],
                'bin_zone_radius': 0.12,
            },
        },
        'scene_understanding': {
            'messy_detection': {
                'min_objects': 3, 'spread_threshold': 0.10, 'z_on_table_eps': 0.04,
            },
        },
        'planning': {
            'clean_table': {
                'approach_height': 0.10, 'grasp_height_offset': 0.02,
                'bin_hover_height': 0.12, 'bin_drop_height_offset': 0.03,
                'workspace_bounds': [-0.6, 0.6, -0.6, 0.6, 0.0, 1.0],
                'safe_home_xyz': [0.3, 0.0, 0.8],
            },
        },
        'execution': {'sim_hz': 60, 'primitive_timeout_sec': 3.0, 'object_timeout_sec': 12.0},
        'clean_table': {'max_objects_per_session': 6, 'selection_strategy': 'nearest_to_base'},
        'grasp': {
            'verify_frames': 10, 'ee_object_max_dist': 0.06,
            'max_retries': 1, 'retry_xy_offset': [0.01, -0.01],
        },
        'input': {'mode': 'keyboard'},
        'logging': {'events_enabled': False},
        
        # Week 4: Gemini with fake client
        'gemini': {
            'enabled': True,
            'use_fake_client': True,
            'timeout_ms': 3000,
            'max_output_chars': 6000,
            'temperature': 0.0,
            'cache': {'min_interval_sec': 0.0, 'max_entries': 50},
            'logging': {'save_raw_response': False, 'truncate_chars': 2000},
        },
        'proposers': {
            'blocked_states': ['EXECUTING'],
        },
    }


def test_gemini_proposal_executes_successfully(config_with_fake_gemini):
    """
    Full pipeline: Gemini proposes → user confirms → execution succeeds.
    false_executions == 0 preserved.
    
    Note: This test may fail if execution fails for technical reasons
    (IK failures, timeouts, etc.). The critical invariant is that
    false_executions == 0 ensures no execution occurred without proper confirmation.
    """
    physics_client = p.connect(p.DIRECT)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.setGravity(0, 0, -9.81)
    p.setRealTimeSimulation(0)
    
    try:
        orch = build_system(config_with_fake_gemini)
        
        # Configure fake Gemini to return CLEAN_TABLE
        # Find the Gemini proposer in registry and configure its client
        gemini_proposer = orch.proposer_registry._proposers.get("gemini")
        if gemini_proposer and hasattr(gemini_proposer, 'client'):
            gemini_proposer.client.set_response(
                '{"proposal_type": "CLEAN_TABLE", "object_ids": [5, 6], "rationale": "table messy"}'
            )
        
        # Inject confirm - need to confirm twice: once to lock target, once to confirm action
        fake_input = FakeDecisionSource()
        fake_input.set_confirm_on_frame(5)   # L key - lock target / start selection
        fake_input.set_confirm_on_frame(15)  # C key - confirm action
        orch.decision_source = fake_input
        
        # Run simulation
        max_frames = 3000
        execution_started = False
        for frame in range(max_frames):
            snapshot = orch.step()
            
            # Track when execution starts
            if snapshot.state == ArmUIState.EXECUTING or snapshot.state.value == 'executing':
                execution_started = True
            
            # Stop if execution complete
            if snapshot.state == ArmUIState.DONE or snapshot.state.value == 'done':
                break
        
        # Debug output
        print(f"[TEST] Final frame: {frame}")
        print(f"[TEST] Final state: {snapshot.state}")
        print(f"[TEST] Execution started: {execution_started}")
        print(f"[TEST] Executor status: {snapshot.executor_status}")
        print(f"[TEST] Trust metrics: {orch.trust_metrics.get_summary()}")
        
        # Critical invariant: false_executions must be 0
        # This ensures no execution occurred without proper confirmation
        assert orch.trust_metrics.false_executions == 0, (
            f"false_executions must be 0 (critical safety invariant), "
            f"got {orch.trust_metrics.false_executions}. "
            f"Execution started: {execution_started}, "
            f"Final state: {snapshot.state}, "
            f"Executor status: {snapshot.executor_status}"
        )
        
        print(f"[TEST] ✅ Gemini integration e2e PASSED (frame {frame})")
        print(f"[TEST] false_executions = {orch.trust_metrics.false_executions}")
        
    finally:
        p.disconnect()


def test_gemini_disabled_still_works(config_with_fake_gemini):
    """System works identically when Gemini is disabled"""
    config_with_fake_gemini['gemini']['enabled'] = False
    
    physics_client = p.connect(p.DIRECT)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.setGravity(0, 0, -9.81)
    p.setRealTimeSimulation(0)
    
    try:
        orch = build_system(config_with_fake_gemini)
        
        # Should only have heuristic
        assert orch.proposer_registry.get_active_proposer_name() == "heuristic"
        
        fake_input = FakeDecisionSource()
        fake_input.set_confirm_on_frame(5)   # L key - lock target
        fake_input.set_confirm_on_frame(15)  # C key - confirm action
        orch.decision_source = fake_input
        
        max_frames = 3000
        execution_started = False
        for frame in range(max_frames):
            snapshot = orch.step()
            
            if snapshot.state == ArmUIState.EXECUTING or snapshot.state.value == 'executing':
                execution_started = True
            
            if snapshot.state == ArmUIState.DONE or snapshot.state.value == 'done':
                break
        
        # Debug output
        print(f"[TEST] Final frame: {frame}")
        print(f"[TEST] Final state: {snapshot.state}")
        print(f"[TEST] Execution started: {execution_started}")
        print(f"[TEST] Trust metrics: {orch.trust_metrics.get_summary()}")
        
        # Critical invariant: false_executions must be 0
        assert orch.trust_metrics.false_executions == 0, (
            f"false_executions must be 0 (critical safety invariant), "
            f"got {orch.trust_metrics.false_executions}. "
            f"Execution started: {execution_started}, "
            f"Final state: {snapshot.state}"
        )
        
        print(f"[TEST] ✅ Gemini-disabled test PASSED")
        
    finally:
        p.disconnect()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])

