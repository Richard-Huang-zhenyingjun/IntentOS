"""
Motion Baseline Test - Bypasses all orchestrator/controller code.
Tests PyBullet + URDF + motor control in isolation.
If this doesn't work, nothing else will.
"""
import pybullet as p
import pybullet_data
import time
import numpy as np
import os

def main():
    # Connect to PyBullet
    # On macOS, GUI mode can crash with OpenGL errors, so we default to DIRECT
    # Set environment variable BASELINE_USE_GUI=1 to force GUI mode
    import os
    import sys
    
    use_gui = os.environ.get('BASELINE_USE_GUI', '0') == '1'
    
    # On macOS, GUI often fails with OpenGL errors, so default to DIRECT
    if sys.platform == 'darwin' and not use_gui:
        print("[BASELINE] macOS detected - using DIRECT mode (set BASELINE_USE_GUI=1 to try GUI)")
        use_gui = False
    
    if use_gui:
        print("[BASELINE] Attempting GUI connection...")
        try:
            physics_client = p.connect(p.GUI)
            print("[BASELINE] Connected to PyBullet GUI")
        except Exception as e:
            print(f"[BASELINE] GUI connection failed: {e}")
            print("[BASELINE] Falling back to DIRECT mode")
            use_gui = False
            physics_client = p.connect(p.DIRECT)
    else:
        physics_client = p.connect(p.DIRECT)
        print("[BASELINE] Connected to PyBullet (DIRECT/headless mode)")
        print("[BASELINE] Note: Motion will be tested but not visually displayed")
    
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.setGravity(0, 0, -9.81)
    
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
                print(f"[BASELINE] Loaded robot from: {urdf_path}")
                break
        except Exception as e:
            print(f"[BASELINE] Failed to load {urdf_path}: {e}")
            continue
    
    if robot_id is None:
        print("[BASELINE] ERROR: Could not load robot URDF")
        return False
    
    # Disable real-time simulation (manual stepping)
    p.setRealTimeSimulation(0)
    print("[BASELINE] Real-time simulation disabled (manual stepping)")
    
    # Discover joints
    num_joints = p.getNumJoints(robot_id)
    revolute_joints = []
    
    for i in range(num_joints):
        joint_info = p.getJointInfo(robot_id, i)
        joint_type = joint_info[2]
        joint_name = joint_info[1].decode('utf-8')
        
        if joint_type == p.JOINT_REVOLUTE:
            revolute_joints.append(i)
            print(f"[BASELINE] Joint {i}: {joint_name} (REVOLUTE)")
    
    if not revolute_joints:
        print("[BASELINE] ERROR: No revolute joints found!")
        return False
    
    # Test single joint motion
    test_joint_idx = revolute_joints[0]  # Test joint 0
    target_position = 0.5  # radians
    
    print(f"\n[BASELINE] Testing joint {test_joint_idx}")
    print(f"[BASELINE] Target position: {target_position} rad")
    print(f"[BASELINE] Starting 4-second simulation (240 frames @ 60Hz)...\n")
    
    # Get initial position
    initial_pos = p.getJointState(robot_id, test_joint_idx)[0]
    print(f"[BASELINE] Initial position: {initial_pos:.4f}")
    
    # Set motor control
    p.setJointMotorControl2(
        bodyIndex=robot_id,
        jointIndex=test_joint_idx,
        controlMode=p.POSITION_CONTROL,
        targetPosition=target_position,
        force=400.0,  # Explicit force
        positionGain=0.2,
        velocityGain=1.0
    )
    
    # Step simulation and log motion
    num_frames = 240
    log_interval = 20
    
    for frame in range(num_frames):
        p.stepSimulation()
        if use_gui:
            time.sleep(1./240.)  # Real-time visualization only in GUI mode
        
        if frame % log_interval == 0:
            current_pos = p.getJointState(robot_id, test_joint_idx)[0]
            delta = current_pos - initial_pos
            error = abs(current_pos - target_position)
            print(f"[BASELINE] Frame {frame:3d}: pos={current_pos:+.4f}, delta={delta:+.4f}, error={error:.4f}")
    
    # Final check
    final_pos = p.getJointState(robot_id, test_joint_idx)[0]
    final_delta = abs(final_pos - initial_pos)
    
    print(f"\n[BASELINE] Final position: {final_pos:.4f}")
    print(f"[BASELINE] Total movement: {final_delta:.4f} rad")
    
    # Success criteria: joint moved at least 0.1 rad
    success = final_delta > 0.1
    
    if success:
        print("[BASELINE] ✅ SUCCESS - Joint moved significantly!")
    else:
        print("[BASELINE] ❌ FAILURE - Joint did not move enough")
        print("[BASELINE] Possible issues:")
        print("[BASELINE]   - URDF has fixed/locked joints")
        print("[BASELINE]   - Force too low")
        print("[BASELINE]   - Simulation not stepping")
        print("[BASELINE]   - Joint limits preventing motion")
    
    p.disconnect()
    return success

if __name__ == '__main__':
    try:
        success = main()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n[BASELINE] FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

