"""
Test that system factory correctly assembles all components.
"""
import pytest
import pybullet as p
import pybullet_data
import sys
import yaml
from pathlib import Path

# Add parent directory so src can be imported as a package
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.system_factory import build_system
from src.core.system_factory import _build_arm_controller, _build_hardware_bridge
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
        assert orch.agent_registry is not None
        assert "arm" in orch.agent_registry
        assert orch.agent_registry.get("arm")._executor is orch.executor
        assert orch.execution_kernel is not None
        assert orch.intentos_planner is not None
        assert orch.intentos is not None
        assert orch.intentos._registry is orch.agent_registry
        assert orch.agent_coordinator is not None
        assert orch.intentos._coordinator is orch.agent_coordinator
        assert orch.agent_coordinator._cfg.max_parallel_agents == 1
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


def test_hardware_backend_builds_arm_controller_with_fake_serial(config):
    cfg = config.copy()
    cfg["hardware"] = {
        "backend": "hardware",
        "dry_run": True,
        "real": {
            "port": "/dev/mock",
            "baud": 115200,
        },
        "joint_limits": [
            [-90, 90],
            [-45, 90],
            [-90, 45],
            [-90, 90],
            [-180, 180],
            [0, 80],
        ],
    }

    controller = _build_arm_controller(cfg)

    from src.robot.hardware.arm_controller import HardwareArmController
    from src.robot.hardware.serial_controller_fake import FakeSerialController

    assert isinstance(controller, HardwareArmController)
    assert isinstance(controller._serial, FakeSerialController)
    assert controller._serial.is_connected


def test_simulator_backend_builds_no_hardware_arm_controller(config):
    cfg = config.copy()
    cfg["hardware"] = {"backend": "simulator"}
    assert _build_arm_controller(cfg) is None


def test_hardware_bridge_dry_run_uses_fake_serial(config):
    cfg = config.copy()
    cfg["hardware"] = {
        "backend": "hardware",
        "dry_run": True,
        "real": {
            "port": "/dev/mock",
            "baud": 115200,
        },
        "joint_limits": [
            [-90, 90],
            [-45, 90],
            [-90, 45],
            [-90, 90],
            [-180, 180],
            [0, 80],
        ],
    }

    bridge = _build_hardware_bridge(cfg, sim=None)

    assert bridge is not None
    assert bridge.is_connected()


def test_hardware_yaml_defaults_to_simulator():
    with open("configs/hardware.yaml") as f:
        cfg = yaml.safe_load(f)
    assert cfg["hardware"]["backend"] == "simulator"


def test_agents_yaml_defaults_sim_agent_disabled():
    with open("configs/agents.yaml") as f:
        cfg = yaml.safe_load(f)

    assert cfg["agents"]["arm"]["enabled"] is True
    assert cfg["agents"]["sim_agent"]["enabled"] is False


def test_world_yaml_contains_named_zones():
    with open("configs/world.yaml") as f:
        cfg = yaml.safe_load(f)

    assert set(cfg["zones"]) >= {"zone_left", "zone_right", "bin"}
    assert cfg["zones"]["zone_left"]["x"] == [-0.8, 0.0]


def test_sim_agent_disabled_by_default_not_registered(config):
    physics_client = p.connect(p.DIRECT)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.setGravity(0, 0, -9.81)
    p.setRealTimeSimulation(0)

    try:
        orch = build_system(config)
        assert "arm" in orch.agent_registry
        assert "sim_agent" not in orch.agent_registry
    finally:
        orch.close()
        p.disconnect()


def test_sim_agent_enabled_registers_second_agent(config):
    cfg = config.copy()
    cfg["agents"] = {
        "sim_agent": {
            "type": "sim",
            "enabled": True,
            "success_rates": {
                "reach": 1.0,
                "grasp": 1.0,
                "move": 1.0,
                "release": 1.0,
                "home": 1.0,
            },
            "simulate_delays": False,
            "seed": 7,
        }
    }

    physics_client = p.connect(p.DIRECT)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.setGravity(0, 0, -9.81)
    p.setRealTimeSimulation(0)

    try:
        orch = build_system(cfg)
        from src.agents import SimAgent

        assert "arm" in orch.agent_registry
        assert "sim_agent" in orch.agent_registry
        assert isinstance(orch.agent_registry.get("sim_agent"), SimAgent)
        assert orch.agent_coordinator._cfg.max_parallel_agents == 2
        assert orch.intentos._coordinator is orch.agent_coordinator
    finally:
        orch.close()
        p.disconnect()


def test_intentos_layer_uses_gemini_timeout_ms(config):
    cfg = config.copy()
    cfg["gemini"] = {
        "enabled": True,
        "use_fake_client": True,
        "timeout_ms": 2500,
    }

    physics_client = p.connect(p.DIRECT)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.setGravity(0, 0, -9.81)
    p.setRealTimeSimulation(0)

    try:
        orch = build_system(cfg)
        assert orch.intentos is not None
        assert orch.intentos_planner._cfg.llm_enabled
        assert orch.intentos_planner._cfg.llm_timeout_s == 2.5
        assert orch.intentos_planner._gemini is not None
    finally:
        orch.close()
        p.disconnect()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
