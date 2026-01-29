#!/usr/bin/env python3
"""
Live Camera Demo - See Intent Interface working with real webcam

Usage:
    python scripts/run_live_camera.py
    
Controls:
    Q - Quit
    SPACE - Pause/Resume
    ESC - Exit
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import cv2
import time
from intent_core.system_orchestrator import SystemOrchestrator

def main():
    print("=" * 60)
    print("INTENT INTERFACE - LIVE CAMERA DEMO")
    print("=" * 60)
    print("\nStarting camera...")
    
    # Config with real camera
    config = {
        'camera': {
            'enabled': True,
            'mode': 'live',  # Use real camera
            'device_id': 0,   # Default webcam
            'width': 640,
            'height': 480,
            'fps': 30
        },
        'detection': {
            'enabled': True,
            'mode': 'contour',  # Use contour detection (no ML required)
            'min_confidence': 0.5,
            'min_area_pixels': 1000
        },
        'tracking': {
            'enabled': True,
            'track_max_age_frames': 10,
            'track_min_hits': 3
        },
        'focus_selection': {
            'enabled': True,
            'min_confidence': 0.5
        },
        'affordances': {
            'enabled': True,
            'max_affordance_options': 2
        },
        'gesture': {
            'enabled': False  # Disable for simple demo
        },
        'execution': {
            'enabled': False  # Safe mode for first test
        },
        'ui': {
            'enabled': True
        },
        'logging': {
            'enabled': True,
            'log_dir': 'logs'
        }
    }
    
    try:
        # Create orchestrator
        orch = SystemOrchestrator(config, seed=42)
        
        print("✅ Camera initialized!")
        print("\nControls:")
        print("  Q or ESC - Quit")
        print("  SPACE - Pause/Resume")
        print("\nLooking for objects...")
        print("-" * 60)
        
        paused = False
        frame_count = 0
        start_time = time.time()
        
        # Get camera reference from orchestrator
        if hasattr(orch, 'camera_stream') and orch.camera_stream:
            camera = orch.camera_stream
        else:
            print("❌ Camera not accessible from orchestrator")
            return
        
        while True:
            if not paused:
                # Step system
                timestamp = time.time()
                snapshot = orch.step(timestamp)
                frame_count += 1
                
                # Get and display camera frame with overlays
                if hasattr(orch, 'last_camera_frame') and orch.last_camera_frame is not None:
                    frame = orch.last_camera_frame.image.copy()
                    
                    # Draw detection boxes if available
                    if hasattr(orch, 'last_detection_result') and orch.last_detection_result:
                        for det in orch.last_detection_result.objects:
                            x, y, w, h = det.bbox
                            cv2.rectangle(frame, (int(x), int(y)), 
                                        (int(x+w), int(y+h)), (0, 255, 0), 2)
                            cv2.putText(frame, f"{det.label} {det.confidence:.2f}",
                                      (int(x), int(y-10)), cv2.FONT_HERSHEY_SIMPLEX,
                                      0.5, (0, 255, 0), 2)
                    
                    # Show state overlay at top
                    state_text = f"State: {snapshot.system_state} | Objects: {snapshot.num_tracked_objects}"
                    cv2.putText(frame, state_text, (10, 30), 
                              cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    
                    # Show focused object
                    if snapshot.scoped_object_id:
                        focus_text = f"Focused: {snapshot.scoped_object_label}"
                        cv2.putText(frame, focus_text, (10, 60), 
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                    
                    # Display frame
                    cv2.imshow('Intent Interface Camera - Press Q to quit', frame)
                
                # Print status every 30 frames (~1 second at 30fps)
                if frame_count % 30 == 0:
                    elapsed = time.time() - start_time
                    fps = frame_count / elapsed if elapsed > 0 else 0
                    
                    print(f"\n[Frame {frame_count} | FPS: {fps:.1f}]")
                    print(f"  State: {snapshot.system_state}")
                    print(f"  Objects tracked: {snapshot.num_tracked_objects}")
                    
                    if snapshot.scoped_object_id:
                        print(f"  ✓ Focused: {snapshot.scoped_object_label} "
                              f"(confidence: {snapshot.scope_confidence:.2f})")
                    
                    if snapshot.affordances_available:
                        print(f"  ✓ Actions available: {len(snapshot.affordance_options)}")
                        for i, opt in enumerate(snapshot.affordance_options[:2]):
                            print(f"     {i+1}. {opt.get('title', 'Action')}")
                    
                    if snapshot.ambiguity_detected:
                        print(f"  ⚠️  Ambiguity: {snapshot.ambiguity_reason}")
                    
                    if snapshot.paused:
                        print(f"  ⏸️  PAUSED: {snapshot.pause_reason}")
            
            # Handle keyboard input
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q') or key == 27:  # Q or ESC
                break
            elif key == ord(' '):  # SPACE
                paused = not paused
                if paused:
                    print("\n⏸️  [PAUSED] - Press SPACE to resume")
                else:
                    print("\n▶️  [RESUMED]")
    
    except KeyboardInterrupt:
        print("\n\n⏹️  Interrupted by user")
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        cv2.destroyAllWindows()
        
        # Print summary
        if frame_count > 0:
            elapsed = time.time() - start_time
            avg_fps = frame_count / elapsed if elapsed > 0 else 0
            
            print("\n" + "=" * 60)
            print("Demo Summary:")
            print(f"  Total frames: {frame_count}")
            print(f"  Duration: {elapsed:.1f}s")
            print(f"  Average FPS: {avg_fps:.1f}")
            print("=" * 60)
        
        print("\n✅ Demo complete!")

if __name__ == '__main__':
    main()

