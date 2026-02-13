import pybullet as p
from dataclasses import dataclass
from typing import Optional


@dataclass
class GripperState:
    """Current gripper state."""
    width: float
    force: float
    is_closed: bool
    is_grasping: bool


class GripperController:
    """Physical parallel-jaw gripper controller with force feedback."""

    def __init__(
        self,
        robot_id: int,
        left_finger_joint: int,
        right_finger_joint: int,
        max_width: float = 0.08,
        close_force: float = 30.0,
        grasp_force_threshold: float = 5.0,
    ):
        self.robot_id = robot_id
        self.left_finger_joint = left_finger_joint
        self.right_finger_joint = right_finger_joint
        self.max_width = max_width
        self.close_force = close_force
        self.grasp_force_threshold = grasp_force_threshold

        self._target_width = max_width
        self._closing = False
        self._opening = False

    def open(self) -> None:
        self._target_width = self.max_width
        self._opening = True
        self._closing = False
        self._set_finger_positions(self.max_width / 2.0, force=self.close_force)

    def close(self, force: Optional[float] = None) -> None:
        applied_force = force if force is not None else self.close_force
        self._target_width = 0.0
        self._closing = True
        self._opening = False
        self._set_finger_positions(0.0, force=applied_force)

    def _set_finger_positions(self, half_width: float, force: float) -> None:
        p.setJointMotorControl2(
            bodyIndex=self.robot_id,
            jointIndex=self.left_finger_joint,
            controlMode=p.POSITION_CONTROL,
            targetPosition=half_width,
            force=force,
            maxVelocity=0.1,
        )
        p.setJointMotorControl2(
            bodyIndex=self.robot_id,
            jointIndex=self.right_finger_joint,
            controlMode=p.POSITION_CONTROL,
            targetPosition=half_width,
            force=force,
            maxVelocity=0.1,
        )

    def get_state(self) -> GripperState:
        left_state = p.getJointState(self.robot_id, self.left_finger_joint)
        right_state = p.getJointState(self.robot_id, self.right_finger_joint)

        left_pos = float(left_state[0])
        right_pos = float(right_state[0])
        width = left_pos + right_pos

        left_force = abs(float(left_state[3]))
        right_force = abs(float(right_state[3]))
        total_force = left_force + right_force

        is_closed = width < 0.005
        is_grasping = total_force > self.grasp_force_threshold

        return GripperState(
            width=width,
            force=total_force,
            is_closed=is_closed,
            is_grasping=is_grasping,
        )

    def is_motion_complete(self) -> bool:
        state = self.get_state()
        if self._closing:
            return state.is_closed or state.is_grasping
        if self._opening:
            return abs(state.width - self.max_width) < 0.005
        return True

    def verify_grasp(self) -> bool:
        return self.get_state().is_grasping

    def get_grasp_quality(self) -> float:
        """Assess grasp quality from force profile."""
        state = self.get_state()
        ideal_force = 15.0
        force_error = abs(state.force - ideal_force) / max(ideal_force, 1e-6)
        quality = max(0.0, 1.0 - force_error)
        if not state.is_closed and state.force < 10.0:
            quality *= 0.5
        return float(quality)
