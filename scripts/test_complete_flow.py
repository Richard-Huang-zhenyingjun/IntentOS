#!/usr/bin/env python3
"""
Complete Action Execution Diagnostic
Tests: L key → State changes → Proposal → C key → Execution
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pybullet as p
import time
from src.robot.simulator import RobotSimulator
from src.core.orchestrator import Orchestrator
from src.input.keyboard_input import KeyboardInput
from src.core.schema import DecisionSignal
from src.ui.overlay import DebugOverlay
import yaml

print("=" * 70)
print("COMPLETE ACTION EXECUTION DIAGNOSTIC")
print("=" * 70)

# Load config
try:
    with open('configs/default.yaml', 'r') as f:
        config = yaml.safe_load(f)
except:
    config = {}

# Create components
print("\n[SETUP] Creating components...")
sim = RobotSimulator(config, use_gui=True)
decision_source = KeyboardInput(config)
orch = Orchestrator(config, decision_source, sim)
overlay = DebugOverlay()

print(f"  Simulator: Robot={sim.robot_id}, Cube={sim.cube_id}")
print(f"  Initial state: {orch.state_machine.state}")

print("\n" + "=" * 70)
print("TEST SEQUENCE")
print("=" * 70)
print("\nThis will test the complete flow:")
print("  1. Press L → Should lock target and go to SELECTING")
print("  2. System → Should propose action and go to CONFIRMING")
print("  3. Press C → Should execute action")
print("\nStarting in 3 seconds...")
time.sleep(3)

# Test state
test_state = "waiting_for_l"
l_pressed_frame = None
c_pressed_frame = None
frame = 0

print("\n" + "=" * 70)
print("STEP 1: PRESS L TO LOCK TARGET")
print("=" * 70)

try:
    while True:
        frame += 1
        
        # Read keys
        keys = p.getKeyboardEvents()
        
        # === STEP 1: L KEY ===
        if test_state == "waiting_for_l":
            if ord('l') in keys and keys[ord('l')] & p.KEY_WAS_TRIGGERED:
                print(f"\n[FRAME {frame}] ✓ L KEY PRESSED")
                print(f"  Before: state={orch.state_machine.state}, target={orch.state_machine.target_id}")
                
                # Lock target
                orch.force_lock_target(sim.cube_id)
                l_pressed_frame = frame
                
                print(f"  After: state={orch.state_machine.state}, target={orch.state_machine.target_id}, locked={orch.state_machine.target_locked}")
                
                test_state = "waiting_for_proposal"
                print(f"\n{'=' * 70}")
                print(f"STEP 2: WAITING FOR SYSTEM TO PROPOSE ACTION")
                print(f"{'=' * 70}")
        
        # Cache keys
        decision_source._cached_keys = keys
        
        # Step orchestrator
        snapshot = orch.step()
        
        # Render UI overlay (show state on screen)
        overlay.render(snapshot)
        
        # === STEP 2: WAIT FOR PROPOSAL ===
        if test_state == "waiting_for_proposal":
            if snapshot.state.value == 'confirming':
                print(f"\n[FRAME {frame}] ✓ SYSTEM PROPOSED ACTION")
                print(f"  State: {snapshot.state.value}")
                print(f"  Proposal: {snapshot.proposal.action.value if snapshot.proposal else None}")
                print(f"  Reason: {snapshot.proposal.reason if snapshot.proposal else None}")
                
                test_state = "waiting_for_c"
                print(f"\n{'=' * 70}")
                print(f"STEP 3: PRESS C TO CONFIRM")
                print(f"{'=' * 70}")
            
            # Show progress every 10 frames
            if (frame - l_pressed_frame) % 10 == 0:
                print(f"[FRAME {frame}] Waiting... state={snapshot.state.value}")
        
        # === STEP 3: C KEY ===
        if test_state == "waiting_for_c":
            if ord('c') in keys and keys[ord('c')] & p.KEY_WAS_TRIGGERED:
                print(f"\n[FRAME {frame}] ✓ C KEY PRESSED")
                print(f"  Before: state={orch.state_machine.state}")
                
                c_pressed_frame = frame
                test_state = "waiting_for_execution"
                
                print(f"\n{'=' * 70}")
                print(f"STEP 4: WAITING FOR ACTION EXECUTION")
                print(f"{'=' * 70}")
        
        # === STEP 4: WAIT FOR EXECUTION ===
        if test_state == "waiting_for_execution":
            if snapshot.state.value == 'executing':
                print(f"\n[FRAME {frame}] ✓ ACTION EXECUTING")
                print(f"  State: {snapshot.state.value}")
                print(f"  Action: {snapshot.proposal.action.value if snapshot.proposal else 'None'}")
            
            elif snapshot.state.value == 'done':
                print(f"\n[FRAME {frame}] ✓ ACTION COMPLETE")
                
                test_state = "test_complete"
                print(f"\n{'=' * 70}")
                print(f"TEST COMPLETE - PRESS Q TO QUIT")
                print(f"{'=' * 70}")
            
            # Show progress every 10 frames
            if c_pressed_frame and (frame - c_pressed_frame) % 10 == 0:
                print(f"[FRAME {frame}] Executing... state={snapshot.state.value}")
        
        # Q to quit
        if ord('q') in keys and keys[ord('q')] & p.KEY_WAS_TRIGGERED:
            print(f"\n[FRAME {frame}] Q pressed, quitting...")
            break
        
        # Timeout after 600 frames (10 seconds per step)
        if test_state == "waiting_for_proposal" and l_pressed_frame and (frame - l_pressed_frame) > 600:
            print(f"\n[TIMEOUT] No proposal after 10 seconds!")
            print(f"  Current state: {snapshot.state.value}")
            print(f"  Target: {snapshot.target_id}, Locked: {snapshot.target_locked}")
            break
        
        if test_state == "waiting_for_c" and l_pressed_frame and (frame - l_pressed_frame) > 600:
            print(f"\n[TIMEOUT] Waiting too long for C key")
            print(f"  Press C to confirm!")
        
        if test_state == "waiting_for_execution" and c_pressed_frame and (frame - c_pressed_frame) > 600:
            print(f"\n[TIMEOUT] No execution after 10 seconds!")
            print(f"  Current state: {snapshot.state.value}")
            print(f"  Proposal: {snapshot.proposal}")
            break
        
        time.sleep(1.0 / 60.0)

except KeyboardInterrupt:
    print("\n\nInterrupted")

finally:
    orch.close()
    
    print("\n" + "=" * 70)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 70)
    
    if test_state == "waiting_for_l":
        print("\n❌ FAILED: L key was never pressed")
        print("   Action: Click PyBullet window and press L")
    
    elif test_state == "waiting_for_proposal":
        print("\n❌ FAILED: No proposal after pressing L")
        print("   Issue: State machine didn't transition to CONFIRMING")
        print("   Check: Planner, preconditions, world state")
    
    elif test_state == "waiting_for_c":
        print("\n⚠️  INCOMPLETE: System is waiting for C key")
        print("   Press C to continue the test")
    
    elif test_state == "waiting_for_execution":
        print("\n❌ FAILED: No execution after pressing C")
        print("   Issue: State didn't transition to EXECUTING")
        print("   Check: State machine process_decision, orchestrator")
    
    elif test_state == "test_complete":
        print("\n✅ SUCCESS: Complete flow worked!")
        print("   L → Proposal → C → Execution")
    
    print("\n" + "=" * 70)

