"""
Week 5 Tests: IK Solver and Safety Limits

Tests:
- IK solver returns valid joint angles
- Joint limits respected
- Safety clamping functions
- Pose error computation
"""

import pytest
import yaml
import numpy as np
import sys

sys.path.insert(0, 'src')

from robotics import (
    ArmSimulator, solve_ik, clamp_joint_targets, 
    within_limits, compute_pose_error
)


@pytest.fixture
def sim():
    """Create simulator in DIRECT mode."""
    with open('configs/robotics.yaml', 'r') as f:
        cfg = yaml.safe_load(f)
    cfg['scene']['use_gui'] = False
    
    with open('configs/robotics_test.yaml', 'w') as f:
        yaml.dump(cfg, f)
    
    sim = ArmSimulator(cfg_path='configs/robotics_test.yaml')
    sim.connect()
    sim.reset_world()
    
    yield sim
    
    sim.close()
    
    import os
    os.remove('configs/robotics_test.yaml')


def test_ik_solver_returns_valid_joints(sim):
    """Test IK solver returns joint angles within limits."""
    # Target above table
    target_pos = np.array([0.3, 0.0, 0.7])
    
    q_solution = solve_ik(sim.robot, target_pos)
    
    assert q_solution.shape == (sim.robot.num_joints,)
    assert within_limits(q_solution, sim.robot.joint_lower, sim.robot.joint_upper)


def test_ik_solver_respects_joint_limits(sim):
    """Test IK solutions always within joint limits."""
    # Try multiple targets
    targets = [
        np.array([0.4, 0.1, 0.6]),
        np.array([0.3, -0.1, 0.7]),
        np.array([0.5, 0.0, 0.65]),
    ]
    
    for target_pos in targets:
        q_solution = solve_ik(sim.robot, target_pos)
        assert within_limits(q_solution, sim.robot.joint_lower, sim.robot.joint_upper), \
            f"IK solution violates limits for target {target_pos}"


def test_clamp_joint_targets():
    """Test joint limit clamping."""
    q = np.array([0.0, 2.0, -3.0])  # Some outside limits
    lower = np.array([-1.0, -1.0, -1.0])
    upper = np.array([1.0, 1.0, 1.0])
    
    q_clamped = clamp_joint_targets(q, lower, upper)
    
    assert within_limits(q_clamped, lower, upper)
    assert np.allclose(q_clamped, [0.0, 1.0, -1.0])


def test_within_limits_detection():
    """Test within_limits correctly detects violations."""
    lower = np.array([0.0, 0.0])
    upper = np.array([1.0, 1.0])
    
    assert within_limits(np.array([0.5, 0.5]), lower, upper)
    assert within_limits(np.array([0.0, 1.0]), lower, upper)  # Boundary
    assert not within_limits(np.array([1.5, 0.5]), lower, upper)  # Above
    assert not within_limits(np.array([0.5, -0.5]), lower, upper)  # Below


def test_compute_pose_error():
    """Test pose error computation."""
    current = np.array([0.0, 0.0, 0.0])
    target = np.array([0.03, 0.04, 0.0])  # 5cm away
    
    pos_err, _ = compute_pose_error(current, target)
    
    assert abs(pos_err - 0.05) < 1e-6  # 3-4-5 triangle


def test_ik_with_current_seed(sim):
    """Test IK uses current joint angles as seed."""
    from robotics import read_arm_state
    
    target_pos = np.array([0.35, 0.0, 0.65])
    
    # Get current state
    arm_state = read_arm_state(sim.robot)
    
    # Solve IK with seed
    q_solution = solve_ik(sim.robot, target_pos, current_q=arm_state.q)
    
    assert q_solution.shape == (sim.robot.num_joints,)
    assert within_limits(q_solution, sim.robot.joint_lower, sim.robot.joint_upper)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])




