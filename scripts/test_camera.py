#!/usr/bin/env python3
"""
Camera Test - Verify your webcam is accessible

This is a simple test to check if OpenCV can access your camera
before running the full demo.

Usage:
    python scripts/test_camera.py
"""

import cv2
import sys

def test_camera(device_id=0):
    """Test if camera is accessible"""
    print("=" * 60)
    print("CAMERA TEST")
    print("=" * 60)
    print(f"\nTrying to open camera {device_id}...")
    
    # Try to open camera
    cap = cv2.VideoCapture(device_id)
    
    if not cap.isOpened():
        print(f"❌ ERROR: Could not open camera {device_id}")
        print("\nTroubleshooting:")
        print("  1. Check if camera is connected")
        print("  2. Check if another app is using the camera")
        print("  3. Try a different device_id (0, 1, 2...)")
        print("  4. On macOS: System Preferences → Security & Privacy → Camera")
        return False
    
    # Get camera properties
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    
    print(f"✅ Camera opened successfully!")
    print(f"\nCamera Info:")
    print(f"  Resolution: {width}x{height}")
    print(f"  FPS: {fps}")
    
    # Try to read a frame
    print("\nReading test frame...")
    ret, frame = cap.read()
    
    if not ret or frame is None:
        print("❌ ERROR: Could not read frame from camera")
        cap.release()
        return False
    
    print(f"✅ Frame captured: {frame.shape}")
    
    # Show preview
    print("\nShowing preview window...")
    print("Press any key to close...")
    
    cv2.imshow('Camera Test - Press any key to close', frame)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    
    cap.release()
    
    print("\n" + "=" * 60)
    print("✅ CAMERA TEST PASSED!")
    print("=" * 60)
    print("\nYou can now run the live camera demo:")
    print("  python scripts/run_live_camera.py")
    
    return True

def main():
    # Test default camera
    success = test_camera(0)
    
    if not success:
        print("\nWould you like to try a different camera? (y/n): ", end="")
        response = input().strip().lower()
        
        if response == 'y':
            print("Enter device ID (e.g., 1, 2, 3): ", end="")
            try:
                device_id = int(input().strip())
                test_camera(device_id)
            except ValueError:
                print("❌ Invalid device ID")
                sys.exit(1)
        else:
            sys.exit(1)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⏹️  Test cancelled")
        cv2.destroyAllWindows()
        sys.exit(0)






