#!/usr/bin/env python3
"""
Main demo entry point.
Week 3: Uses system factory for clean assembly.

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

from src.core.diag import print_startup_banner
from src.core.system_factory import build_system
from src.core.schema import UISnapshot
from src.input.keyboard_input import KeyboardInput
from src.ui.overlay import DebugOverlay
import pybullet as p
import time


def main():
    print_startup_banner()
    
    parser = argparse.ArgumentParser(description='Intent Interface Demo')
    parser.add_argument('--config', default='configs/default.yaml', help='Config file')
    parser.add_argument('--headless', action='store_true', help='Run without GUI')
    args = parser.parse_args()
    
    # Load config
    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)
    
    # Week 3: Set GUI mode in config (factory will use it)
    if args.headless:
        config['simulator'] = config.get('simulator', {})
        config['simulator']['use_gui'] = False
    
    print("=" * 60)
    print("INTENT INTERFACE DEMO - Week 3")
    print("=" * 60)
    print("\nPhilosophy: SELECT → PROPOSE → CONFIRM → EXECUTE")
    print("Safety: false_executions == 0")
    print("Week 3: Using system factory for dependency injection\n")
    
    # Week 3: Build system (all wiring happens here)
    orch = build_system(config)
    
    # Warning: Focus PyBullet window
    if not args.headless:
        print("\n" + "=" * 60)
        print("⚠️  IMPORTANT: CLICK ON PYBULLET WINDOW TO ACTIVATE IT!")
        print("=" * 60)
        print("\nWaiting 3 seconds for you to click the window...")
        time.sleep(3)
        print("Starting demo...\n")
    
    # Create UI
    overlay = DebugOverlay()
    
    print("Controls:")
    print("  L - Lock target (cube)")
    print("  C - Confirm action")
    print("  X - Cancel action")
    print("  R - Reset system")
    print("  Q - Quit")
    print("\nRunning...\n")
    
    frame = 0
    try:
        while True:
            frame += 1
            # CRITICAL FIX: Read keys ONCE per frame to avoid buffer clearing issue
            # p.getKeyboardEvents() clears the buffer after reading, so we must:
            # 1. Read keys ONCE
            # 2. Extract C/X for orchestrator decision
            # 3. Use same keys dict for L/R/Q controls
            
            # CRITICAL FIX: Read keys ONCE per frame
            # p.getKeyboardEvents() clears the buffer, so reading twice loses keys
            # Solution: Read once, pass to KeyboardInput, then use for L/R/Q
            keys = p.getKeyboardEvents()  # Read ONCE per frame
            
            # DEBUG: Show what keys were detected
            if keys:
                key_chars = [chr(k) for k in keys.keys() if 32 <= k <= 126]
                print(f"[DEBUG FRAME] Keys detected: {key_chars}")
                print(f"[DEBUG FRAME] L key code {ord('l')} in keys: {ord('l') in keys}")
                if ord('l') in keys:
                    print(f"[DEBUG FRAME] L key state: {keys[ord('l')]}, TRIGGERED: {keys[ord('l')] & p.KEY_WAS_TRIGGERED}")
            
            # DEBUG: Show all keyboard events detected
            if keys:
                print(f"\n[KEYBOARD DEBUG] Keys detected: {len(keys)} key(s)")
                for key_code, key_state in keys.items():
                    try:
                        char = chr(key_code)
                        if char.isprintable():
                            char_repr = f"'{char}'"
                        else:
                            char_repr = f"<non-printable>"
                    except:
                        char_repr = "<invalid>"
                    
                    # Decode key state flags
                    state_flags = []
                    if key_state & p.KEY_WAS_TRIGGERED:
                        state_flags.append("TRIGGERED")
                    if key_state & p.KEY_IS_DOWN:
                        state_flags.append("DOWN")
                    if key_state & p.KEY_WAS_RELEASED:
                        state_flags.append("RELEASED")
                    
                    state_str = " | ".join(state_flags) if state_flags else f"state={key_state}"
                    
                    print(f"  [KEYBOARD DEBUG]   Key code {key_code} ({char_repr}): {state_str}")
                
                # Specifically check for L key
                l_lower = ord('l')
                l_upper = ord('L')
                if l_lower in keys:
                    print(f"  [KEYBOARD DEBUG]   ✓ Lowercase 'l' detected!")
                if l_upper in keys:
                    print(f"  [KEYBOARD DEBUG]   ✓ Uppercase 'L' detected!")
            else:
                # Only print empty message occasionally to avoid spam
                if frame % 300 == 0:  # Every 5 seconds at 60fps
                    print(f"[KEYBOARD DEBUG] No keys detected (frame {frame})")
            
            # Pass keys to KeyboardInput (if it's a KeyboardInput instance)
            # This prevents KeyboardInput from reading again and clearing buffer
            if isinstance(decision_source, KeyboardInput):
                # Temporarily store keys for KeyboardInput to use
                decision_source._cached_keys = keys
            
            snapshot = orch.step()  # KeyboardInput will use cached keys
            
            # Handle L - Lock target (case-insensitive)
            print(f"[DEBUG L] Checking L key condition...")
            print(f"  ord('l') = {ord('l')}")
            print(f"  ord('l') in keys = {ord('l') in keys}")
            if ord('l') in keys:
                print(f"  keys[ord('l')] = {keys[ord('l')]}")
                print(f"  p.KEY_WAS_TRIGGERED = {p.KEY_WAS_TRIGGERED}")
                print(f"  keys[ord('l')] & p.KEY_WAS_TRIGGERED = {keys[ord('l')] & p.KEY_WAS_TRIGGERED}")
            
            l_pressed = (ord('l') in keys and keys[ord('l')] & p.KEY_WAS_TRIGGERED) or \
                        (ord('L') in keys and keys[ord('L')] & p.KEY_WAS_TRIGGERED)
            
            print(f"[DEBUG L] l_pressed = {l_pressed}")
            
            if l_pressed:
                print(f"[DEBUG L] >>> INSIDE L KEY HANDLER!")
                # Week 3: Use world_artifacts from orchestrator
                if orch.world_artifacts and len(orch.world_artifacts.object_ids) > 0:
                    target_id = orch.world_artifacts.object_ids[0]
                    print(f"[DEBUG L] >>> Calling force_lock_target({target_id})")
                    orch.force_lock_target(target_id)
                else:
                    print(f"[DEBUG L] >>> No objects in world_artifacts!")
            
            # Handle R - Reset
            if ord('r') in keys and keys[ord('r')] & p.KEY_WAS_TRIGGERED:
                orch.state_machine.reset()
                print("[DEMO] System reset")
            
            # Handle Q - Quit
            print(f"[DEBUG Q] Checking Q key condition...")
            print(f"  ord('q') in keys = {ord('q') in keys}")
            if ord('q') in keys:
                print(f"  keys[ord('q')] = {keys[ord('q')]}")
                print(f"  keys[ord('q')] & p.KEY_WAS_TRIGGERED = {keys[ord('q')] & p.KEY_WAS_TRIGGERED}")
            
            if ord('q') in keys and keys[ord('q')] & p.KEY_WAS_TRIGGERED:
                print(f"[DEBUG Q] >>> QUITTING")
                print("\n[DEMO] Quitting...")
                break
            
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

