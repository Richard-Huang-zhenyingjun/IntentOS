"""
Virtual Arm Demo (Legacy)
Week 1-8: Original demo script

⚠️  DEPRECATED: Use run_unified_arm_demo.py for Week 9+ demos
    python scripts/run_unified_arm_demo.py --mode happy_path

This script is maintained for backward compatibility and testing.

Usage:
  # Basic demo
  python scripts/run_virtual_arm_demo.py
  
  # With EEG
  python scripts/run_virtual_arm_demo.py --eeg --eeg-source brainlink
  
  # With scenario
  python scripts/run_virtual_arm_demo.py --scenario eeg_dropout_mid_reach --faults

For production demos, use run_unified_arm_demo.py instead.
"""

import sys
import time
import yaml
import numpy as np
import pybullet as p
import argparse

sys.path.insert(0, 'src')

from robotics import ArmSimulator
from world import WorldModel
from perception import GazeEstimator, SelectionCursor, TargetSelector
from intent_core import ArmOrchestrator
from ui import SelectionOverlay, ArmIntentOverlay
from sim import FaultInjector, get_scenario, list_scenarios
from utils.safe_pybullet import safe_get_pose


def get_mouse_cursor(sim) -> SelectionCursor:
    """Get mouse position as normalized cursor."""
    mouse_events = p.getMouseEvents()
    
    if not mouse_events:
        return SelectionCursor.from_mouse(0.5, 0.5)
    
    event = mouse_events[-1]
    x, y = event[1], event[2]
    
    width, height, _, _, _, _ = sim.get_camera_params()
    
    u = x / width if width > 0 else 0.5
    v = y / height if height > 0 else 0.5
    
    return SelectionCursor.from_mouse(u, v)


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Hybrid BCI Robot Control Demo")
    
    # EEG options
    parser.add_argument('--eeg', action='store_true',
                        help='Enable EEG decision input')
    parser.add_argument('--eeg-source', choices=['mock', 'brainlink'], default='mock',
                        help='EEG source: mock (keyboard) or brainlink (real BCI)')
    parser.add_argument('--serial-port', type=str, default='',
                        help='BrainLink serial port (empty = auto-detect)')
    
    # Gaze options
    parser.add_argument('--no-gaze', action='store_true',
                        help='Disable gaze estimation (mouse only)')
    
    # Scenario options (Week 8)
    parser.add_argument('--scenario', type=str, default=None,
                        choices=list_scenarios(),
                        help='Run pre-defined demo scenario')
    parser.add_argument('--faults', action='store_true',
                        help='Enable fault injection (used with --scenario)')
    parser.add_argument('--seed', type=int, default=42,
                        help='Fault injection random seed')
    
    return parser.parse_args()


def print_full_state(orchestrator: ArmOrchestrator, snapshot: dict):
    """Print complete system state."""
    print("\n" + "="*70)
    print("COMPLETE SYSTEM STATE")
    print("="*70)
    print(f"State Machine:     {snapshot['state']}")
    print(f"Last Event:        {snapshot['last_event']}")
    print(f"Cooldown:          {snapshot['cooldown']} frames")
    print("-"*70)
    
    if snapshot['target_locked']:
        print(f"Target:            🔒 Locked (Object {snapshot['target_id']})")
    elif snapshot['target_id'] is not None:
        print(f"Target:            👁️  Hovering (Object {snapshot['target_id']}, {snapshot['selection_hover_frames']}%)")
    else:
        print(f"Target:            None")
    
    print("-"*70)
    
    if snapshot['proposal'] is not None:
        prop = snapshot['proposal']
        print(f"Proposal:          {prop['action']}")
        print(f"Reason:            {prop['reason']}")
        print(f"Available:         {prop['available']}")
    else:
        print(f"Proposal:          None")
    
    print("-"*70)
    
    # Week 6: Grasp state
    gripper = snapshot.get('gripper_state', 'unknown')
    held = snapshot.get('held_object_id')
    if held is not None:
        print(f"Gripper:           CLOSED (holding object {held})")
    elif gripper == "closed":
        print(f"Gripper:           CLOSED (empty)")
    else:
        print(f"Gripper:           OPEN")
    
    print("-"*70)
    print(f"EE Position:       {snapshot['ee_pos']}")
    print(f"Object Position:   {snapshot['obj_pos']}")
    print("="*70)


def main():
    # Parse arguments
    args = parse_args()
    
    print("\n" + "="*70)
    print("Week 7 Demo: Hybrid BCI Robot Control with BrainLink")
    print("="*70)
    print(f"EEG Mode: {'Enabled' if args.eeg else 'Disabled'}")
    if args.eeg:
        print(f"EEG Source: {args.eeg_source}")
        if args.eeg_source == 'brainlink' and args.serial_port:
            print(f"Serial Port: {args.serial_port}")
    print("="*70 + "\n")
    
    # Load config
    with open('configs/robotics.yaml', 'r') as f:
        cfg = yaml.safe_load(f)
    
    # Override serial port if specified
    if args.serial_port:
        cfg['eeg']['brainlink']['serial_port'] = args.serial_port
    
    # Week 8: Load scenario if specified
    scenario = None
    fault_injector = None
    
    if args.scenario:
        scenario = get_scenario(args.scenario)
        print(f"\n{'='*70}")
        print(f"SCENARIO: {scenario.name}")
        print(f"{'='*70}")
        print(f"{scenario.description}")
        print(f"{'='*70}\n")
        
        if args.faults:
            fault_injector = FaultInjector(seed=args.seed, schedule=scenario.faults)
            print(f"✓ Fault injection enabled ({len(scenario.faults)} faults)")
    
    # Initialize simulator
    sim = ArmSimulator(cfg_path='configs/robotics.yaml')
    sim.connect()
    sim.reset_world()
    
    # Initialize world model
    world = WorldModel(cfg)
    world.update_from_sim(sim)
    
    # Initialize target selector (Week 3)
    selector = TargetSelector(sim, cfg)
    
    # Initialize gaze estimator (optional)
    gaze_enabled = cfg['selection']['gaze']['enabled'] and not args.no_gaze
    gaze = None
    if gaze_enabled:
        gaze = GazeEstimator(
            camera_id=cfg['selection']['gaze']['camera_id'],
            width=cfg['selection']['gaze']['width'],
            height=cfg['selection']['gaze']['height']
        )
        if gaze.start():
            print("✓ Gaze estimator started")
        else:
            print("⚠️  Gaze failed, using mouse only")
            gaze = None
            gaze_enabled = False
    
    # Initialize orchestrator (Week 7: with optional BrainLink)
    orchestrator = ArmOrchestrator(
        cfg,
        use_eeg=args.eeg,
        eeg_source=args.eeg_source if args.eeg else "mock",
        fault_injector=fault_injector
    )
    print(f"✓ Orchestrator initialized ({orchestrator.decision_source.get_source_name() if orchestrator.decision_source else 'Keyboard'})")
    
    # Initialize overlays
    selection_overlay = SelectionOverlay()
    intent_overlay = ArmIntentOverlay()
    
    # Initial step
    snapshot = orchestrator.step(sim, world, selector)
    print_full_state(orchestrator, snapshot)
    
    # Simulation loop
    print("\nStarting control loop...")
    print("Controls: C=CONFIRM, X=CANCEL, U=Unlock, G=ToggleGaze, R=Reset, ESC=Quit, D=Detail")
    print("-" * 70)
    
    frame_count = 0
    paused = False
    last_print_time = time.time()
    print_interval = 2.0
    
    # Scenario narration tracking
    narration_index = 0
    scenario_start_time = time.time() if scenario else None
    
    # Start fault injector if enabled
    if fault_injector:
        fault_injector.start(time.time())
    
    try:
        while True:
            # Check keyboard events (excluding C/X which orchestrator handles)
            keys = p.getKeyboardEvents()
            
            # Quit on ESC (65307) or Q (113)
            if 65307 in keys or 113 in keys:
                print("\n✓ User requested quit")
                break
            
            # Pause on SPACE (32)
            if 32 in keys and keys[32] & p.KEY_WAS_TRIGGERED:
                paused = not paused
                print(f"{'⏸️  Paused' if paused else '▶️  Resumed'}")
            
            # Reset on R (114)
            if 114 in keys and keys[114] & p.KEY_WAS_TRIGGERED:
                print("\n🔄 Resetting world + state machine...")
                sim.reset_world()
                world.update_from_sim(sim)
                selector.manual_unlock()
                orchestrator.reset()
                snapshot = orchestrator.step(sim, world, selector)
                print_full_state(orchestrator, snapshot)
                frame_count = 0
                last_print_time = time.time()
            
            # Unlock on U (117)
            if 117 in keys and keys[117] & p.KEY_WAS_TRIGGERED:
                print("🔓 Manual unlock")
                selector.manual_unlock()
            
            # Toggle gaze on G (103)
            if 103 in keys and keys[103] & p.KEY_WAS_TRIGGERED:
                gaze_enabled = not gaze_enabled
                print(f"{'👁️  Gaze enabled' if gaze_enabled else '🖱️  Mouse only'}")
            
            # Detailed state on D (100)
            if 100 in keys and keys[100] & p.KEY_WAS_TRIGGERED:
                print_full_state(orchestrator, snapshot)
                
                # Week 8: Print fault injector status
                if fault_injector:
                    fault_status = fault_injector.get_status(time.time())
                    print(f"\nFault Injector:")
                    print(f"  Seed: {fault_status['seed']}")
                    print(f"  Elapsed: {fault_status['elapsed']:.1f}s")
                    print(f"  Active: {fault_status['active_faults']}")
            
            # Step simulation (if not paused)
            if not paused:
                sim.step(n=1)
                frame_count += 1
                
                # Get cursor input (gaze or mouse)
                cursor = None
                if gaze_enabled and gaze is not None:
                    cursor = gaze.read_cursor()
                    confidence_threshold = cfg['selection']['gaze']['confidence_threshold']
                    if cursor and cursor.confidence < confidence_threshold:
                        cursor = None
                
                if cursor is None:
                    cursor = get_mouse_cursor(sim)
                
                # Update target selection (Week 3)
                state = selector.update(cursor)
                
                # Update orchestrator (Week 4: state machine + input)
                snapshot = orchestrator.step(sim, world, selector)
                
                # Update selection overlay (Week 3)
                selection_overlay.clear()
                if state.locked:
                    # STEP B: Get pose ONCE - validates and fetches in one call (no TOCTOU)
                    pose = safe_get_pose(state.locked_id)
                    selection_overlay.draw_lock_indicator(pose)
                elif state.current_hover_id is not None:
                    # STEP B: Get pose ONCE for hover indicator
                    hover_pose = safe_get_pose(state.current_hover_id)
                    selection_overlay.draw_hover_indicator(
                        hover_pose,
                        state.hover_frames,
                        selector.tracker.dwell_frames
                    )
                
                # Update intent overlay (Week 4)
                intent_overlay.render(snapshot)
            
            # Print status periodically
            if time.time() - last_print_time > print_interval:
                status = "PAUSED" if paused else "RUNNING"
                
                # Execution info
                exec_info = ""
                if snapshot["execution"]["active"]:
                    progress = snapshot["execution"]["progress"]
                    steps = snapshot["execution"]["steps"]
                    phase = snapshot["execution"].get("grasp_phase", "")
                    phase_str = f" [{phase}]" if phase else ""
                    exec_info = f" | Executing: {int(progress*100)}% ({steps} steps{phase_str})"
                
                # Grasp info
                grasp_info = ""
                held = snapshot.get("held_object_id")
                if held is not None:
                    grasp_info = f" | Holding: obj {held}"
                
                print(f"[{status}] Frame {frame_count:4d} | "
                      f"State: {snapshot['state']:20s}{exec_info}{grasp_info}")
                last_print_time = time.time()
                
                # Print scenario narration
                if scenario and scenario_start_time:
                    elapsed = time.time() - scenario_start_time
                    while narration_index < len(scenario.narration):
                        narr_time, narr_msg = scenario.narration[narration_index]
                        if elapsed >= narr_time:
                            print(f"\n[{elapsed:.1f}s] {narr_msg}\n")
                            narration_index += 1
                        else:
                            break
            
            # Prevent busy-wait
            time.sleep(0.001)
    
    except KeyboardInterrupt:
        print("\n✓ Interrupted by user")
    
    finally:
        if gaze is not None:
            gaze.close()
        orchestrator.close()
        sim.close()
        print("\n✓ Demo complete\n")


if __name__ == "__main__":
    main()
