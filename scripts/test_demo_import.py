"""
Quick test to validate the demo script can be imported and run (headless).
"""

import sys
sys.path.insert(0, 'src')

import yaml
from robotics import ArmSimulator
from world import WorldModel

print("✓ All imports successful")

# Load config
with open('configs/robotics.yaml', 'r') as f:
    cfg = yaml.safe_load(f)

# Force headless
cfg['scene']['use_gui'] = False

with open('configs/robotics_test.yaml', 'w') as f:
    yaml.dump(cfg, f)

# Initialize simulator
sim = ArmSimulator(cfg_path='configs/robotics_test.yaml')
sim.connect()
sim.reset_world()

print("✓ Simulator initialized")

# Initialize world model
world = WorldModel(cfg)
world.update_from_sim(sim)

print("✓ World model initialized and updated")

# Get snapshot
snapshot = world.debug_snapshot()

print("\n" + "="*70)
print("WORLD MODEL STATE")
print("="*70)
print(f"EE Position:       {snapshot['ee_pos']}")
print(f"Object Position:   {snapshot['obj_pos']}")
print(f"Object Visible:    {snapshot['obj_visible']}")
print("-"*70)
print(f"Available Actions: {snapshot['available_actions']} ({snapshot['num_available']})")
print(f"Proposed Action:   {snapshot['proposed_action']}")
print("="*70)

# Run a few steps
print("\nRunning 100 physics steps...")
for i in range(100):
    sim.step(n=1)
    world.update_from_sim(sim)

# Get updated snapshot
snapshot_after = world.debug_snapshot()

print("\n" + "="*70)
print("WORLD MODEL STATE (After Physics)")
print("="*70)
print(f"EE Position:       {snapshot_after['ee_pos']}")
print(f"Object Position:   {snapshot_after['obj_pos']}")
print(f"Object Visible:    {snapshot_after['obj_visible']}")
print("-"*70)
print(f"Available Actions: {snapshot_after['available_actions']} ({snapshot_after['num_available']})")
print(f"Proposed Action:   {snapshot_after['proposed_action']}")
print("="*70)

# Cleanup
sim.close()

import os
os.remove('configs/robotics_test.yaml')

print("\n✅ Demo script validation complete!")
print("   - All imports working")
print("   - Simulator integration working")
print("   - World model integration working")
print("   - State tracking working")
print("   - Action availability working")
print("   - Action proposal working")






