"""
MuJoCo simulator — drop-in replacement for PyBullet simulator.

Implements the same interface as src/robot/simulator.py so the rest of
the system (orchestrator, executor, etc.) doesn't need to change.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import mujoco
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class MuJoCoConfig:
    """Configuration for MuJoCo simulator."""
    model_path: str = os.path.join("models", "kuka_iiwa", "model.xml")
    timestep: float = 0.002          # 500 Hz physics (MuJoCo default)
    render_width: int = 640
    render_height: int = 480
    use_gui: bool = True
    gravity: tuple = (0.0, 0.0, -9.81)


class MuJoCoSimulator:
    """
    MuJoCo-based robot simulator.

    Replaces the PyBullet simulator with identical external interface:
    - load_robot() → loads MJCF/URDF model
    - step() → advances physics
    - get_joint_positions() → reads joint state
    - set_joint_targets() → sends position commands
    - get_end_effector_pose() → reads EE position + orientation
    - render_camera() → returns RGB image (for OpenVLA input)
    - add_object() → spawns objects in the scene
    - reset() → resets simulation state
    """

    def __init__(self, config: Optional[MuJoCoConfig] = None):
        self.config = config or MuJoCoConfig()
        self._model: Optional[mujoco.MjModel] = None
        self._data: Optional[mujoco.MjData] = None
        self._renderer: Optional[mujoco.Renderer] = None
        self._viewer = None
        self._is_loaded = False
        self._joint_names: list[str] = []
        self._actuator_names: list[str] = []

    def load_robot(self) -> None:
        """Load robot model from MJCF or URDF."""
        path = self.config.model_path
        if not os.path.exists(path):
            raise FileNotFoundError(f"Model not found: {path}")

        logger.info(f"Loading MuJoCo model from {path}")
        self._model = mujoco.MjModel.from_xml_path(path)
        self._data = mujoco.MjData(self._model)

        # Discover joints and actuators
        self._joint_names = [
            mujoco.mj_id2name(self._model, mujoco.mjtObj.mjOBJ_JOINT, i)
            for i in range(self._model.njnt)
            if mujoco.mj_id2name(self._model, mujoco.mjtObj.mjOBJ_JOINT, i) is not None
        ]
        self._actuator_names = [
            mujoco.mj_id2name(self._model, mujoco.mjtObj.mjOBJ_ACTUATOR, i)
            for i in range(self._model.nu)
            if mujoco.mj_id2name(self._model, mujoco.mjtObj.mjOBJ_ACTUATOR, i) is not None
        ]

        logger.info(
            f"Model loaded: {self._model.nq} qpos, {self._model.nv} qvel, "
            f"{self._model.nu} actuators, {len(self._joint_names)} named joints"
        )
        logger.info(f"Joint names: {self._joint_names}")
        logger.info(f"Actuator names: {self._actuator_names}")

        # Initialize renderer (optional in headless/CI environments).
        if os.environ.get("MUJOCO_GL", "").lower() == "disable":
            logger.info("Skipping MuJoCo renderer initialization (MUJOCO_GL=disable)")
            self._renderer = None
        else:
            try:
                self._renderer = mujoco.Renderer(
                    self._model,
                    height=self.config.render_height,
                    width=self.config.render_width,
                )
            except Exception as exc:  # pragma: no cover - environment dependent
                logger.warning("MuJoCo renderer unavailable: %s", exc)
                self._renderer = None

        self._is_loaded = True

    def step(self) -> None:
        """Advance physics by one timestep."""
        assert self._is_loaded, "Call load_robot() first"
        mujoco.mj_step(self._model, self._data)

    def step_n(self, n: int) -> None:
        """Advance physics by n timesteps."""
        for _ in range(n):
            self.step()

    def get_joint_positions(self) -> np.ndarray:
        """Return current joint positions (qpos for all robot joints)."""
        assert self._is_loaded
        # For a simple kinematic chain, qpos directly gives joint angles
        return self._data.qpos[: self._model.njnt].copy()

    def get_joint_velocities(self) -> np.ndarray:
        """Return current joint velocities."""
        assert self._is_loaded
        return self._data.qvel[: self._model.nv].copy()

    def set_joint_targets(self, targets: np.ndarray) -> None:
        """
        Set target joint positions for position-controlled actuators.

        This sets ctrl for position actuators — MuJoCo's built-in PD
        controller handles the physics of getting there smoothly.
        """
        assert self._is_loaded
        assert len(targets) == self._model.nu, (
            f"Expected {self._model.nu} targets, got {len(targets)}"
        )
        self._data.ctrl[:] = targets

    def get_end_effector_pose(self) -> tuple[np.ndarray, np.ndarray]:
        """
        Return (position, orientation_quat) of end effector.

        Reads from the 'end_effector' site defined in MJCF.
        Returns:
            position: np.ndarray shape (3,) — [x, y, z]
            orientation: np.ndarray shape (4,) — quaternion [w, x, y, z]
        """
        assert self._is_loaded
        site_id = mujoco.mj_name2id(
            self._model, mujoco.mjtObj.mjOBJ_SITE, "end_effector"
        )
        if site_id < 0:
            raise ValueError("No 'end_effector' site in model")

        pos = self._data.site_xpos[site_id].copy()
        # Convert rotation matrix to quaternion
        rot_mat = self._data.site_xmat[site_id].reshape(3, 3)
        quat = np.zeros(4)
        mujoco.mju_mat2Quat(quat, rot_mat.flatten())
        return pos, quat

    def render_camera(self, camera_name: str = "") -> np.ndarray:
        """
        Render RGB image from camera.

        Args:
            camera_name: Name of camera in MJCF. Empty string = free camera.

        Returns:
            np.ndarray shape (H, W, 3) dtype uint8 — RGB image.
            This is what gets fed to OpenVLA.
        """
        assert self._is_loaded
        if self._renderer is None:
            raise RuntimeError("Renderer is unavailable in this environment.")
        mujoco.mj_forward(self._model, self._data)
        self._renderer.update_scene(self._data, camera=camera_name)
        return self._renderer.render()

    def add_object(
        self,
        name: str,
        shape: str = "box",
        size: tuple = (0.03, 0.03, 0.03),
        position: tuple = (0.5, 0.0, 0.45),
        color: tuple = (1.0, 0.0, 0.0, 1.0),
        mass: float = 0.1,
    ) -> int:
        """
        Add a manipulable object to the scene.

        NOTE: MuJoCo doesn't support runtime body addition to compiled models.
        Objects must be defined in the MJCF XML. This method is a placeholder
        that documents the interface — actual objects should be added to the
        MJCF file or use MuJoCo's `mjx` for runtime modification.

        For Week 1, define objects directly in model.xml.
        For later weeks, consider using dm_control's `composer` for dynamic scenes.

        Returns:
            Object ID (body index in the model).
        """
        logger.warning(
            "add_object() is a placeholder — add objects to MJCF XML directly. "
            f"Requested: {name} at {position}"
        )
        # Try to find the object by name if it's already in the model
        body_id = mujoco.mj_name2id(
            self._model, mujoco.mjtObj.mjOBJ_BODY, name
        )
        if body_id >= 0:
            return body_id
        return -1

    def get_object_position(self, name: str) -> Optional[np.ndarray]:
        """Get position of a named body."""
        assert self._is_loaded
        body_id = mujoco.mj_name2id(
            self._model, mujoco.mjtObj.mjOBJ_BODY, name
        )
        if body_id < 0:
            return None
        return self._data.xpos[body_id].copy()

    def reset(self) -> None:
        """Reset simulation to initial state."""
        assert self._is_loaded
        mujoco.mj_resetData(self._model, self._data)
        mujoco.mj_forward(self._model, self._data)
        logger.info("Simulation reset to initial state")

    def launch_viewer(self) -> None:
        """Launch interactive MuJoCo viewer (blocking)."""
        assert self._is_loaded
        import mujoco.viewer
        mujoco.viewer.launch(self._model, self._data)

    def close(self) -> None:
        """Clean up resources."""
        if self._renderer:
            self._renderer.close()
            self._renderer = None
        self._viewer = None
        self._is_loaded = False
        logger.info("MuJoCo simulator closed")

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    @property
    def num_joints(self) -> int:
        return self._model.njnt if self._model else 0

    @property
    def num_actuators(self) -> int:
        return self._model.nu if self._model else 0

    @property
    def joint_names(self) -> list[str]:
        return self._joint_names.copy()

    @property
    def timestep(self) -> float:
        return self._model.opt.timestep if self._model else 0.002
