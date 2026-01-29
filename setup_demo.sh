#!/bin/bash
# Setup script to create demo files in Intent-Interface-Prototype directory

TARGET_DIR="/Users/richardhuang/Intent-Interface-Prototype"

echo "Setting up demo files in: $TARGET_DIR"
echo ""

# Create directories
mkdir -p "$TARGET_DIR/scripts"
mkdir -p "$TARGET_DIR/configs"
mkdir -p "$TARGET_DIR/src/intent_core"
mkdir -p "$TARGET_DIR/src/ui"

echo "✅ Directories created"

# Copy files (we'll create them inline since we can't copy from workspace)
cat > "$TARGET_DIR/scripts/run_unified_demo.py" << 'DEMO_EOF'
#!/usr/bin/env python3
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
    print(f"\n{'='*70}")
    print(f"Intent Interface Prototype - Week 9 Visual Demo")
    print(f"Mode: {mode.upper()}")
    print(f"{'='*70}\n")
    print("👁️  Watch the RIGHT PANEL to see system reasoning")
    print("📋 Timeline shows last 5 intent decisions")
    print("🔐 Authority gates show safety checks")
    print("⚠️  Red ❌ indicates why execution was blocked\n")
    print("Starting demo...\n")
    
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
        print("\n\nDemo stopped by user")
    
    print(f"\n{'='*70}")
    print(f"Demo complete!")
    print(f"Total ticks: {orchestrator.tick_count}")
    print(f"{'='*70}\n")

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
DEMO_EOF

chmod +x "$TARGET_DIR/scripts/run_unified_demo.py"
echo "✅ Created scripts/run_unified_demo.py"

# Create config file
cat > "$TARGET_DIR/configs/default.yaml" << 'CONFIG_EOF'
# Intent Interface Prototype - Configuration
# Week 9 Visual Demo

seed: 42

# State machine settings
state_machine:
  confidence_threshold: 0.7
  scope_timeout_seconds: 5.0
  adaptive_dwell_enabled: true
  baseline_dwell_ms: 500
  min_dwell_ms: 200
  max_dwell_ms: 1000

# Confidence tracker settings
confidence_tracker:
  consistency_threshold: 0.6
  window_seconds: 1.5
  ema_alpha: 0.3
  decay_rate: 0.1

# Multi-object settings (Week 6)
multi_object:
  enabled: true
  max_candidates: 10
  ambiguity_threshold: 0.2
  focus_commit_cooldown_ms: 500

# Multi-user settings (Week 7)
multi_user:
  enabled: true
  num_users: 2
  min_attribution_confidence: 0.85
  allow_shared_objects: false
  lock_ttl_seconds: 2.0

# Fault injection (for stress testing, Week 8)
fault_injection:
  enabled: false
  seed: 42
  identity_dropout_rate: 0.01
  misattribution_rate: 0.01
  lock_loss_rate: 0.01
  oscillation_burst_rate: 0.01
  confidence_collapse_rate: 0.01

# Recovery settings (Week 8)
recovery:
  enabled: true
  min_attribution_confidence: 0.85
  pause_on_identity_drop: true
  pause_on_lock_loss: true
  pause_on_ambiguity_in_confirming: true
  pause_on_oscillation: true
  pause_on_confidence_collapse: true

# Undo settings (Week 8)
undo:
  enabled: true
  undo_window_seconds: 10.0

# Simulator settings
simulator:
  noise_level: 0.3
  select_rate: 0.1
  confirm_rate: 0.05

# Narrative logging (Week 9)
narrative:
  enabled: true
  log_dir: data/narratives

# UI settings (Week 9 Final Polish)
ui:
  window_width: 1200
  window_height: 600
  panel_width: 400
CONFIG_EOF

echo "✅ Created configs/default.yaml"

# Create __init__.py files
touch "$TARGET_DIR/src/__init__.py"
touch "$TARGET_DIR/src/intent_core/__init__.py"
touch "$TARGET_DIR/src/ui/__init__.py"
echo "✅ Created __init__.py files"

echo ""
echo "=========================================="
echo "Setup complete! Now creating Python files..."
echo "=========================================="
echo ""
echo "Run this Python script to create the remaining files:"
echo "  python create_demo_files.py"
echo ""

