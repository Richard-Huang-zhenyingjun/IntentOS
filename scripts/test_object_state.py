"""
Quick test for Week 2 Task 1: Object State Module

Verifies that ObjectState and read_object_state() work with Week 1 simulator.
"""

import sys
sys.path.insert(0, 'src')

from robotics import ArmSimulator
from perception import ObjectState, read_object_state
import numpy as np


def main():
    print("\n" + "="*60)
    print("Week 2 Task 1: Object State Module Test")
    print("="*60 + "\n")
    
    # Initialize simulator (headless mode)
    import yaml
    with open('configs/robotics.yaml', 'r') as f:
        cfg = yaml.safe_load(f)
    cfg['scene']['use_gui'] = False
    
    with open('configs/robotics_test.yaml', 'w') as f:
        yaml.dump(cfg, f)
    
    sim = ArmSimulator(cfg_path='configs/robotics_test.yaml')
    sim.connect()
    sim.reset_world()
    
    print("✅ Simulator initialized\n")
    
    # Test 1: Read initial object state
    print("Test 1: Reading initial object state")
    print("-" * 60)
    obj_state = read_object_state(sim.object_id)
    print(obj_state)
    print()
    
    # Verify state
    assert isinstance(obj_state, ObjectState), "Should return ObjectState"
    assert obj_state.object_id == sim.object_id, "Object ID mismatch"
    assert obj_state.pos.shape == (3,), "Position should be 3D"
    assert obj_state.orn.shape == (4,), "Orientation should be quaternion"
    assert obj_state.lin_vel.shape == (3,), "Linear velocity should be 3D"
    assert obj_state.ang_vel.shape == (3,), "Angular velocity should be 3D"
    assert obj_state.visible == True, "Should be visible in Week 2"
    print("✅ All assertions passed\n")
    
    # Test 2: Object state after physics
    print("Test 2: Object state after physics simulation")
    print("-" * 60)
    print(f"Initial position: {np.round(obj_state.pos, 3)}")
    
    sim.step(n=100)  # Run physics
    
    obj_state_after = read_object_state(sim.object_id)
    print(f"After 100 steps: {np.round(obj_state_after.pos, 3)}")
    print(f"Position change: {np.round(obj_state_after.pos - obj_state.pos, 4)}")
    print(f"Linear velocity: {np.round(obj_state_after.lin_vel, 4)}")
    print()
    
    # Object should have settled (minimal velocity)
    assert np.linalg.norm(obj_state_after.lin_vel) < 0.01, "Object should be nearly stationary"
    print("✅ Physics settling verified\n")
    
    # Test 3: Verify state matches legacy method
    print("Test 3: Compare with Week 1 legacy method")
    print("-" * 60)
    legacy_pos, legacy_orn = sim.get_object_pose()
    
    np.testing.assert_allclose(obj_state_after.pos, legacy_pos, rtol=1e-5)
    np.testing.assert_allclose(obj_state_after.orn, legacy_orn, rtol=1e-5)
    
    print(f"ObjectState pos: {np.round(obj_state_after.pos, 3)}")
    print(f"Legacy pos:      {np.round(legacy_pos, 3)}")
    print("✅ Legacy compatibility verified\n")
    
    # Cleanup
    sim.close()
    
    import os
    os.remove('configs/robotics_test.yaml')
    
    # Summary
    print("="*60)
    print("✅ Week 2 Task 1: Object State Module - COMPLETE")
    print("="*60)
    print()
    print("Verified:")
    print("  ✅ ObjectState dataclass working")
    print("  ✅ read_object_state() reads pose, velocity, visibility")
    print("  ✅ Integration with Week 1 simulator")
    print("  ✅ Physics state tracking accurate")
    print("  ✅ Legacy compatibility maintained")
    print()


if __name__ == "__main__":
    main()





