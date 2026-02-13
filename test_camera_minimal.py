#!/usr/bin/env python3
"""
Minimal Camera Test - Absolute simplest test possible
If this doesn't work, it's a camera/permissions issue
"""

import cv2

print("=" * 60)
print("MINIMAL CAMERA TEST")
print("=" * 60)

# Try to open camera
print("\nOpening camera 0...")
cap = cv2.VideoCapture(0)

print(f"Camera opened: {cap.isOpened()}")

if not cap.isOpened():
    print("\n❌ FAILED - Camera won't open")
    print("\nTry:")
    print("  1. Check System Preferences → Security & Privacy → Camera")
    print("  2. Grant permission to Terminal/Python")
    print("  3. Try device ID 1: cv2.VideoCapture(1)")
    exit(1)

print("✅ Camera opened!")
print("\nReading frames... (Press Q to quit)")
print("-" * 60)

frame_count = 0

try:
    while True:
        ret, frame = cap.read()
        
        if not ret:
            print(f"❌ Can't read frame {frame_count + 1}")
            break
        
        frame_count += 1
        
        # Add frame counter
        cv2.putText(frame, f"Frame: {frame_count}", 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        
        # Show frame
        cv2.imshow('Minimal Camera Test - Press Q to quit', frame)
        
        # Print every 30 frames
        if frame_count % 30 == 0:
            print(f"Frame {frame_count} - Shape: {frame.shape}")
        
        # Quit on Q
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("\nQuitting...")
            break

except KeyboardInterrupt:
    print("\n\nInterrupted")

finally:
    cap.release()
    cv2.destroyAllWindows()
    
    print("\n" + "=" * 60)
    print(f"✅ Total frames captured: {frame_count}")
    print("=" * 60)
    
    if frame_count > 0:
        print("\n✅ SUCCESS - Camera is working!")
        print("\nYou can now run:")
        print("  python scripts/run_live_with_display.py")
    else:
        print("\n❌ FAILED - No frames captured")
        print("\nCamera opened but couldn't read frames")






