#!/usr/bin/env python3
"""
Intent Interface Demo - DEBUG VERSION
With extensive keyboard and state debugging
"""

import sys
import argparse
import yaml
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.orchestrator import Orchestrator
from src.core.schema import UISnapshot
from src.input.keyboard_input import KeyboardInput
from src.input.eeg_source import EEGSource
from src.robot.simulator import RobotSimulator
from src.ui.overlay import DebugOverlay
import pybullet as p
import time

def main():
    parser = argparse.ArgumentParser(description='Intent Interface Demo - DEBUG')
    parser.add_argument('--config', default='configs/default.yaml', help='Config file')
    parser.add_argument('--eeg', action='store_true', help='Use EEG input (mocked)')
    parser.add_argument('--headless', action='store_true', help='Run without GUI')
    args = parser.parse_args()
    
    # Load config
    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)
    
    print("=" * 60)
    print("INTENT INTERFACE DEMO - DEBUG MODE")
    print("=" * 60)
    print("\nPhilosophy: SELECT → PROPOSE → CONFIRM → EXECUTE")
    print("Safety: false_executions == 0\n")
    
    # Create simulator
    sim = RobotSimulator(config, use_gui=not args.headless)
    print(f"\n[SETUP] Cube ID: {sim.cube_id}")
    print(f"[SETUP] Cube valid: {sim.is_valid_object(sim.cube_id)}")
    
    # Create input source
    if args.eeg:
        decision_source = EEGSource(config, mock_mode=True)
        print("Input: EEG (mocked - keyboard still active)\n")
    else:
        decision_source = KeyboardInput(config)
        print("Input: Keyboard (C=confirm, X=cancel)\n")
    
    # Create orchestrator
    orch = Orchestrator(config, decision_source, sim)
    
    # Create UI
    overlay = DebugOverlay()
    
    print("Controls:")
    print("  L - Lock target (cube)")
    print("  C - Confirm action (only works when proposal exists!)")
    print("  X - Cancel action")
    print("  R - Reset system")
    print("  Q - Quit")
    print("\n" + "=" * 60)
    print("IMPORTANT: Click on PyBullet window to focus it!")
    print("=" * 60)
    print("\nRunning...\n")
    
    frame = 0
    last_state = None
    
    try:
        while True:
            frame += 1
            
            # Main orchestrator step (reads C/X keys)
            snapshot = orch.step()
            
            # Debug: Show state changes
            if snapshot.state != last_state:
                print(f"\n[STATE] {last_state} → {snapshot.state.value}")
                last_state = snapshot.state
            
            # Debug: Show proposal
            if snapshot.proposal:
                print(f"[PROPOSAL] {snapshot.proposal.action.value}: {snapshot.proposal.reason}")
            
            # Now read L/R/Q keys (after orchestrator)
            keys = p.getKeyboardEvents()
            
            # DEBUG: Show any keys detected
            if keys:
                key_chars = [chr(k) for k in keys.keys() if 32 <= k <= 126]
                if key_chars:
                    print(f"[KEYS] Detected: {', '.join(key_chars)}")
            
            # L - Lock target
            if ord('l') in keys and keys[ord('l')] & p.KEY_WAS_TRIGGERED:
                print(f"\n[L KEY] Pressed! Locking cube {sim.cube_id}")
                if sim.cube_id is not None:
                    orch.force_lock_target(sim.cube_id)
                    print(f"[L KEY] ✓ Lock command sent")
                else:
                    print(f"[L KEY] ✗ No cube to lock!")
            
            # Also check uppercase L
            if ord('L') in keys and keys[ord('L')] & p.KEY_WAS_TRIGGERED:
                print(f"\n[L KEY] Uppercase L pressed! Locking cube {sim.cube_id}")
                if sim.cube_id is not None:
                    orch.force_lock_target(sim.cube_id)
                    print(f"[L KEY] ✓ Lock command sent")
                else:
                    print(f"[L KEY] ✗ No cube to lock!")
            
            # R - Reset
            if ord('r') in keys and keys[ord('r')] & p.KEY_WAS_TRIGGERED:
                print("\n[R KEY] Reset pressed")
                orch.state_machine.reset()
                print("[R KEY] ✓ System reset")
            
            # Q - Quit
            if ord('q') in keys and keys[ord('q')] & p.KEY_WAS_TRIGGERED:
                print("\n[Q KEY] Quit pressed, exiting...")
                break
            
            # Render UI
            overlay.render(snapshot)
            
            # Debug: Show state summary every 60 frames (1 second)
            if frame % 60 == 0:
                print(f"\n[FRAME {frame}] State: {snapshot.state.value}, "
                      f"Target: {snapshot.target_id}, "
                      f"Locked: {snapshot.target_locked}, "
                      f"Proposal: {snapshot.proposal is not None}")
            
            # CRITICAL: Check false executions
            if snapshot.false_executions > 0:
                print(f"\n❌ CRITICAL: FALSE EXECUTION DETECTED!")
                print(f"   Total: {snapshot.false_executions}")
                print(f"   This should NEVER happen!\n")
            
            # Sleep to maintain frame rate
            time.sleep(1.0 / 60.0)  # 60 FPS
    
    except KeyboardInterrupt:
        print("\n[DEMO] Interrupted")
    
    finally:
        orch.close()
        print("\n[DEMO] Cleanup complete")
        print("=" * 60)

if __name__ == "__main__":
    main()



