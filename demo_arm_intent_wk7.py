"""
Demo: Arm Intent Interface with BrainLink Lite EEG
Week 7: Real BCI integration with robust decision strategy.

Usage:
    # Run with BrainLink (auto-detects or falls back to MockEEG):
    python demo_arm_intent_wk7.py --eeg brainlink

    # Run with MockEEG (keyboard C/X):
    python demo_arm_intent_wk7.py --eeg mock

    # Run with keyboard only (no EEG):
    python demo_arm_intent_wk7.py

Features:
    - BrainLink Lite serial communication
    - Robust decision strategy (windowing, majority vote, cooldown)
    - Signal quality monitoring
    - EEG stability gates
    - Automatic PAUSED state on signal loss
    - Full transparency (EEG metrics, stability, confidence)
"""

import sys
import os
sys.path.insert(0, 'src')

import argparse
import yaml
import pybullet as p
import time

from robotics import ArmSimulator
from world import WorldModel
from intent_core import ArmOrchestrator
from ui import ArmIntentOverlay, SelectionOverlay
from perception import TargetSelector


def main():
    """Run Week 7 demo."""
    # Parse arguments
    parser = argparse.ArgumentParser(description="Week 7: BrainLink EEG Demo")
    parser.add_argument('--eeg', type=str, default='none',
                       choices=['brainlink', 'mock', 'none'],
                       help='EEG source: brainlink (real hardware), mock (keyboard), none (keyboard only)')
    parser.add_argument('--config', type=str, default='configs/robotics.yaml',
                       help='Config file path')
    parser.add_argument('--fps', type=int, default=30,
                       help='Simulation FPS')
    args = parser.parse_args()
    
    # Load config
    with open(args.config, 'r') as f:
        cfg = yaml.safe_load(f)
    
    print("=" * 60)
    print("Week 7: BrainLink Lite EEG Integration Demo")
    print("=" * 60)
    print()
    
    # Initialize PyBullet
    print("Initializing PyBullet...")
    client_id = p.connect(p.GUI)
    p.setGravity(0, 0, -9.81)
    p.setRealTimeSimulation(0)
    
    # Create components
    print("Creating components...")
    sim = ArmSimulator(cfg, debug=False)
    world = WorldModel(cfg)
    
    # Initialize orchestrator with EEG source
    use_eeg = args.eeg != 'none'
    eeg_source = args.eeg if use_eeg else 'mock'
    orchestrator = ArmOrchestrator(cfg, use_eeg=use_eeg, eeg_source=eeg_source)
    
    overlay = ArmIntentOverlay()
    selector = TargetSelector(cfg)
    selection_overlay = SelectionOverlay()
    
    # Camera setup
    p.resetDebugVisualizerCamera(
        cameraDistance=1.5,
        cameraYaw=45,
        cameraPitch=-30,
        cameraTargetPosition=[0.3, 0.0, 0.2]
    )
    
    print()
    print("=" * 60)
    print("DEMO STARTED")
    print("=" * 60)
    print()
    print("Instructions:")
    print("  - Look at an object for ~0.6s to lock target")
    print("  - System proposes actions automatically")
    
    if args.eeg == 'brainlink':
        print("  - Concentrate (high attention) to CONFIRM")
        print("  - Relax (low attention) to CANCEL")
        print("  - OR use keyboard: C=CONFIRM, X=CANCEL")
    elif args.eeg == 'mock':
        print("  - C = CONFIRM action")
        print("  - X = CANCEL action")
    else:
        print("  - C = CONFIRM action")
        print("  - X = CANCEL action")
    
    print()
    print("Watch for:")
    print("  - EEG STATUS panel (if using BrainLink/Mock)")
    print("  - Signal stability indicators")
    print("  - PAUSED state on signal loss")
    print("  - Cooldown periods between decisions")
    print()
    print("Press Ctrl+C to exit")
    print("=" * 60)
    print()
    
    # Main loop
    frame_time = 1.0 / args.fps
    last_status_print = time.time()
    frame_count = 0
    
    try:
        while True:
            start_time = time.time()
            
            # Update selector (gaze tracking)
            selector.update()
            
            # Step orchestrator
            ui_snapshot = orchestrator.step(sim, world, selector)
            
            # Render overlays
            overlay.render(ui_snapshot)
            
            # Show selection state
            if ui_snapshot["target_locked"]:
                selection_overlay.draw_locked_indicator(ui_snapshot["target_id"])
            elif ui_snapshot["target_id"] is not None:
                dwell_frames = 18  # From config
                selection_overlay.draw_hover_indicator(
                    ui_snapshot["target_id"],
                    ui_snapshot["selection_hover_frames"],
                    dwell_frames
                )
            
            # Step simulation
            p.stepSimulation()
            
            # Print status every 5 seconds
            frame_count += 1
            if time.time() - last_status_print > 5.0:
                print(f"[{frame_count:6d}] State: {ui_snapshot['state']:20s} | Target: {ui_snapshot['target_id']} | Decision Source: {ui_snapshot['decision_source']}")
                
                # Print EEG status if available
                if ui_snapshot.get('eeg') and ui_snapshot['eeg'].get('connected'):
                    eeg = ui_snapshot['eeg']
                    features = eeg.get('features', {})
                    att = features.get('attention', 0)
                    stable_str = "STABLE" if eeg.get('stable') else f"UNSTABLE ({eeg.get('reason', 'unknown')})"
                    conf = eeg.get('confidence', 0.0) * 100
                    print(f"          EEG: Attention={att:.0f}, Status={stable_str}, Confidence={conf:.0f}%")
                
                last_status_print = time.time()
            
            # Throttle to target FPS
            elapsed = time.time() - start_time
            if elapsed < frame_time:
                time.sleep(frame_time - elapsed)
    
    except KeyboardInterrupt:
        print()
        print("=" * 60)
        print("DEMO STOPPED")
        print("=" * 60)
        print()
        print("Statistics:")
        print(f"  Total frames: {frame_count}")
        print(f"  Runtime: {frame_count * frame_time:.1f}s")
        print(f"  Final state: {ui_snapshot['state']}")
        
        if ui_snapshot.get('eeg') and ui_snapshot['eeg'].get('connected'):
            eeg = ui_snapshot['eeg']
            print()
            print("EEG Status:")
            print(f"  Source: {ui_snapshot['decision_source']}")
            print(f"  Last signal: {eeg.get('last_signal', 'IDLE')}")
            print(f"  Confidence: {eeg.get('confidence', 0.0) * 100:.0f}%")
        
        print()
        print("Thank you for testing Week 7!")
        print("=" * 60)
    
    finally:
        # Cleanup
        if hasattr(orchestrator, 'decision_source') and orchestrator.decision_source:
            orchestrator.decision_source.close()
        p.disconnect()


if __name__ == "__main__":
    main()

