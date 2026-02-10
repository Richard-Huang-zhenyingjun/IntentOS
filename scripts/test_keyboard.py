#!/usr/bin/env python3
"""
Keyboard Input Diagnostic - Tests PyBullet keyboard capture
Run this to verify keyboard input is working before testing the full demo.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pybullet as p
import pybullet_data
import time

print("=" * 70)
print("KEYBOARD INPUT DIAGNOSTIC")
print("=" * 70)

# Connect to PyBullet
print("\n[1] Connecting to PyBullet GUI...")
client = p.connect(p.GUI)
print(f"    ✓ Connected (client={client})")

# Load a simple scene
print("\n[2] Loading test scene...")
p.setAdditionalSearchPath(pybullet_data.getDataPath())
p.setGravity(0, 0, -9.81)
plane = p.loadURDF("plane.urdf")
cube = p.loadURDF("cube_small.urdf", [0, 0, 1])
print(f"    ✓ Loaded plane={plane}, cube={cube}")

print("\n" + "=" * 70)
print("KEYBOARD TEST - FOCUS THE PYBULLET WINDOW!")
print("=" * 70)
print("\nInstructions:")
print("  1. Click on the PyBullet GUI window to focus it")
print("  2. Press keys: L, C, X, R, Q")
print("  3. Watch the output below")
print("  4. Press Q to quit when done")
print("\nListening for keyboard events...")
print("-" * 70)

# Track key presses
key_count = {
    'L': 0,
    'l': 0,
    'C': 0,
    'c': 0,
    'X': 0,
    'x': 0,
    'R': 0,
    'r': 0,
    'Q': 0,
    'q': 0,
}

start_time = time.time()
last_report_time = 0

try:
    while True:
        # Step simulation
        p.stepSimulation()
        
        # Read keyboard events
        keys = p.getKeyboardEvents()
        
        # Process keys
        if keys:
            for key_code, key_state in keys.items():
                # Convert to character
                try:
                    char = chr(key_code)
                except:
                    char = f"<{key_code}>"
                
                # Check if key was pressed (not held)
                if key_state & p.KEY_WAS_TRIGGERED:
                    print(f"  ✓ KEY PRESSED: '{char}' (code={key_code}, state={key_state})")
                    
                    # Track specific keys
                    if char in key_count:
                        key_count[char] += 1
                    
                    # Quit on Q
                    if char in ['q', 'Q']:
                        print("\n[QUIT] Q key pressed, exiting...")
                        raise KeyboardInterrupt
        
        # Show elapsed time every 5 seconds
        elapsed = time.time() - start_time
        current_second = int(elapsed)
        if current_second % 5 == 0 and current_second > 0 and current_second != last_report_time:
            print(f"\n[{current_second}s] Still listening... (press Q to quit)")
            last_report_time = current_second
        
        # Small delay
        time.sleep(1.0 / 240.0)  # 240 Hz

except KeyboardInterrupt:
    print("\n" + "-" * 70)
    print("Test interrupted")

finally:
    # Disconnect
    p.disconnect()
    
    # Show summary
    print("\n" + "=" * 70)
    print("KEYBOARD TEST SUMMARY")
    print("=" * 70)
    
    total_presses = sum(key_count.values())
    
    if total_presses == 0:
        print("\n❌ NO KEYS DETECTED!")
        print("\nPossible issues:")
        print("  1. PyBullet GUI window not focused")
        print("  2. Running in headless mode (no GUI)")
        print("  3. Keyboard capture not working on your system")
        print("\nSolutions:")
        print("  - Click on the PyBullet window")
        print("  - Make sure window is visible")
        print("  - Try running without other applications capturing input")
    else:
        print(f"\n✓ Total keys detected: {total_presses}")
        print("\nKey counts:")
        for key, count in sorted(key_count.items()):
            if count > 0:
                print(f"  {key}: {count} times")
        
        # Check for specific issues
        issues = []
        
        if key_count['L'] == 0 and key_count['l'] == 0:
            issues.append("L key not detected - try pressing it")
        
        if key_count['C'] == 0 and key_count['c'] == 0:
            issues.append("C key not detected - try pressing it")
        
        # Check case sensitivity
        if key_count['L'] > 0 and key_count['l'] == 0:
            issues.append("Only uppercase L detected - case sensitivity issue?")
        elif key_count['l'] > 0 and key_count['L'] == 0:
            issues.append("Only lowercase l detected - case sensitivity issue?")
        
        if issues:
            print("\n⚠️  Issues detected:")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print("\n✓ All test keys working!")
    
    print("\n" + "=" * 70)
    print("Next steps:")
    print("  1. If keys detected → Try running the demo")
    print("  2. If no keys detected → Focus issue - click PyBullet window")
    print("  3. If only some keys work → Check key handling in demo script")
    print("=" * 70)


