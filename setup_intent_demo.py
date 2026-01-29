#!/usr/bin/env python3
"""
Complete setup script - Run this from Intent-Interface-Prototype directory
"""

from pathlib import Path

# Get current directory
CURRENT_DIR = Path.cwd()
print(f"Setting up demo in: {CURRENT_DIR}")
print()

# Create directories
(CURRENT_DIR / "scripts").mkdir(exist_ok=True)
(CURRENT_DIR / "configs").mkdir(exist_ok=True)
(CURRENT_DIR / "src" / "intent_core").mkdir(parents=True, exist_ok=True)
(CURRENT_DIR / "src" / "ui").mkdir(parents=True, exist_ok=True)

# Create __init__.py files
(CURRENT_DIR / "src" / "__init__.py").write_text("# Intent Interface Prototype\n")
(CURRENT_DIR / "src" / "intent_core" / "__init__.py").write_text("# Intent Core Module\n")
(CURRENT_DIR / "src" / "ui" / "__init__.py").write_text("# UI Module\n")

print("✅ Directories created")

# Create run_unified_demo.py
(CURRENT_DIR / "scripts" / "run_unified_demo.py").write_text('''#!/usr/bin/env python3
"""
Week 9 Unified Visual Demo

Single command to run complete system with visualization.
"""

import argparse
import sys
import yaml
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.intent_core.system_orchestrator import SystemOrchestrator
from src.ui.workspace_ui import WorkspaceUI

def load_config(mode: str) -> dict:
    """Load configuration for demo mode."""
    config_path = Path(__file__).parent.parent / "configs" / "default.yaml"
    
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    # Adjust based on mode
    if mode == "single":
        config["multi_user"]["num_users"] = 1
        config["fault_injection"]["enabled"] = False
    
    elif mode == "multi_user":
        config["multi_user"]["num_users"] = 2
        config["fault_injection"]["enabled"] = False
    
    elif mode == "fault_injection":
        config["multi_user"]["num_users"] = 2
        config["fault_injection"]["enabled"] = True
        config["fault_injection"]["identity_dropout_rate"] = 0.05
    
    elif mode == "full_narrative":
        config["multi_user"]["num_users"] = 2
        config["fault_injection"]["enabled"] = True
        config["fault_injection"]["identity_dropout_rate"] = 0.03
    
    return config

def run_demo(mode: str):
    """Run unified visual demo."""
    print(f"\\n{'='*70}")
    print(f"Intent Interface Prototype - Week 9 Visual Demo")
    print(f"Mode: {mode.upper()}")
    print(f"{'='*70}\\n")
    print("👁️  Watch the RIGHT PANEL to see system reasoning")
    print("📋 Timeline shows last 5 intent decisions")
    print("🔐 Authority gates show safety checks")
    print("⚠️  Red ❌ indicates why execution was blocked\\n")
    print("Starting demo...\\n")
    
    # Load config
    config = load_config(mode)
    
    # Create orchestrator
    orchestrator = SystemOrchestrator(config)
    
    # Create UI
    ui = WorkspaceUI(title=f"Intent Interface - {mode}")
    
    # Update callback
    def update_callback(dt: float):
        """Update callback for UI."""
        # Step orchestrator
        step_result = orchestrator.step()
        
        # Get UI snapshot
        ui_snapshot = orchestrator.get_ui_snapshot(step_result["timestamp"])
        
        # Update UI
        ui.update(ui_snapshot)
        
        # Console output
        if orchestrator.tick_count % 10 == 0:  # Every 10 ticks
            print(f"[{step_result['timestamp']:.1f}] {step_result['what_happened']}")
            if step_result.get('why_nothing_happened'):
                print(f"         → WHY: {step_result['why_nothing_happened']}")
    
    # Run UI
    try:
        ui.run(update_callback=update_callback, tick_ms=500)
    except KeyboardInterrupt:
        print("\\n\\nDemo stopped by user")
    
    print(f"\\n{'='*70}")
    print(f"Demo complete!")
    print(f"Total ticks: {orchestrator.tick_count}")
    print(f"{'='*70}\\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Week 9 Visual Demo - Intent Interface Prototype"
    )
    parser.add_argument(
        "--mode",
        choices=["single", "multi_user", "fault_injection", "full_narrative"],
        default="single",
        help="Demo mode to run"
    )
    
    args = parser.parse_args()
    run_demo(args.mode)
''')
print("✅ Created scripts/run_unified_demo.py")

# Create config file (continuing in next message due to length)

