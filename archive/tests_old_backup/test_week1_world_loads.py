"""
Week 1 Test: Validate world loading and state reading.

Tests:
- PyBullet connection (DIRECT mode for speed)
- World reset (plane, table, object, robot)
- Robot model metadata
- State reading (joints, EE pose, object pose)
"""

import pytest
import numpy as np
import pybullet as p
import sys

sys.path.insert(0, 'src')

from robotics import ArmSimulator, read_arm_state


@pytest.fixture
def simulator():
    """Create simulator in DIRECT mode for testing."""
    # Temporarily override config to use DIRECT mode
    import yaml
    with open('configs/robotics.yaml', 'r') as f:
        cfg = yaml.safe_load(f)
    
    # Force DIRECT mode for tests
    cfg['scene']['use_gui'] = False
    
    # Save temporary config
    with open('configs/robotics_test.yaml', 'w') as f:
        yaml.dump(cfg, f)
    
    sim = ArmSimulator(cfg_path='configs/robotics_test.yaml')
    sim.connect()
    sim.reset_world()
    
    yield sim
    
    sim.close()
    
    # Cleanup
    import os
    os.remove('configs/robotics_test.yaml')


def test_connection(simulator):
    """Test PyBullet connection is active."""
    assert simulator._connected, "Simulator should be connected"
    assert simulator.physics_client is not None, "Physics client should exist"


def test_world_bodies_loaded(simulator):
    """Test all world bodies are loaded."""
    assert simulator.plane_id is not None, "Plane should be loaded"
    assert simulator.plane_id >= 0, "Plane ID should be valid"
    
    assert simulator.table_id is not None, "Table should be loaded"
    assert simulator.table_id >= 0, "Table ID should be valid"
    
    assert simulator.object_id is not None, "Object should be loaded"
    assert simulator.object_id >= 0, "Object ID should be valid"
    
    assert simulator.robot is not None, "Robot should be loaded"
    assert simulator.robot.body_id >= 0, "Robot body ID should be valid"


def test_robot_model_metadata(simulator):
    """Test robot model has correct metadata."""
    robot = simulator.robot
    
    assert robot.num_joints > 0, "Robot should have controllable joints"
    assert len(robot.joint_indices) == robot.num_joints, "Joint indices length mismatch"
    assert len(robot.joint_lower) == robot.num_joints, "Joint limits length mismatch"
    assert len(robot.joint_upper) == robot.num_joints, "Joint limits length mismatch"
    assert len(robot.joint_names) == robot.num_joints, "Joint names length mismatch"
    
    # Check limits are valid
    assert np.all(robot.joint_lower < robot.joint_upper), "Joint limits should be valid"
    
    # Check EE link is valid
    assert robot.ee_link_index >= 0, "EE link index should be valid"
    assert robot.ee_link_name, "EE link name should not be empty"


def test_arm_state_reading(simulator):
    """Test reading arm state."""
    state = read_arm_state(simulator.robot)
    
    assert state.num_joints == simulator.robot.num_joints, "Joint count mismatch"
    assert state.q.shape == (simulator.robot.num_joints,), "Joint angles shape mismatch"
    assert state.dq.shape == (simulator.robot.num_joints,), "Joint velocities shape mismatch"
    assert state.ee_pos.shape == (3,), "EE position should be 3D"
    assert state.ee_orn.shape == (4,), "EE orientation should be quaternion"
    
    # Check values are finite
    assert np.all(np.isfinite(state.q)), "Joint angles should be finite"
    assert np.all(np.isfinite(state.dq)), "Joint velocities should be finite"
    assert np.all(np.isfinite(state.ee_pos)), "EE position should be finite"
    assert np.all(np.isfinite(state.ee_orn)), "EE orientation should be finite"


def test_object_pose_reading(simulator):
    """Test reading object pose."""
    pos, orn = simulator.get_object_pose()
    
    assert pos.shape == (3,), "Object position should be 3D"
    assert orn.shape == (4,), "Object orientation should be quaternion"
    assert np.all(np.isfinite(pos)), "Object position should be finite"
    assert np.all(np.isfinite(orn)), "Object orientation should be finite"


def test_physics_stepping(simulator):
    """Test physics simulation can step."""
    # Get initial object height
    pos_before, _ = simulator.get_object_pose()
    z_before = pos_before[2]
    
    # Step simulation (gravity should affect object minimally since it's on table)
    simulator.step(n=100)
    
    pos_after, _ = simulator.get_object_pose()
    z_after = pos_after[2]
    
    # Object should settle to correct height on table
    # Expected: table_height (0.6) + cube_radius (0.02) = 0.62m
    expected_z = 0.62
    assert abs(z_after - expected_z) < 0.01, f"Object should settle at {expected_z}m (table + radius)"
    
    # Also verify it settled downward (started too high at 0.65)
    assert z_after < z_before, "Object should have settled down due to gravity"


def test_joint_limits_respected(simulator):
    """Test joint angles are within limits."""
    state = read_arm_state(simulator.robot)
    robot = simulator.robot
    
    # Initial configuration should be within limits
    assert np.all(state.q >= robot.joint_lower - 0.01), "Joints below lower limit"
    assert np.all(state.q <= robot.joint_upper + 0.01), "Joints above upper limit"


if __name__ == "__main__":
    # Allow running directly
    pytest.main([__file__, "-v"])
