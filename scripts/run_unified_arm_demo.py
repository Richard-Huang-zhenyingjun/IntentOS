

#!/usr/bin/env python3
"""
Unified Arm Demo Runner
Week 9: Production-ready demonstration system.

Usage:
    # Happy path (normal operation)
    python scripts/run_unified_arm_demo.py --mode happy_path
    
    # Safety refusal (blocking unsafe actions)
    python scripts/run_unified_arm_demo.py --mode safety_refusal --eeg --eeg-source mock
    
    # Recovery demonstration
    python scripts/run_unified_arm_demo.py --mode recovery --eeg --eeg-source mock --faults
    
    # Full 5-minute narrative
    python scripts/run_unified_arm_demo.py --mode full_narrative --eeg --eeg-source mock
    
    # Real BrainLink
    python scripts/run_unified_arm_demo.py --mode happy_path --eeg --eeg-source brainlink
"""

import sys
import argparse
import yaml
import time
import pybullet as p
import tempfile
import os
from typing import Optional

sys.path.insert(0, 'src')

from robotics import ArmSimulator
from robotics.arm_simulator import is_valid_body
from utils.safe_pybullet import safe_debug_text, safe_get_pose
from world import WorldModel
from perception import TargetSelector, GazeEstimator, SelectionCursor
from intent_core import ArmOrchestrator, ArmUISnapshot
from intent_core.arm_intent_schema import ArmDecision, DecisionSignal, ArmUIState
from ui import SelectionOverlay, ArmIntentOverlay
from sim import FaultInjector, DemoMode, get_mode_config, get_mode_scenario, list_demo_modes


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Unified Arm Demo Runner (Week 9)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # Demo mode
    parser.add_argument('--mode', type=str, default='happy_path',
                        choices=list_demo_modes(),
                        help='Demo mode to run')
    
    # EEG options
    parser.add_argument('--eeg', action='store_true',
                        help='Enable EEG input (BrainLink or Mock)')
    parser.add_argument('--eeg-source', type=str, default='mock',
                        choices=['brainlink', 'mock'],
                        help='EEG source (requires --eeg)')
    
    # Gaze tracking
    parser.add_argument('--no-gaze', action='store_true',
                        help='Disable gaze tracking (mouse only)')
    
    # Fault injection
    parser.add_argument('--faults', action='store_true',
                        help='Enable fault injection (if mode supports it)')
    parser.add_argument('--seed', type=int, default=42,
                        help='Random seed for fault injection')
    
    # Session
    parser.add_argument('--session-id', type=str, default=None,
                        help='Custom session ID (auto-generated if not provided)')
    
    # Output
    parser.add_argument('--no-metrics', action='store_true',
                        help='Disable metrics export')
    
    return parser.parse_args()


def print_controls():
    """Print control instructions."""
    print("\n" + "="*70)
    print("CONTROLS")
    print("="*70)
    print("Q       - Quit")
    print("C       - Confirm action (keyboard mode)")
    print("X       - Cancel / Undo")
    print("U       - Unlock target")
    print("R       - Reset system")
    print("D       - Print detailed state")
    print("V       - Reset camera view (PATCH 5)")
    print("L       - Force lock cube (STEP 2 diagnostic)")
    print("SPACE   - Pause/Resume")
    print("="*70 + "\n")


def main():
    """Main demo loop."""
    args = parse_args()
    
    # Load base config
    cfg_path = 'configs/robotics.yaml'
    with open(cfg_path, 'r') as f:
        cfg = yaml.safe_load(f)
    
    # Get mode-specific config
    mode = DemoMode(args.mode)
    cfg = get_mode_config(mode, cfg)
    
    # Get scenario (if mode has one)
    scenario = get_mode_scenario(mode)
    
    # Override metrics export
    if args.no_metrics:
        cfg['demo']['save_metrics'] = False
    
    # Ensure GUI mode is enabled (config defaults to true)
    # Can be overridden by config file setting
    if 'use_gui' not in cfg.get('scene', {}):
        cfg.setdefault('scene', {})['use_gui'] = True
    
    # Write temporary config for simulator
    temp_cfg_fd, temp_cfg_path = tempfile.mkstemp(suffix='.yaml', text=True)
    with os.fdopen(temp_cfg_fd, 'w') as f:
        yaml.dump(cfg, f)
    
    # Print mode banner
    print("\n" + "="*70)
    print(f"DEMO MODE: {mode.value.upper()}")
    print("="*70)
    if mode == DemoMode.HAPPY_PATH:
        print("Normal operation - gaze select → EEG confirm → grasp object")
    elif mode == DemoMode.SAFETY_REFUSAL:
        print("Safety demonstration - system blocks unsafe actions")
    elif mode == DemoMode.RECOVERY:
        print("Recovery workflow - pause → recover from faults")
    elif mode == DemoMode.FULL_NARRATIVE:
        print("Complete 5-minute walkthrough with narration")
    print("="*70 + "\n")
    
    # Create fault injector if enabled
    fault_injector = None
    if args.faults and scenario:
        fault_injector = FaultInjector(seed=args.seed, schedule=scenario.faults)
        print(f"✓ Fault injection enabled ({len(scenario.faults)} faults, seed={args.seed})")
    
    # Initialize simulator
    sim = ArmSimulator(temp_cfg_path)
    sim.connect()
    sim.reset_world()
    
    # Initialize world model
    world = WorldModel(cfg)
    
    # Initialize target selector
    selector = TargetSelector(sim, cfg)
    
    # Initialize gaze estimator (optional)
    use_gaze = not args.no_gaze
    gaze_estimator = None
    
    if use_gaze:
        gaze_estimator = GazeEstimator()
        if not gaze_estimator.start():
            print("⚠️  Gaze tracking failed, falling back to mouse")
            use_gaze = False
            gaze_estimator = None
    
    # Initialize overlays
    selection_overlay = SelectionOverlay()
    intent_overlay = ArmIntentOverlay()
    
    # Initialize orchestrator
    orchestrator = ArmOrchestrator(
        cfg,
        use_eeg=args.eeg,
        eeg_source=args.eeg_source if args.eeg else "mock",
        fault_injector=fault_injector,
        session_id=args.session_id
    )
    
    print_controls()
    
    # Scenario narration tracking
    narration_index = 0
    scenario_start_time = time.time() if scenario else None
    
    # Start fault injector if enabled
    if fault_injector:
        fault_injector.start(time.time())
    
    frame_count = 0
    paused = False
    last_status_print = time.time()
    status_print_interval = 2.0
    
    # FIX 4: Compensated frame limiting
    target_fps = 60  # Increased from 30 for smoother animation
    target_frame_time = 1.0 / target_fps
    
    # PATCH 3: Input echo - track key press display
    key_echo_id: Optional[int] = None
    key_echo_time: float = 0.0
    KEY_ECHO_DURATION = 1.0  # Show for 1 second
    
    # Layer 3: Visual feedback for forced lock (reusable debug text)
    debug_text_id: Optional[int] = None
    
    # Key code to name mapping
    KEY_NAMES = {
        99: "CONFIRM (C)",
        120: "CANCEL (X)",
        117: "UNLOCK (U)",
        114: "RESET (R)",
        100: "DETAIL (D)",
        113: "QUIT (Q)",
        32: "PAUSE (SPACE)",
        65307: "QUIT (ESC)",
        118: "VIEW (V)",  # PATCH 5: Camera reset
        108: "LOCK (L)",  # STEP 2: Force target lock
    }
    
    def get_key_name(key_code: int) -> str:
        """Get human-readable key name."""
        if key_code in KEY_NAMES:
            return KEY_NAMES[key_code]
        elif 32 <= key_code <= 126:  # Printable ASCII
            return f"'{chr(key_code)}'"
        else:
            return f"Key {key_code}"
    
    try:
        while True:
            # === HEARTBEAT: Prove loop is alive ===
            if frame_count % 30 == 0:  # Every 30 frames (~1 second at 60 FPS)
                print(f"[HEARTBEAT] Frame {frame_count} - Loop is running")
            
            # FIX 4: Start frame timing
            frame_start = time.time()
            
            # Get cursor input (gaze or mouse)
            cursor = None
            if use_gaze and gaze_estimator:
                cursor = gaze_estimator.read_cursor()
                if cursor and cursor.confidence < cfg['selection']['gaze']['confidence_threshold']:
                    cursor = None
            
            # Fall back to mouse if gaze not available
            # Note: Using getMouseEvents() consumes events, which prevents camera controls
            # For now, use center of screen as default cursor position
            # User can still control camera with trackpad/mouse gestures
            if cursor is None:
                # Use screen center as default (allows camera control to work)
                # In a real implementation, you'd use a non-consuming method or separate selection mode
                cursor = SelectionCursor.from_mouse(0.5, 0.5)
            
            # FIX 1: Orchestrator step FIRST (applies forced lock if pending)
            # Orchestrator reads C/X keys internally via confirm_input.read()
            print(f"[MAIN] About to call orchestrator.step()")
            snapshot = orchestrator.step(sim, world, selector)
            print(f"[MAIN] orchestrator.step() returned")
            print(f"[MAIN] Snapshot state: {snapshot.state}")
            print(f"[MAIN] Snapshot proposal: {snapshot.proposed_action}")
            
            # === NUCLEAR TEST: Force confirm if C detected ===
            nuclear_keys = p.getKeyboardEvents()
            if (ord('c') in nuclear_keys and nuclear_keys[ord('c')] & p.KEY_WAS_TRIGGERED) or \
               (ord('C') in nuclear_keys and nuclear_keys[ord('C')] & p.KEY_WAS_TRIGGERED) or \
               (99 in nuclear_keys and nuclear_keys[99] & p.KEY_WAS_TRIGGERED):
                print(f"\n[NUCLEAR] C KEY DETECTED, FORCING STATE MACHINE CONFIRM")
                print(f"  Current state: {orchestrator.state_machine.state}")
                print(f"  Active proposal: {orchestrator.state_machine.active_proposal}")
                
                if orchestrator.state_machine.state == ArmUIState.AWAITING_CONFIRM:
                    print(f"[NUCLEAR] Creating fake CONFIRM decision and re-ticking")
                    fake_decision = ArmDecision.from_keyboard(DecisionSignal.CONFIRM)
                    orchestrator.state_machine.tick(world, fake_decision, orchestrator.controller)
                    print(f"[NUCLEAR] After force tick, state: {orchestrator.state_machine.state}")
                else:
                    print(f"[NUCLEAR] State is {orchestrator.state_machine.state}, not AWAITING_CONFIRM - skipping")
            
            # Phase 1 Fix: Don't update selector if ANYTHING is locked (normal or forced)
            # This prevents auto-unlock countdown from starting
            current_state = selector.tracker.get_state()
            if current_state.locked:
                # Already locked - don't run update (which would start unlock countdown)
                selection_state = current_state
            else:
                # Not locked - run normal update (raycast, dwell detection, etc.)
                selection_state = selector.update(cursor)
            
            # Render selection overlay
            # STEP B: Get pose ONCE - validates and fetches in one call (no TOCTOU)
            if selection_state.locked and isinstance(selection_state.locked_id, int):
                # Get pose ONCE - validates and fetches in one call (no TOCTOU)
                pose = safe_get_pose(selection_state.locked_id)
                
                if pose is None:
                    # Object invalid - queue self-heal (deferred to frame boundary)
                    print(f"[RENDER] ⚠️ Object {selection_state.locked_id} no longer exists, requesting global unlock")
                    orchestrator.request_global_unlock("render_invalid_body", selection_state.locked_id)
                else:
                    # Pose valid - render using validated pose
                    selection_overlay.draw_lock_indicator(pose)
            elif selection_state.current_hover_id is not None:
                # Get pose ONCE for hover indicator
                hover_pose = safe_get_pose(selection_state.current_hover_id)
                selection_overlay.draw_hover_indicator(
                    hover_pose,
                    selection_state.hover_frames,
                    cfg['selection']['dwell_frames']
                )
            else:
                # STEP 0 FIX: Clear indicators when no selection (methods handle clearing)
                # Just call with None to trigger clearing in the methods
                selection_overlay.draw_hover_indicator(None, 0, 1)
            
            # Render intent overlay (pass p module, not client ID)
            intent_overlay.render(p, snapshot)
            
            # Step physics
            sim.step()
            
            # FIX: Read keyboard AFTER orchestrator.step() so orchestrator can read C/X keys first
            # orchestrator.step() calls confirm_input.read() which reads C/X keys internally
            # Main loop reads keys here for OTHER keys (Q, U, R, D, SPACE, V, L, P) that are handled in main loop
            keys = p.getKeyboardEvents()
            
            # PATCH 3: Input echo - show every key press
            for key_code, key_state in keys.items():
                if key_state & p.KEY_WAS_TRIGGERED:
                    key_name = get_key_name(key_code)
                    key_echo_time = time.time()
                    
                    # Display key press on screen (center-top)
                    echo_text = f"🔔 KEY PRESSED: {key_name}"
                    position = (0.0, 0.0, 1.1)
                    
                    # STEP D: Use safe debug text wrapper for consistency
                    key_echo_id = safe_debug_text(
                        text=echo_text,
                        position=position,
                        color=(1.0, 1.0, 0.0),  # Bright yellow
                        size=1.5,
                        lifetime=0,
                        replace_id=key_echo_id
                    )
                    break  # Only show first triggered key per frame
            
            # Clear key echo after duration
            if key_echo_id is not None and time.time() - key_echo_time > KEY_ECHO_DURATION:
                try:
                    p.removeUserDebugItem(key_echo_id)
                except:
                    pass
                key_echo_id = None
            
            # Q = Quit
            if ord('q') in keys and keys[ord('q')] & p.KEY_WAS_TRIGGERED:
                print("\nQuitting...")
                break
            
            # U = Unlock (Phase 2: Clear forced lock if present)
            if ord('u') in keys and keys[ord('u')] & p.KEY_WAS_TRIGGERED:
                # STEP C: Use deferred self-heal mechanism for consistency
                orchestrator.request_global_unlock("manual_unlock", None)
                print("[KEY] U -> Unlock requested (will execute at frame boundary)")
            
            # R = Reset
            if ord('r') in keys and keys[ord('r')] & p.KEY_WAS_TRIGGERED:
                orchestrator.reset()
                print("System reset")
            
            # D = Detailed state
            if ord('d') in keys and keys[ord('d')] & p.KEY_WAS_TRIGGERED:
                print("\n" + "="*70)
                print("DETAILED STATE")
                print("="*70)
                print(f"State: {snapshot.state}")
                print(f"Target: {snapshot.locked_object_id}")
                print(f"Proposal: {snapshot.proposed_action}")
                print("="*70)
            
            # SPACE = Pause/Resume
            if ord(' ') in keys and keys[ord(' ')] & p.KEY_WAS_TRIGGERED:
                paused = not paused
                print(f"{'⏸️  Paused' if paused else '▶️  Resumed'}")
            
            # PATCH 5: V = Camera reset (view)
            if ord('v') in keys and keys[ord('v')] & p.KEY_WAS_TRIGGERED:
                p.resetDebugVisualizerCamera(
                    cameraDistance=1.5,
                    cameraYaw=45,
                    cameraPitch=-30,
                    cameraTargetPosition=[0, 0, 0.5]
                )
                print("Camera reset to default view")
            
            # STEP 2: L = Force target lock (diagnostic hack)
            # STEP B4: Validate using safe wrapper (validates + fetches in one call)
            if ord('l') in keys and keys[ord('l')] & p.KEY_WAS_TRIGGERED:
                cube_id = sim.object_id
                
                # Validate using safe wrapper
                pose = safe_get_pose(cube_id)
                
                if pose is None:
                    # Invalid or missing object
                    print("[FORCE LOCK] ❌ No valid cube object in scene")
                    debug_text_id = safe_debug_text(
                        text="❌ No valid cube",
                        position=(0.5, 0.0, 1.0),
                        color=(1, 0, 0),
                        size=1.5,
                        lifetime=2.0,
                        replace_id=debug_text_id
                    )
                else:
                    # Valid object - queue forced lock (pass selector for idempotency check)
                    orchestrator.force_lock_target(cube_id, selector=selector)
                    debug_text_id = safe_debug_text(
                        text=f"✅ Lock queued: cube {cube_id}",
                        position=(0.5, 0.0, 1.0),
                        color=(0, 1, 0),
                        size=1.5,
                        lifetime=1.0,
                        replace_id=debug_text_id
                    )
            
            # P = Force PLACE action (if holding object)
            if ord('p') in keys and keys[ord('p')] & p.KEY_WAS_TRIGGERED:
                print("\n[KEY] P -> FORCE PLACE")
                
                # Check if holding object
                if world.is_holding_any():
                    # Check if controller is not already active
                    if not orchestrator.controller.is_active():
                        try:
                            from robotics.action_types import ArmActionType
                            orchestrator.controller.start_action(ArmActionType.PLACE_OBJECT, world, sim)
                            print("[KEY] PLACE action started")
                            debug_text_id = safe_debug_text(
                                text="✅ PLACE action started",
                                position=(0.5, 0.0, 1.0),
                                color=(0, 1, 0),
                                size=1.5,
                                lifetime=1.0,
                                replace_id=debug_text_id
                            )
                        except ValueError as e:
                            print(f"[KEY] Cannot start PLACE: {e}")
                            debug_text_id = safe_debug_text(
                                text=f"❌ Cannot place: {str(e)[:20]}",
                                position=(0.5, 0.0, 1.0),
                                color=(1, 0, 0),
                                size=1.5,
                                lifetime=2.0,
                                replace_id=debug_text_id
                            )
                    else:
                        print("[KEY] P pressed but controller already active")
                        debug_text_id = safe_debug_text(
                            text="❌ Action already in progress",
                            position=(0.5, 0.0, 1.0),
                            color=(1, 0, 0),
                            size=1.5,
                            lifetime=2.0,
                            replace_id=debug_text_id
                        )
                else:
                    print("[KEY] P pressed but not holding any object")
                    debug_text_id = safe_debug_text(
                        text="❌ Not holding object",
                        position=(0.5, 0.0, 1.0),
                        color=(1, 0, 0),
                        size=1.5,
                        lifetime=2.0,
                        replace_id=debug_text_id
                    )
            
            # Print status periodically
            now = time.time()
            if not paused and now - last_status_print > status_print_interval:
                print(f"[{frame_count:4d}] State: {snapshot.state:20s} | Target: {snapshot.locked_object_id or 'None'}")
                last_status_print = now
            
            # Scenario narration
            if scenario and scenario_start_time:
                elapsed = time.time() - scenario_start_time
                while narration_index < len(scenario.narration):
                    narr_time, narr_msg = scenario.narration[narration_index]
                    if elapsed >= narr_time:
                        print(f"\n[{elapsed:.1f}s] {narr_msg}\n")
                        narration_index += 1
                    else:
                        break
            
            frame_count += 1
            
            # FIX 4: Compensated frame limiting (replaces fixed sleep)
            if not paused:
                frame_elapsed = time.time() - frame_start
                sleep_time = max(0.001, target_frame_time - frame_elapsed)
                time.sleep(sleep_time)
    
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    
    finally:
        # Cleanup
        print("\nCleaning up...")
        
        orchestrator.close()
        
        if gaze_estimator:
            gaze_estimator.stop()
        
        sim.close()
        
        # Remove temporary config file
        if os.path.exists(temp_cfg_path):
            os.unlink(temp_cfg_path)
        
        print("✓ Demo complete")


if __name__ == "__main__":
    main()
