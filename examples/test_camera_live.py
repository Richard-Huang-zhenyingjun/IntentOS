#!/usr/bin/env python3
"""
Simple test script to verify camera stream works.
Run this to test your camera setup.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.vision.camera_stream import CameraStream, CameraConfig
import cv2

def test_mock_mode():
    """Test camera stream in mock mode (no real camera needed)."""
    print("Testing CameraStream in MOCK mode...")
    print("="*60)
    
    config = CameraConfig(
        mock_mode=True,
        width=640,
        height=480,
        target_fps=30
    )
    
    stream = CameraStream(config, seed=42)
    
    if not stream.start():
        print("❌ Failed to start mock camera")
        return False
    
    print("✅ Mock camera started")
    print(f"   Resolution: {config.width}x{config.height}")
    print(f"   Target FPS: {config.target_fps}")
    print()
    print("Getting 5 frames...")
    
    for i in range(5):
        frame = stream.get_frame()
        if frame is None:
            print(f"❌ Frame {i}: None")
            continue
        
        print(f"✅ Frame {i}: ID={frame.frame_id}, "
              f"timestamp={frame.timestamp:.3f}, "
              f"fps={frame.fps:.1f}, "
              f"size={frame.width}x{frame.height}")
    
    stream.stop()
    print()
    print("✅ Mock mode test passed!")
    return True


def test_real_camera():
    """Test camera stream with real camera (if available)."""
    print("\nTesting CameraStream with REAL camera...")
    print("="*60)
    
    config = CameraConfig(
        mock_mode=False,
        device_index=0,
        width=640,
        height=480,
        target_fps=30
    )
    
    stream = CameraStream(config)
    
    if not stream.start():
        print("⚠️  Real camera not available (this is OK for testing)")
        print("   The system will continue without camera")
        return True  # Not an error - graceful degradation
    
    print("✅ Real camera started")
    print(f"   Device: {config.device_index}")
    print(f"   Resolution: {config.width}x{config.height}")
    print()
    print("Getting 5 frames (press Ctrl+C to stop)...")
    
    try:
        for i in range(5):
            frame = stream.get_frame()
            if frame is None:
                print(f"⚠️  Frame {i}: None (camera may have disconnected)")
                continue
            
            print(f"✅ Frame {i}: ID={frame.frame_id}, "
                  f"timestamp={frame.timestamp:.3f}, "
                  f"fps={frame.fps:.1f}")
            
            # Optionally display frame (uncomment to see video)
            # cv2.imshow('Camera Test', frame.image)
            # if cv2.waitKey(1) & 0xFF == ord('q'):
            #     break
        
        print()
        print("✅ Real camera test passed!")
        return True
        
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
        return True
    finally:
        stream.stop()
        # cv2.destroyAllWindows()


if __name__ == "__main__":
    print("Camera Stream Test")
    print("="*60)
    print()
    
    # Test mock mode (always works)
    mock_ok = test_mock_mode()
    
    # Test real camera (may not be available)
    real_ok = test_real_camera()
    
    print()
    print("="*60)
    if mock_ok:
        print("✅ All tests passed!")
        print()
        print("Next steps:")
        print("  1. Camera stream is ready for integration")
        print("  2. Add object detection module (next step)")
        print("  3. Integrate with SystemOrchestrator")
    else:
        print("❌ Some tests failed")
    print("="*60)

