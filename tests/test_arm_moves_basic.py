import pytest
import pybullet as p
import pybullet_data
import numpy as np
import os
import sys
from pathlib import Path

# Add parent directory so src can be imported as a package
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_arm_moves_to_target():
    """
    Headless test: Arm must physically move when given target.
    This is the ground truth test for Week 0.
    """
    # Connect headless
    physics_client = p.connect(p.DIRECT)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.setGravity(0, 0, -9.81)
    p.setRealTimeSimulation(0)
    
    # Load plane
    plane_id = p.loadURDF("plane.urdf")
    
    # Load robot (use same paths as simulator)
    robot_urdf_paths = [
        "kuka_iiwa/model.urdf",                    # Standard PyBullet data
        "kuka_iiwa7/model.urdf",                   # Alternative name
        os.path.join(pybullet_data.getDataPath(), "kuka_iiwa/model.urdf"),
    ]
    
    robot_id = None
    for urdf_path in robot_urdf_paths:
        try:
            robot_id = p.loadURDF(
                urdf_path,
                basePosition=[0, 0, 0],
                baseOrientation=[0, 0, 0, 1],
                useFixedBase=True,
                flags=p.URDF_USE_SELF_COLLISION
            )
            if robot_id >= 0:
                print(f"[TEST] Loaded robot from: {urdf_path}")
                break
        except Exception as e:
            print(f"[TEST] Failed to load {urdf_path}: {e}")
            continue
    
    if robot_id is None:
        pytest.fail("Could not load robot URDF from any path")
    
    # Get initial joint 0 position
    initial_j0 = p.getJointState(robot_id, 0)[0]
    print(f"[TEST] Initial joint 0 position: {initial_j0:.4f}")
    
    # Command motion on joint 0 directly (bypass IK for simplicity)
    target_j0 = initial_j0 + 0.5  # Move 0.5 radians
    
    p.setJointMotorControl2(
        bodyIndex=robot_id,
        jointIndex=0,
        controlMode=p.POSITION_CONTROL,
        targetPosition=target_j0,
        force=400.0,
        positionGain=0.2,
        velocityGain=1.0
    )
    
    print(f"[TEST] Commanded joint 0 to move from {initial_j0:.4f} to {target_j0:.4f}")
    
    # Step simulation
    for frame in range(240):  # 4 seconds at 60Hz
        p.stepSimulation()
        if frame % 60 == 0:  # Log every second
            current_j0 = p.getJointState(robot_id, 0)[0]
            print(f"[TEST] Frame {frame}: joint 0 = {current_j0:.4f}")
    
    # Check final position
    final_j0 = p.getJointState(robot_id, 0)[0]
    delta = abs(final_j0 - initial_j0)
    
    print(f"[TEST] Final joint 0 position: {final_j0:.4f}")
    print(f"[TEST] Total movement: {delta:.4f} radians")
    
    p.disconnect()
    
    # Assert significant movement occurred
    assert delta > 0.1, f"Joint did not move enough: delta={delta:.4f} (expected > 0.1)"
    print(f"✅ Test passed: joint moved {delta:.4f} radians")


if __name__ == '__main__':
    test_arm_moves_to_target()

