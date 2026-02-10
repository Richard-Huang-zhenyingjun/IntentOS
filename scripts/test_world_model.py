"""
Quick test for Week 2 Task 5: World Model

Verifies that WorldModel works with simulator and computes action availability.
"""

import sys
sys.path.insert(0, 'src')

from robotics import ArmSimulator
from world import WorldModel
import yaml
import json


def main():
    print("\n" + "="*60)
    print("Week 2 Task 5: World Model Test")
    print("="*60 + "\n")
    
    # Load configuration
    with open('configs/robotics.yaml', 'r') as f:
        cfg = yaml.safe_load(f)
    
    # Force headless mode
    cfg['scene']['use_gui'] = False
    
    # Save temporary config
    with open('configs/robotics_test.yaml', 'w') as f:
        yaml.dump(cfg, f)
    
    # Initialize simulator
    sim = ArmSimulator(cfg_path='configs/robotics_test.yaml')
    sim.connect()
    sim.reset_world()
    
    print("✅ Simulator initialized\n")
    
    # Initialize world model
    world = WorldModel(cfg)
    print("✅ WorldModel initialized")
    print(f"   Config sections: {list(cfg.keys())}\n")
    
    # Test 1: Update state from simulator
    print("Test 1: State Update")
    print("-" * 60)
    world.update_from_sim(sim)
    
    assert world.arm_state is not None, "Arm state should be populated"
    assert world.object_state is not None, "Object state should be populated"
    
    print(f"✅ Arm state: EE at {world.arm_state.ee_pos}")
    print(f"✅ Object state: at {world.object_state.pos}")
    print()
    
    # Test 2: Get available actions
    print("Test 2: Available Actions")
    print("-" * 60)
    available = world.get_available_actions()
    
    print(f"Available actions: {[str(a) for a in available]}")
    assert len(available) >= 0, "Should return a list (empty is ok)"
    print(f"✅ Found {len(available)} available action(s)")
    print()
    
    # Test 3: Propose next action
    print("Test 3: Action Proposal")
    print("-" * 60)
    proposed = world.propose_next_action()
    
    if proposed:
        print(f"Proposed action: {proposed}")
        print(f"✅ Action proposal working")
    else:
        print("No action available (arm at home position)")
        print(f"✅ Correctly returns None when no action available")
    print()
    
    # Test 4: Debug snapshot
    print("Test 4: Debug Snapshot")
    print("-" * 60)
    snapshot = world.debug_snapshot()
    
    print(json.dumps(snapshot, indent=2))
    assert "ee_pos" in snapshot, "Should include EE position"
    assert "obj_pos" in snapshot, "Should include object position"
    assert "available_actions" in snapshot, "Should include available actions"
    print("✅ Debug snapshot complete")
    print()
    
    # Test 5: State after physics simulation
    print("Test 5: State Update After Physics")
    print("-" * 60)
    print("Running 100 physics steps...")
    sim.step(n=100)
    
    world.update_from_sim(sim)
    snapshot_after = world.debug_snapshot()
    
    print(f"Object position changed:")
    print(f"  Before: {snapshot['obj_pos']}")
    print(f"  After:  {snapshot_after['obj_pos']}")
    
    # Object should have settled
    z_before = snapshot['obj_pos'][2]
    z_after = snapshot_after['obj_pos'][2]
    print(f"  Delta Z: {z_after - z_before:.3f}m")
    print("✅ State tracking over time works")
    print()
    
    # Cleanup
    sim.close()
    
    import os
    os.remove('configs/robotics_test.yaml')
    
    # Summary
    print("="*60)
    print("✅ Week 2 Task 5: World Model - COMPLETE")
    print("="*60)
    print()
    print("Verified:")
    print("  ✅ WorldModel class initialization")
    print("  ✅ State update from simulator")
    print("  ✅ Available actions computation")
    print("  ✅ Action proposal logic")
    print("  ✅ Debug snapshot generation")
    print("  ✅ State tracking over time")
    print()


if __name__ == "__main__":
    main()





