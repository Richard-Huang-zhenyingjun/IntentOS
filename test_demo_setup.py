#!/usr/bin/env python3
"""
Test script to verify demo setup before running.
Run this first to check for issues.
"""

import sys
from pathlib import Path

print("="*70)
print("DEMO SETUP VERIFICATION")
print("="*70)
print()

errors = []

# Check 1: Verify we're in the right directory
print("1. Checking directory structure...")
required_files = [
    "scripts/run_unified_demo.py",
    "configs/default.yaml",
    "src/intent_core/system_orchestrator.py",
    "src/ui/intent_visualizer.py",
    "src/ui/workspace_ui.py",
]

for file_path in required_files:
    if Path(file_path).exists():
        print(f"   ✅ {file_path}")
    else:
        print(f"   ❌ {file_path} - MISSING")
        errors.append(f"Missing file: {file_path}")

print()

# Check 2: Python version
print("2. Checking Python version...")
version = sys.version_info
print(f"   Python {version.major}.{version.minor}.{version.micro}")
if version.major < 3 or (version.major == 3 and version.minor < 7):
    print("   ⚠️  Python 3.7+ recommended")
else:
    print("   ✅ Python version OK")

print()

# Check 3: Required modules
print("3. Checking required modules...")

try:
    import yaml
    print("   ✅ yaml (PyYAML)")
except ImportError:
    print("   ❌ yaml (PyYAML) - MISSING")
    print("      Install with: pip install pyyaml")
    errors.append("Missing module: yaml (install with: pip install pyyaml)")

try:
    import tkinter
    print("   ✅ tkinter")
except ImportError:
    print("   ❌ tkinter - MISSING")
    print("      On Mac: Usually included with Python")
    print("      On Linux: sudo apt-get install python3-tk")
    errors.append("Missing module: tkinter")

try:
    import argparse
    print("   ✅ argparse (built-in)")
except ImportError:
    print("   ❌ argparse - MISSING (should be built-in)")
    errors.append("Missing module: argparse")

print()

# Check 4: Import our modules
print("4. Checking project imports...")
sys.path.insert(0, str(Path.cwd()))

try:
    from src.intent_core.system_orchestrator import SystemOrchestrator
    print("   ✅ SystemOrchestrator")
except ImportError as e:
    print(f"   ❌ SystemOrchestrator - {e}")
    errors.append(f"Import error: SystemOrchestrator - {e}")

try:
    from src.ui.workspace_ui import WorkspaceUI
    print("   ✅ WorkspaceUI")
except ImportError as e:
    print(f"   ❌ WorkspaceUI - {e}")
    errors.append(f"Import error: WorkspaceUI - {e}")

try:
    from src.ui.intent_visualizer import IntentVisualizer
    print("   ✅ IntentVisualizer")
except ImportError as e:
    print(f"   ❌ IntentVisualizer - {e}")
    errors.append(f"Import error: IntentVisualizer - {e}")

print()

# Check 5: Config file
print("5. Checking config file...")
try:
    import yaml
    with open("configs/default.yaml") as f:
        config = yaml.safe_load(f)
    print(f"   ✅ Config loaded ({len(config)} sections)")
except Exception as e:
    print(f"   ❌ Config error - {e}")
    errors.append(f"Config error: {e}")

print()

# Summary
print("="*70)
if errors:
    print("❌ SETUP ISSUES FOUND:")
    for error in errors:
        print(f"   • {error}")
    print()
    print("Fix the issues above, then run:")
    print("   python scripts/run_unified_demo.py --mode full_narrative")
else:
    print("✅ ALL CHECKS PASSED!")
    print()
    print("Ready to run the demo:")
    print("   python scripts/run_unified_demo.py --mode full_narrative")
print("="*70)

