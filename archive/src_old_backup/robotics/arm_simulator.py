"""
Robot arm simulator - owns PyBullet connection and world state.
Week 1: Static world with gravity, table, cube, and arm.
"""

import time
from typing import Dict, Any, Optional
import yaml
import numpy as np
import pybullet as p
import pybullet_data
from .arm_model import ArmModel
from utils.safe_pybullet import init_safe_pybullet, is_valid_body as safe_is_valid_body


# Legacy compatibility: Keep old function signature but delegate to safe wrapper
def is_valid_body(body_id: int, physics_client_id: int = 0) -> bool:
    """
    Check if a PyBullet body ID is currently valid.
    
    DEPRECATED: Use utils.safe_pybullet.is_valid_body() instead.
    This function is kept for backward compatibility.
    
    Args:
        body_id: PyBullet body unique ID to validate
        physics_client_id: PyBullet physics client (default 0, ignored - uses global instance)
    
    Returns:
        True if body exists in current simulation, False otherwise
    """
    return safe_is_valid_body(body_id)


class ArmSimulator:
    """
    PyBullet simulation environment manager.
    
    Responsibilities:
        - Connect/disconnect PyBullet (GUI or DIRECT)
        - Load world (plane, table, object, robot)
        - Step physics simulation
        - Provide access to body IDs and models
    
    Week 1: Static world only (no motion control).
    """
    
    def __init__(self, cfg_path: str = "configs/robotics.yaml"):
        """
        Initialize simulator (does NOT connect yet).
        
        Args:
            cfg_path: Path to robotics configuration YAML
        """
        with open(cfg_path, 'r') as f:
            self.cfg = yaml.safe_load(f)
        
        self.physics_client = None
        self.robot: Optional[ArmModel] = None
        self.plane_id: Optional[int] = None
        self.table_id: Optional[int] = None
        self.object_id: Optional[int] = None
        
        self._connected = False
    
    def connect(self) -> None:
        """
        Connect to PyBullet (GUI or DIRECT mode).
        """
        if self._connected:
            print("⚠️  Already connected to PyBullet")
            return
        
        use_gui = self.cfg['scene']['use_gui']
        
        if use_gui:
            self.physics_client = p.connect(p.GUI)
            
            # Configure camera
            cam_cfg = self.cfg['scene']['camera']
            p.resetDebugVisualizerCamera(
                cameraDistance=cam_cfg['distance'],
                cameraYaw=cam_cfg['yaw'],
                cameraPitch=cam_cfg['pitch'],
                cameraTargetPosition=cam_cfg['target']
            )
            
            # Enable mouse controls for camera (trackpad gestures work)
            p.configureDebugVisualizer(p.COV_ENABLE_MOUSE_PICKING, 1)
            p.configureDebugVisualizer(p.COV_ENABLE_KEYBOARD_SHORTCUTS, 1)
            # Hide debug panels for cleaner view
            p.configureDebugVisualizer(p.COV_ENABLE_GUI, 0)
            p.configureDebugVisualizer(p.COV_ENABLE_TINY_RENDERER, 0)
        else:
            self.physics_client = p.connect(p.DIRECT)
        
        # Set PyBullet data path for built-in models
        p.setAdditionalSearchPath(pybullet_data.getDataPath())
        
        # STEP A: Initialize safe PyBullet boundary layer
        init_safe_pybullet(physics_client_id=self.physics_client)
        print(f"✓ Safe PyBullet boundary initialized")
        
        self._connected = True
        print(f"✓ Connected to PyBullet ({'GUI' if use_gui else 'DIRECT'} mode)")
    
    def reset_world(self) -> None:
        """
        Reset simulation world: load plane, table, object, robot.
        """
        if not self._connected:
            raise RuntimeError("Must call connect() before reset_world()")
        
        # Configure physics
        phys_cfg = self.cfg['physics']
        p.setGravity(*phys_cfg['gravity'])
        p.setTimeStep(phys_cfg['timestep'])
        p.setPhysicsEngineParameter(
            numSolverIterations=phys_cfg['num_solver_iterations']
        )
        
        print(f"✓ Physics configured: {phys_cfg['timestep']}s timestep, gravity={phys_cfg['gravity']}")
        
        # Load ground plane
        self.plane_id = p.loadURDF("plane.urdf")
        print("✓ Loaded ground plane")
        
        # Load table
        self._load_table()
        
        # Load object (cube)
        self._load_object()
        
        # Load robot arm
        self.robot = ArmModel.load(self.cfg['robot'])
        
        print("✓ World reset complete\n")
    
    def _load_table(self) -> None:
        """Create table using collision shape + multibody."""
        table_cfg = self.cfg['table']
        
        # Create box collision shape
        half_extents = [d / 2 for d in table_cfg['dimensions']]
        collision_shape = p.createCollisionShape(
            p.GEOM_BOX,
            halfExtents=half_extents
        )
        
        visual_shape = p.createVisualShape(
            p.GEOM_BOX,
            halfExtents=half_extents,
            rgbaColor=table_cfg['color']
        )
        
        # Create static body
        self.table_id = p.createMultiBody(
            baseMass=0,  # Static (infinite mass)
            baseCollisionShapeIndex=collision_shape,
            baseVisualShapeIndex=visual_shape,
            basePosition=table_cfg['position']
        )
        
        print(f"✓ Loaded table: {table_cfg['dimensions']} at height {table_cfg['height']}m")
    
    def _load_object(self) -> None:
        """Create cube object with mass."""
        obj_cfg = self.cfg['object']
        
        if obj_cfg['type'] != 'cube':
            raise NotImplementedError(f"Object type '{obj_cfg['type']}' not supported in Week 1")
        
        half_size = obj_cfg['size'] / 2
        
        collision_shape = p.createCollisionShape(
            p.GEOM_BOX,
            halfExtents=[half_size] * 3
        )
        
        visual_shape = p.createVisualShape(
            p.GEOM_BOX,
            halfExtents=[half_size] * 3,
            rgbaColor=obj_cfg['color']
        )
        
        self.object_id = p.createMultiBody(
            baseMass=obj_cfg['mass'],
            baseCollisionShapeIndex=collision_shape,
            baseVisualShapeIndex=visual_shape,
            basePosition=obj_cfg['start_pose']['position'],
            baseOrientation=obj_cfg['start_pose']['orientation']
        )
        
        print(f"✓ Loaded {obj_cfg['type']}: {obj_cfg['size']}m, mass={obj_cfg['mass']}kg")
    
    def step(self, n: int = 1) -> None:
        """
        Step physics simulation.
        
        Args:
            n: Number of simulation steps
        """
        if not self._connected:
            raise RuntimeError("Must call connect() before step()")
        
        use_realtime = self.cfg['physics']['use_real_time']
        timestep = self.cfg['physics']['timestep']
        
        for _ in range(n):
            p.stepSimulation()
            
            if use_realtime:
                time.sleep(timestep)
    
    def get_object_pose(self) -> tuple[np.ndarray, np.ndarray]:
        """
        Get current object position and orientation.
        
        Returns:
            (position, orientation) as numpy arrays
        """
        if self.object_id is None:
            raise RuntimeError("Object not loaded")
        
        # STEP B: Use safe wrapper for body pose
        from utils.safe_pybullet import safe_get_pose
        pose_result = safe_get_pose(self.object_id)
        if pose_result is None:
            return None  # Object removed or invalid
        pos, orn = pose_result
        return np.array(pos), np.array(orn)
    
    def get_camera_params(self) -> tuple:
        """
        Get current camera parameters from PyBullet.
        
        Returns:
            (width, height, view_matrix, proj_matrix, cam_pos, cam_target)
            
        Note: In DIRECT mode, returns config defaults since debug visualizer unavailable.
        """
        try:
            cam_info = p.getDebugVisualizerCamera()
            
            width = cam_info[0]
            height = cam_info[1]
            view_matrix = cam_info[2]
            proj_matrix = cam_info[3]
            cam_pos = np.array(cam_info[11])
            cam_target = np.array(cam_info[12])
            
            return width, height, view_matrix, proj_matrix, cam_pos, cam_target
        except (IndexError, AttributeError):
            # DIRECT mode - use config defaults
            cam_cfg = self.cfg['scene']['camera']
            
            # Compute camera position from distance/angles
            distance = cam_cfg['distance']
            yaw_rad = np.radians(cam_cfg['yaw'])
            pitch_rad = np.radians(cam_cfg['pitch'])
            
            target = np.array(cam_cfg['target'])
            
            # Spherical to Cartesian
            cam_pos = target + distance * np.array([
                np.cos(pitch_rad) * np.cos(yaw_rad),
                np.cos(pitch_rad) * np.sin(yaw_rad),
                np.sin(pitch_rad)
            ])
            
            # Default matrices (identity-like)
            view_matrix = list(p.computeViewMatrix(
                cameraEyePosition=cam_pos.tolist(),
                cameraTargetPosition=target.tolist(),
                cameraUpVector=[0, 0, 1]
            ))
            
            proj_matrix = list(p.computeProjectionMatrixFOV(
                fov=60, aspect=1.0, nearVal=0.1, farVal=100
            ))
            
            return 640, 480, view_matrix, proj_matrix, cam_pos, target
    
    def screen_to_world_ray(self, u: float, v: float) -> tuple[np.ndarray, np.ndarray]:
        """
        Convert normalized screen coordinates to world-space ray.
        
        Args:
            u: Horizontal position [0, 1]
            v: Vertical position [0, 1]
            
        Returns:
            (ray_from, ray_to) as 3D world positions
            
        Note: Uses simple projection math in DIRECT mode.
        """
        width, height, view_matrix, proj_matrix, cam_pos, cam_target = self.get_camera_params()
        
        # Convert normalized [0, 1] to pixel coordinates
        x = int(u * width)
        y = int(v * height)
        
        try:
            # Use PyBullet's built-in ray computation (GUI mode)
            # Note: PyBullet screen coordinates are (0,0) at top-left
            ray_from, ray_to = p.getCameraRay(
                x, y,
                width, height,
                view_matrix,
                proj_matrix
            )
            return np.array(ray_from), np.array(ray_to)
        except:
            # DIRECT mode fallback - simple projection
            # Ray starts at camera, goes through screen point toward target
            ray_from = cam_pos
            
            # Simple approximation: interpolate based on u,v
            # u,v=0.5,0.5 points at target
            offset = np.array([
                (u - 0.5) * 2.0,  # Horizontal offset
                (v - 0.5) * 2.0,  # Vertical offset  
                0.0
            ])
            
            direction = (cam_target - cam_pos) + offset
            direction = direction / np.linalg.norm(direction)
            
            ray_to = ray_from + direction * 10.0  # 10m ray length
            
            return ray_from, ray_to
    
    def ray_test_object(self, u: float, v: float) -> Optional[int]:
        """
        Cast ray from camera through screen point and test for object hits.
        
        Args:
            u: Horizontal position [0, 1]
            v: Vertical position [0, 1]
            
        Returns:
            Hit object ID, or None if no hit
        """
        ray_from, ray_to = self.screen_to_world_ray(u, v)
        
        # Cast ray
        results = p.rayTest(ray_from, ray_to)
        
        if not results or len(results) == 0:
            return None
        
        # Get first hit
        hit = results[0]
        object_id = hit[0]
        
        # Filter out plane and table (only return cube)
        if object_id == self.plane_id or object_id == self.table_id:
            return None
        
        return object_id
    
    def close(self) -> None:
        """Disconnect from PyBullet."""
        if self._connected:
            p.disconnect()
            self._connected = False
            print("✓ Disconnected from PyBullet")
