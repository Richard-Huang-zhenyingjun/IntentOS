#!/usr/bin/env python3
"""
Simplified Live Camera - Direct OpenCV access
Tests camera feed without orchestrator complexity
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import cv2
import time
from intent_core.system_orchestrator import SystemOrchestrator


def main():
    print("=" * 60)
    print("LIVE CAMERA WITH DISPLAY")
    print("=" * 60)
    print("\nTesting direct camera access...\n")
    
    # Open camera directly FIRST
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("❌ Cannot open camera")
        print("\nTroubleshooting:")
        print("  1. Check if camera is connected")
        print("  2. Try different device ID: VideoCapture(1), VideoCapture(2)...")
        print("  3. Check camera permissions (System Preferences → Security)")
        return
    
    # Set camera properties
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    # Read a test frame
    ret, test_frame = cap.read()
    if not ret or test_frame is None:
        print("❌ Cannot read from camera")
        print("   Camera opened but no frames available")
        cap.release()
        return
    
    print(f"✅ Camera working!")
    print(f"   Resolution: {test_frame.shape[1]}x{test_frame.shape[0]}")
    print(f"   Channels: {test_frame.shape[2]}")
    print(f"   Dtype: {test_frame.dtype}")
    print("\nControls:")
    print("  Q - Quit")
    print("  SPACE - Pause/Resume")
    print("\n" + "-" * 60)
    
    # Now create orchestrator WITHOUT camera (we'll feed frames manually)
    config = {
        'camera': {'enabled': False},  # Don't let orchestrator open camera
        'detection': {
            'enabled': True, 
            'mode': 'contour',
            'min_confidence': 0.5,
            'min_area_pixels': 1000
        },
        'tracking': {'enabled': True},
        'affordances': {'enabled': True},
        'execution': {'enabled': False},
        'logging': {'enabled': False}  # Reduce overhead
    }
    
    print("Creating system orchestrator...")
    orch = SystemOrchestrator(config, seed=42)
    print("✅ Orchestrator ready\n")
    
    frame_count = 0
    start_time = time.time()
    paused = False
    
    try:
        while True:
            if not paused:
                # Read frame from camera
                ret, frame = cap.read()
                if not ret or frame is None:
                    print("❌ Failed to read frame")
                    break
                
                frame_count += 1
                
                # Create a copy for display
                display_frame = frame.copy()
                
                # TODO: Feed frame to orchestrator for processing
                # For now, just display the raw camera feed
                
                # Draw frame counter
                cv2.putText(display_frame, f"Frame: {frame_count}", 
                           (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                # Draw FPS
                elapsed = time.time() - start_time
                fps = frame_count / elapsed if elapsed > 0 else 0
                cv2.putText(display_frame, f"FPS: {fps:.1f}", 
                           (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                # Draw status
                cv2.putText(display_frame, "Camera Feed Active", 
                           (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                # Show frame
                cv2.imshow('Intent Interface - Live Camera', display_frame)
            else:
                # Paused - just wait
                cv2.waitKey(100)
            
            # Handle keyboard
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord(' '):
                paused = not paused
                print("\n⏸️  [PAUSED]" if paused else "\n▶️  [RESUMED]")
    
    except KeyboardInterrupt:
        print("\n\n⏹️  Interrupted")
    
    finally:
        cap.release()
        cv2.destroyAllWindows()
        
        elapsed = time.time() - start_time
        avg_fps = frame_count / elapsed if elapsed > 0 else 0
        
        print("\n" + "=" * 60)
        print("Summary:")
        print(f"  Total frames: {frame_count}")
        print(f"  Duration: {elapsed:.1f}s")
        print(f"  Average FPS: {avg_fps:.1f}")
        print("=" * 60)
        print("\n✅ Camera test complete!")


if __name__ == '__main__':
    main()






