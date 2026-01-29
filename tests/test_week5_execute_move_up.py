"""
Week 5 Tests: Autonomous Execution

Tests:
- Controller can start action
- Execution completes successfully
- Safety limits enforced during motion
- Cancellation works
"""

import pytest
import yaml
import sys

sys.path.insert(0, 'src')

from robotics import ArmSimulator, ArmController, ArmActionType, read_arm_state
from world import WorldModel


@pytest.fixture
def sim_world_controller():
    """Create simulator, world model, and controller."""
    with open('configs/robotics.yaml', 'r') as f:
        cfg = yaml.safe_load(f)
    cfg['scene']['use_gui'] = False
    
    # Speed up test: reduce max steps
    cfg['control']['max_steps_per_action'] = 600  # 5s instead of 10s
    
    with open('configs/robotics_test.yaml', 'w') as f:
        yaml.dump(cfg, f)
    
    sim = ArmSimulator(cfg_path='configs/robotics_test.yaml')
    sim.connect()
    sim.reset_world()
    
    world = WorldModel(cfg)
    world.update_from_sim(sim)
    
    controller = ArmController(cfg)
    
    yield sim, world, controller, cfg
    
    sim.close()
    
    import os
    os.remove('configs/robotics_test.yaml')


def test_controller_starts_move_up(sim_world_controller):
    """Test controller can start MOVE_ARM_UP action."""
    sim, world, controller, cfg = sim_world_controller
    
    # Start action
    controller.start_action(ArmActionType.MOVE_ARM_UP, world, sim)
    
    assert controller.active_action == ArmActionType.MOVE_ARM_UP
    assert controller.trajectory is not None
    assert controller.target_pos is not None


def test_move_up_execution_completes(sim_world_controller):
    """Test MOVE_ARM_UP executes to completion."""
    sim, world, controller, cfg = sim_world_controller
    
    # Record initial EE height
    initial_state = read_arm_state(sim.robot)
    initial_z = initial_state.ee_pos[2]
    
    # Start action
    controller.start_action(ArmActionType.MOVE_ARM_UP, world, sim)
    
    # Execute until done (with timeout)
    max_ticks = cfg['control']['max_steps_per_action']
    done = False
    result = None
    
    for _ in range(max_ticks):
        sim.step(n=1)
        world.update_from_sim(sim)
        done, result = controller.tick(world, sim)
        
        if done:
            break
    
    # Should complete successfully
    assert done, "Execution should complete"
    assert result is not None, "Should return result"
    assert result.success, f"Should succeed: {result.reason}"
    
    # Verify arm moved up
    final_state = read_arm_state(sim.robot)
    final_z = final_state.ee_pos[2]
    
    assert final_z > initial_z, "End effector should move up"
    assert final_z - initial_z >= 0.08, "Should lift at least 8cm (delta_z=10cm with tolerance)"


def test_execution_respects_joint_limits(sim_world_controller):
    """Test joint limits never violated during execution."""
    sim, world, controller, cfg = sim_world_controller
    
    controller.start_action(ArmActionType.MOVE_ARM_UP, world, sim)
    
    # Execute and check limits each step
    for _ in range(200):  # Check first 200 steps
        sim.step(n=1)
        world.update_from_sim(sim)
        
        arm_state = read_arm_state(sim.robot)
        
        # Check limits
        assert all(arm_state.q >= sim.robot.joint_lower - 1e-3), "Joint below lower limit"
        assert all(arm_state.q <= sim.robot.joint_upper + 1e-3), "Joint above upper limit"
        
        done, _ = controller.tick(world, sim)
        if done:
            break


def test_cancellation_stops_motion(sim_world_controller):
    """Test cancellation stops execution."""
    sim, world, controller, cfg = sim_world_controller
    
    controller.start_action(ArmActionType.MOVE_ARM_UP, world, sim)
    
    # Execute a few steps
    for _ in range(20):
        sim.step(n=1)
        world.update_from_sim(sim)
        controller.tick(world, sim)
    
    # Cancel
    controller.cancel()
    
    # Next tick should return done with failure
    done, result = controller.tick(world, sim)
    
    assert done, "Should complete after cancel"
    assert result is not None
    assert not result.success, "Should fail"
    assert "cancel" in result.reason.lower(), "Reason should mention cancellation"


def test_controller_timeout_protection(sim_world_controller):
    """Test controller times out if action takes too long."""
    sim, world, controller, cfg = sim_world_controller
    
    # Set unreachable target (modify config)
    cfg['actions']['move_up']['delta_z'] = 5.0  # Impossible height
    
    controller.start_action(ArmActionType.MOVE_ARM_UP, world, sim)
    
    # Execute until timeout
    max_steps = cfg['control']['max_steps_per_action'] + 10
    done = False
    result = None
    
    for _ in range(max_steps):
        sim.step(n=1)
        world.update_from_sim(sim)
        done, result = controller.tick(world, sim)
        
        if done:
            break
    
    # Should timeout
    assert done, "Should eventually complete (timeout)"
    assert result is not None
    assert not result.success, "Should fail due to timeout"
    assert result.steps_used >= cfg['control']['max_steps_per_action'], "Should use max steps"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])




