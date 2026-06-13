import pybullet as p
import pybullet_data
import numpy as np
from src.worlds.world_artifacts import WorldArtifacts
from src.robot.simulator import RobotSimulator as Simulator


def build_messy_table(
    sim: Simulator,
    config: dict,
    object_colors: list = None,
) -> WorldArtifacts:
    """
    Build a deterministic messy table scene.
    
    Returns:
        WorldArtifacts with IDs of everything created
    """
    world_cfg = config['world']['messy_table']
    seed = world_cfg['seed']
    n_objects = world_cfg['n_objects']
    if object_colors is None:
        object_colors = world_cfg.get('object_colors')
    
    # Set random seed for reproducibility
    np.random.seed(seed)
    
    # Load table (simple box for Week 1)
    table_half_extents = [0.4, 0.3, 0.3]  # 80cm x 60cm x 60cm
    table_pos = [0.0, 0.0, 0.3]  # Center at origin, top at z=0.6
    
    table_collision = p.createCollisionShape(
        p.GEOM_BOX,
        halfExtents=table_half_extents
    )
    table_visual = p.createVisualShape(
        p.GEOM_BOX,
        halfExtents=table_half_extents,
        rgbaColor=[0.6, 0.4, 0.2, 1.0]  # Brown
    )
    table_id = p.createMultiBody(
        baseMass=0,  # Static
        baseCollisionShapeIndex=table_collision,
        baseVisualShapeIndex=table_visual,
        basePosition=table_pos
    )
    p.changeDynamics(
        table_id,
        -1,
        lateralFriction=1.0,
        spinningFriction=0.05,
        rollingFriction=0.03,
    )
    
    print(f"[WORLD] Created table at {table_pos}, top at z=0.6")
    
    # Spawn objects on table
    bounds = world_cfg['table_bounds_xy']
    x_min, x_max, y_min, y_max = bounds
    object_positions = world_cfg.get('object_positions')
    resting_z = 0.66  # ~3cm above table top; blocks drop and settle gently.
    
    object_ids = []
    intended_positions = {}
    
    for i in range(n_objects):
        if object_positions and i < len(object_positions):
            x = object_positions[i][0]
            y = object_positions[i][1]
        else:
            # Random position on table (with rejection sampling)
            attempts = 0
            while attempts < 10:
                x = np.random.uniform(x_min, x_max)
                y = np.random.uniform(y_min, y_max)

                # Check not too close to existing objects (simple)
                too_close = False
                for obj_id in object_ids:
                    obj_pos = p.getBasePositionAndOrientation(obj_id)[0]
                    dist = np.linalg.norm(np.array([x, y]) - np.array(obj_pos[:2]))
                    if dist < 0.08:  # 8cm minimum spacing
                        too_close = True
                        break

                if not too_close:
                    break
                attempts += 1
        
        # Create tuned cube (smaller/lighter with higher friction).
        size = 0.03  # half extent -> 6cm cubes
        collision = p.createCollisionShape(p.GEOM_BOX, halfExtents=[size]*3)
        if object_colors and i < len(object_colors):
            rgba = object_colors[i]
        else:
            rgba = [np.random.rand(), np.random.rand(), np.random.rand(), 1.0]
        visual = p.createVisualShape(
            p.GEOM_BOX,
            halfExtents=[size]*3,
            rgbaColor=rgba
        )
        obj_id = p.createMultiBody(
            baseMass=0.08,  # 80g
            baseCollisionShapeIndex=collision,
            baseVisualShapeIndex=visual,
            basePosition=[x, y, resting_z]
        )
        p.changeDynamics(
            obj_id,
            -1,
            lateralFriction=1.5,
            spinningFriction=0.1,
            rollingFriction=0.05,
            restitution=0.1,
            contactStiffness=10000,
            contactDamping=100,
        )
        object_ids.append(obj_id)
        intended_positions[obj_id] = (x, y)
    
    print(f"[WORLD] Spawned {len(object_ids)} objects")
    
    # Define bin zone (visual marker)
    bin_center = tuple(world_cfg['bin_zone_center'])
    bin_radius = world_cfg['bin_zone_radius']
    
    # Draw bin zone marker (debug visualization)
    _draw_bin_zone_marker(bin_center, bin_radius)

    # Create physical tray container (low walls to catch objects).
    tray_y = -0.18
    tray_inner_w = 0.08
    tray_inner_d = 0.08
    wall_t = 0.008
    tray_center = [0.0, tray_y, 0.61]
    tray_half = [0.08, 0.06, 0.01]  # 16cm x 12cm tray base

    tray_col = p.createCollisionShape(
        p.GEOM_BOX,
        halfExtents=tray_half,
    )
    tray_vis = p.createVisualShape(
        p.GEOM_BOX,
        halfExtents=tray_half,
        rgbaColor=[0.8, 0.6, 0.2, 0.6],
    )
    p.createMultiBody(
        baseMass=0,
        baseCollisionShapeIndex=tray_col,
        baseVisualShapeIndex=tray_vis,
        basePosition=tray_center,
    )

    wall_h = 0.04  # 40mm walls — tall enough to catch falling objects
    tray_parts = [
        (0.0, tray_y - tray_inner_d - wall_t, tray_inner_w, wall_t),
        (0.0, tray_y + tray_inner_d + wall_t, tray_inner_w, wall_t),
        (tray_inner_w + wall_t, tray_y, wall_t, tray_inner_d),
        (-(tray_inner_w + wall_t), tray_y, wall_t, tray_inner_d),
    ]
    for wx, wy, wlx, wly in tray_parts:
        wall_col = p.createCollisionShape(
            p.GEOM_BOX,
            halfExtents=[wlx, wly, wall_h],
        )
        wall_vis = p.createVisualShape(
            p.GEOM_BOX,
            halfExtents=[wlx, wly, wall_h],
            rgbaColor=[0.8, 0.6, 0.2, 0.4],
        )
        p.createMultiBody(
            baseMass=0,
            baseCollisionShapeIndex=wall_col,
            baseVisualShapeIndex=wall_vis,
            basePosition=[wx, wy, 0.63],
        )

    # Physical bin container - beside the table edge.
    bin_x, bin_y = 0.4, 0.0
    bin_base_z = 0.55
    bin_inner_w = 0.08
    bin_inner_d = 0.08
    bin_wall_t = 0.008
    bin_wall_h = 0.06

    bin_parts = [
        (
            [bin_inner_w, bin_inner_d, 0.005],
            [bin_x, bin_y, bin_base_z],
            [0.2, 0.6, 0.2, 1.0],
        ),
        (
            [bin_inner_w + bin_wall_t, bin_wall_t, bin_wall_h],
            [bin_x, bin_y - bin_inner_d - bin_wall_t, bin_base_z + bin_wall_h],
            [0.2, 0.6, 0.2, 1.0],
        ),
        (
            [bin_inner_w + bin_wall_t, bin_wall_t, bin_wall_h],
            [bin_x, bin_y + bin_inner_d + bin_wall_t, bin_base_z + bin_wall_h],
            [0.2, 0.6, 0.2, 1.0],
        ),
        (
            [bin_wall_t, bin_inner_d + bin_wall_t * 2, bin_wall_h],
            [bin_x - bin_inner_w - bin_wall_t, bin_y, bin_base_z + bin_wall_h],
            [0.2, 0.6, 0.2, 1.0],
        ),
        (
            [bin_wall_t, bin_inner_d + bin_wall_t * 2, bin_wall_h],
            [bin_x + bin_inner_w + bin_wall_t, bin_y, bin_base_z + bin_wall_h],
            [0.2, 0.6, 0.2, 1.0],
        ),
    ]

    for half_extents, pos, color in bin_parts:
        bin_col = p.createCollisionShape(
            p.GEOM_BOX,
            halfExtents=half_extents,
        )
        bin_vis = p.createVisualShape(
            p.GEOM_BOX,
            halfExtents=half_extents,
            rgbaColor=color,
        )
        p.createMultiBody(
            baseMass=0,
            baseCollisionShapeIndex=bin_col,
            baseVisualShapeIndex=bin_vis,
            basePosition=pos,
        )

    for _ in range(240):
        p.stepSimulation()

    for oid in object_ids:
        pos, orn = p.getBasePositionAndOrientation(oid)
        if abs(pos[0]) > 1.0 or abs(pos[1]) > 1.0 or pos[2] > 1.0 or pos[2] < 0.5:
            x, y = intended_positions[oid]
            p.resetBasePositionAndOrientation(oid, [x, y, 0.63], orn)
        p.resetBaseVelocity(oid, [0, 0, 0], [0, 0, 0])

    return WorldArtifacts(
        table_id=table_id,
        object_ids=object_ids,
        bin_zone_center=bin_center,
        bin_zone_radius=bin_radius,
        seed=seed
    )


def _draw_bin_zone_marker(center: tuple, radius: float):
    """Draw visual circle to mark bin zone"""
    # Draw circle on table plane using debug lines
    num_segments = 16
    for i in range(num_segments):
        angle1 = 2 * np.pi * i / num_segments
        angle2 = 2 * np.pi * (i + 1) / num_segments
        
        x1 = center[0] + radius * np.cos(angle1)
        y1 = center[1] + radius * np.sin(angle1)
        x2 = center[0] + radius * np.cos(angle2)
        y2 = center[1] + radius * np.sin(angle2)
        
        p.addUserDebugLine(
            [x1, y1, center[2]],
            [x2, y2, center[2]],
            lineColorRGB=[0, 1, 0],  # Green
            lineWidth=2
        )


def reset_world(
    sim: Simulator,
    config: dict,
    previous_artifacts: WorldArtifacts | None = None,
    seed: int | None = None,
) -> WorldArtifacts:
    """
    Reset world in-place:
    1) despawn table + objects
    2) reset arm home pose
    3) respawn table + objects (same/new seed)
    """
    # Remove old world bodies first (if present).
    if previous_artifacts is not None:
        for obj_id in previous_artifacts.object_ids:
            try:
                p.removeBody(obj_id)
            except Exception:
                pass
        try:
            p.removeBody(previous_artifacts.table_id)
        except Exception:
            pass

    # Remove debug lines from old bin marker.
    p.removeAllUserDebugItems()

    # Ensure arm returns to known home pose before respawn.
    if hasattr(sim, "_reset_arm_position"):
        sim._reset_arm_position()

    # Apply optional seed override for reproducible reset.
    if seed is not None:
        config.setdefault("world", {})
        config["world"].setdefault("messy_table", {})
        config["world"]["messy_table"]["seed"] = seed

    return build_messy_table(sim, config)
