#!/usr/bin/env python3
"""
Create all demo files in Intent-Interface-Prototype directory
"""

import os
from pathlib import Path

TARGET_DIR = Path("/Users/richardhuang/Intent-Interface-Prototype")

print(f"Creating demo files in: {TARGET_DIR}")
print()

# Create directories
(TARGET_DIR / "scripts").mkdir(parents=True, exist_ok=True)
(TARGET_DIR / "configs").mkdir(parents=True, exist_ok=True)
(TARGET_DIR / "src" / "intent_core").mkdir(parents=True, exist_ok=True)
(TARGET_DIR / "src" / "ui").mkdir(parents=True, exist_ok=True)

# Create __init__.py files
(TARGET_DIR / "src" / "__init__.py").write_text("# Intent Interface Prototype\n")
(TARGET_DIR / "src" / "intent_core" / "__init__.py").write_text("# Intent Core Module\n")
(TARGET_DIR / "src" / "ui" / "__init__.py").write_text("# UI Module\n")

print("✅ Directories and __init__.py files created")

# Read files from workspace and write to target
workspace_root = Path(__file__).parent

files_to_copy = [
    ("scripts/run_unified_demo.py", TARGET_DIR / "scripts" / "run_unified_demo.py"),
    ("configs/default.yaml", TARGET_DIR / "configs" / "default.yaml"),
    ("src/intent_core/system_orchestrator.py", TARGET_DIR / "src" / "intent_core" / "system_orchestrator.py"),
    ("src/intent_core/logger.py", TARGET_DIR / "src" / "intent_core" / "logger.py"),
    ("src/ui/intent_visualizer.py", TARGET_DIR / "src" / "ui" / "intent_visualizer.py"),
    ("src/ui/workspace_ui.py", TARGET_DIR / "src" / "ui" / "workspace_ui.py"),
    ("src/ui/camera_overlay.py", TARGET_DIR / "src" / "ui" / "camera_overlay.py"),
]

for source_rel, target in files_to_copy:
    source = workspace_root / source_rel
    if source.exists():
        target.write_text(source.read_text())
        print(f"✅ Created {target.relative_to(TARGET_DIR)}")
    else:
        print(f"⚠️  Source not found: {source_rel}")

# Make script executable
script_path = TARGET_DIR / "scripts" / "run_unified_demo.py"
if script_path.exists():
    os.chmod(script_path, 0o755)
    print(f"✅ Made script executable")

print()
print("="*70)
print("Setup complete!")
print("="*70)
print()
print(f"Now run:")
print(f"  cd {TARGET_DIR}")
print(f"  python scripts/run_unified_demo.py --mode full_narrative")
print()

