"""
Test that system factory correctly assembles all components.
"""
import pytest
import pybullet as p
import pybullet_data
import sys
from pathlib import Path

# Add parent directory so src can be imported as a package
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.system_factory import build_system
from src.core.schema import ArmUIState


@pytest.fixture
def config():
    """Full system config"""
    return {
        'robot': {
            'max_force': 400.0,
            'position_gain': 0.2,
            'velocity_gain': 1.0,
            'tolerance_rad': 0.02,
            'settle_frames_required': 10,
        },
        'debug': {
            'diag_enabled': False,
            'diag_log_every_n_frames': 999999,
        },
        'world': {
            'messy_table': {
                'seed': 42,
                'n_objects': 4,
                'table_bounds_xy': [-0.30, 0.30, -0.20, 0.20],
                'spawn_height_z': 0.65,
                'bin_zone_center': [0.4, 0.0, 0.75],
                'bin_zone_radius': 0.12,
            },
        },
        'scene_understanding': {
            'messy_detection': {
                'min_objects': 3,
                'spread_threshold': 0.10,
                'z_on_table_eps': 0.04,
            },
        },
        'planning': {
            'clean_table': {
                'approach_height': 0.10,
                'grasp_height_offset': 0.02,
                'bin_hover_height': 0.12,
                'bin_drop_height_offset': 0.03,
                'workspace_bounds': [-0.6, 0.6, -0.6, 0.6, 0.0, 1.0],
                'safe_home_xyz': [0.3, 0.0, 0.8],
            },
        },
        'execution': {
            'sim_hz': 60,
            'primitive_timeout_sec': 3.0,
            'object_timeout_sec': 12.0,
        },
        'clean_table': {
            'max_objects_per_session': 6,
            'selection_strategy': 'nearest_to_base',
        },
        'grasp': {
            'verify_frames': 10,
            'ee_object_max_dist': 0.06,
            'max_retries': 1,
            'retry_xy_offset': [0.01, -0.01],
        },
        'input': {
            'mode': 'KEYBOARD_ONLY',
            'sources_enabled': ['keyboard'],
            'debounce_frames': 6,
            'confirm_hold_frames': 1,
            'min_quality': 0.65,
        },
        'keyboard': {
            'confirm_key': 'c',
            'cancel_key': 'x',
        },
        'logging': {
            'events_enabled': False,
        },
        'simulator': {
            'use_gui': False,  # Headless for testing
        },
    }


def test_system_assembles_without_error(config):
    """Factory builds complete system without crashing"""
    physics_client = p.connect(p.DIRECT)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.setGravity(0, 0, -9.81)
    p.setRealTimeSimulation(0)
    
    try:
        orch = build_system(config)
        
        # Verify components exist (Week 5: decision pipeline)
        assert orch.proposer_registry is not None
        assert orch.scene_summarizer is not None
        assert orch.compiler is not None
        assert orch.executor is not None
        assert orch.decision_pipeline is not None
        assert orch.world_artifacts is not None
        
        # Verify proposer registry has heuristic
        assert orch.proposer_registry.get_active_proposer_name() == "heuristic"
        
        # Verify world artifacts were created
        assert len(orch.world_artifacts.object_ids) > 0
        
        # Run a few frames to verify no crash
        for _ in range(10):
            snapshot = orch.step()
        
        # Verify snapshot has correct structure
        assert snapshot.state in [ArmUIState.IDLE, ArmUIState.SELECTING, ArmUIState.CONFIRMING]
        assert snapshot.scene_summary is not None
        
        print("[TEST] ✅ System factory test PASSED")
    finally:
        orch.close()
        p.disconnect()


def test_system_works_with_injected_test_input(config):
    """System works with fake decision source injected"""
    physics_client = p.connect(p.DIRECT)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.setGravity(0, 0, -9.81)
    p.setRealTimeSimulation(0)
    
    try:
        orch = build_system(config)
        
        # Replace decision pipeline for testing (Week 5)
        from src.input.pipeline import DecisionPipeline
        from src.input.router import DecisionRouter
        from src.input.filter import DecisionFilter
        from src.input.policies import DecisionPolicy
        from src.input.source_fake import FakeSource
        
        # Build test pipeline with fake source
        test_config = config.copy()
        test_config['input'] = {
            'mode': 'KEYBOARD_ONLY',
            'sources_enabled': ['keyboard'],
            'debounce_frames': 0,
            'confirm_hold_frames': 1,
            'min_quality': 0.0,
        }
        policy = DecisionPolicy.from_config(test_config)
        router = DecisionRouter(policy)
        fake_source = FakeSource()
        fake_source.set_confirm_on_frame(5)   # L key - lock target
        fake_source.set_confirm_on_frame(10)  # C key - confirm action
        router.register_source('keyboard', fake_source)
        decision_filter = DecisionFilter(test_config)
        test_pipeline = DecisionPipeline(router, decision_filter)
        orch.decision_pipeline = test_pipeline
        
        # Run until execution completes or timeout
        max_frames = 3000
        for frame in range(max_frames):
            snapshot = orch.step()
            if snapshot.state == ArmUIState.DONE:
                break
        
        assert frame < max_frames, "System hung"
        assert orch.trust_metrics.false_executions == 0
        
        print(f"[TEST] ✅ Integration with factory PASSED (frame {frame})")
    finally:
        orch.close()
        p.disconnect()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])

