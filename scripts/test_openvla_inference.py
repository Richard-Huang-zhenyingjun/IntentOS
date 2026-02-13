"""
Test OpenVLA model inference on a synthetic image.

Run: python scripts/test_openvla_inference.py

Expected output:
  - Model loads (may take 1-5 min first time for download)
  - Produces 7-dim action vector
  - No crashes
"""
import numpy as np
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.external.openvla.adapter import OpenVLAAdapter


def main():
    print("=" * 60)
    print("OpenVLA Inference Test")
    print("=" * 60)

    # Create adapter
    adapter = OpenVLAAdapter()

    # Load model (downloads on first run)
    print("\n[1/3] Loading model (this may take a few minutes on first run)...")
    try:
        adapter.load_model()
        print(f"  ✓ Model loaded on {adapter._device}")
        print(f"  ✓ Action dimensions: {adapter.action_dim}")
    except Exception as e:
        print(f"  ✗ Model loading failed: {e}")
        print("\n  Possible fixes:")
        print("  - Ensure torch is installed: pip install torch torchvision")
        print("  - Ensure transformers is installed: pip install transformers")
        print("  - Check disk space (~15GB for model weights)")
        print("  - Check internet connection (downloads from HuggingFace)")
        return 1

    # Create synthetic test image (a simple colored scene)
    print("\n[2/3] Creating test image...")
    image = np.zeros((480, 640, 3), dtype=np.uint8)
    # Red object on green table
    image[200:280, 280:360] = [255, 0, 0]      # Red cube
    image[300:320, 200:440] = [139, 90, 43]     # Brown table
    image[:200, :] = [135, 206, 235]            # Sky blue background
    print(f"  ✓ Test image: {image.shape}, dtype={image.dtype}")

    # Run inference
    print("\n[3/3] Running inference...")
    instruction = "pick up the red block"
    try:
        action = adapter.predict(instruction, image)
        print(f"  ✓ Instruction: '{instruction}'")
        print(f"  ✓ Delta position: {action.delta_position}")
        print(f"  ✓ Delta rotation: {action.delta_rotation}")
        print(f"  ✓ Gripper: {action.gripper:.3f}")
        print(f"  ✓ Raw action (7-dim): {action.raw_action}")
    except Exception as e:
        print(f"  ✗ Inference failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Validate output
    print("\n" + "=" * 60)
    print("Validation:")
    assert action.raw_action.shape == (7,) or action.raw_action.shape[0] >= 7, (
        f"Expected 7-dim action, got shape {action.raw_action.shape}"
    )
    assert not np.any(np.isnan(action.raw_action)), "NaN in action output"
    assert not np.any(np.isinf(action.raw_action)), "Inf in action output"
    print("  ✓ Action shape valid")
    print("  ✓ No NaN/Inf values")
    print("  ✓ ALL CHECKS PASSED")

    adapter.close()
    print("\nOpenVLA inference test COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
