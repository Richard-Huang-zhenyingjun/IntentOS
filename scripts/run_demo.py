#!/usr/bin/env python3
"""Intent Interface Demo - Single Entrypoint

SELECT → PROPOSE → CONFIRM → EXECUTE

Controls:
- L: Lock target on cube
- C: Confirm proposed action
- X: Cancel
- R: Reset
- Q: Quit
"""

import sys
import argparse
import yaml
from pathlib import Path

# Add parent directory so src can be imported as a package
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
    parser = argparse.ArgumentParser(description='Intent Interface Demo')
    parser.add_argument('--config', default='configs/default.yaml', help='Config file')
    parser.add_argument('--eeg', action='store_true', help='Use EEG input (mocked)')
    parser.add_argument('--headless', action='store_true', help='Run without GUI')
    args = parser.parse_args()
    
    # Load config
    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)
    
    print("=" * 60)
    print("INTENT INTERFACE DEMO")
    print("=" * 60)
    print("\nPhilosophy: SELECT → PROPOSE → CONFIRM → EXECUTE")
    print("Safety: false_executions == 0\n")
    
    # Create simulator
    sim = RobotSimulator(config, use_gui=not args.headless)
    
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
    print("  C - Confirm action")
    print("  X - Cancel action")
    print("  R - Reset system")
    print("  Q - Quit")
    print("\nRunning...\n")
    
    try:
        while True:
            # Check keyboard for special keys (L, R, Q)
            keys = p.getKeyboardEvents()
            
            # L - Lock target
            if ord('l') in keys and keys[ord('l')] & p.KEY_WAS_TRIGGERED:
                orch.force_lock_target(sim.cube_id)
            
            # R - Reset
            if ord('r') in keys and keys[ord('r')] & p.KEY_WAS_TRIGGERED:
                orch.state_machine.reset()
                print("[DEMO] System reset")
            
            # Q - Quit
            if ord('q') in keys and keys[ord('q')] & p.KEY_WAS_TRIGGERED:
                print("\n[DEMO] Quitting...")
                break
            
            # Main loop
            snapshot = orch.step()
            
            # Render UI
            overlay.render(snapshot)
            
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

