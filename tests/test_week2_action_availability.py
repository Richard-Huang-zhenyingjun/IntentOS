"""
Week 2 Tests: World Model + Action Availability

Tests:
- World model state updates
- Action availability computation
- Action proposal logic
- Precondition checks
"""

import pytest
import yaml
import sys

sys.path.insert(0, 'src')

from robotics import ArmSimulator
from world import WorldModel
from robotics.action_types import ArmActionType


@pytest.fixture
def sim_and_world():
    """Create simulator and world model in DIRECT mode."""
    # Force DIRECT mode
    with open('configs/robotics.yaml', 'r') as f:
        cfg = yaml.safe_load(f)
    cfg['scene']['use_gui'] = False
    
    with open('configs/robotics_test.yaml', 'w') as f:
        yaml.dump(cfg, f)
    
    sim = ArmSimulator(cfg_path='configs/robotics_test.yaml')
    sim.connect()
    sim.reset_world()
    
    world = WorldModel(cfg)
    world.update_from_sim(sim)
    
    yield sim, world
    
    sim.close()
    
    import os
    os.remove('configs/robotics_test.yaml')


def test_world_model_updates(sim_and_world):
    """Test world model can update from simulator."""
    sim, world = sim_and_world
    
    world.update_from_sim(sim)
    
    assert world.arm_state is not None, "Arm state should be updated"
    assert world.object_state is not None, "Object state should be updated"
    assert world.arm_state.ee_pos.shape == (3,), "EE position should be 3D"
    assert world.object_state.pos.shape == (3,), "Object position should be 3D"


def test_get_available_actions_returns_list(sim_and_world):
    """Test get_available_actions returns a list."""
    sim, world = sim_and_world
    
    available = world.get_available_actions()
    
    assert isinstance(available, list), "Should return a list"
    assert all(isinstance(a, ArmActionType) for a in available), "All items should be ArmActionType"


def test_propose_next_action_returns_valid_type(sim_and_world):
    """Test propose_next_action returns valid action or None."""
    sim, world = sim_and_world
    
    proposed = world.propose_next_action()
    
    assert proposed is None or isinstance(proposed, ArmActionType), \
        "Should return ArmActionType or None"


def test_proposed_action_is_available(sim_and_world):
    """Test proposed action is in available actions list."""
    sim, world = sim_and_world
    
    available = world.get_available_actions()
    proposed = world.propose_next_action()
    
    if proposed is not None:
        assert proposed in available, "Proposed action must be available"


def test_all_actions_are_known(sim_and_world):
    """Test available actions are subset of known actions."""
    sim, world = sim_and_world
    
    available = world.get_available_actions()
    known_actions = list(ArmActionType)
    
    for action in available:
        assert action in known_actions, f"Unknown action: {action}"


def test_debug_snapshot_has_expected_keys(sim_and_world):
    """Test debug snapshot contains expected fields."""
    sim, world = sim_and_world
    
    snapshot = world.debug_snapshot()
    
    expected_keys = [
        'ee_pos', 'obj_pos', 'obj_visible',
        'available_actions', 'proposed_action', 'num_available'
    ]
    
    for key in expected_keys:
        assert key in snapshot, f"Missing key in snapshot: {key}"


def test_state_updates_after_sim_step(sim_and_world):
    """Test world model tracks simulator state changes."""
    sim, world = sim_and_world
    
    # Get initial state
    world.update_from_sim(sim)
    initial_ee = world.arm_state.ee_pos.copy()
    
    # Step simulation
    sim.step(n=10)
    
    # Update world model
    world.update_from_sim(sim)
    current_ee = world.arm_state.ee_pos
    
    # States should be trackable (might be same if no motion, but finite)
    assert current_ee.shape == initial_ee.shape, "State shape should remain consistent"
    assert all(abs(current_ee) < 100), "EE position should be reasonable"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])




