"""Compatibility wrapper around physical gripper controller."""

from typing import Optional
from src.robot.simulator import RobotSimulator
from src.robot.joint_discovery import discover_gripper_joints
from src.robot.gripper import GripperController, GripperState


class GraspController:
    """Deprecated compatibility layer backed by physical finger joints."""

    def __init__(self, sim: RobotSimulator, gripper_cfg: Optional[dict] = None):
        self.sim = sim
        gripper_cfg = gripper_cfg or {}
        self.holding = False
        self.attached_object_id: Optional[int] = None
        self.gripper: Optional[GripperController] = None

        joints = discover_gripper_joints(sim.robot_id)
        left = joints.get("left_finger_joint")
        right = joints.get("right_finger_joint")
        if left is not None and right is not None:
            self.gripper = GripperController(
                robot_id=sim.robot_id,
                left_finger_joint=left,
                right_finger_joint=right,
                max_width=float(gripper_cfg.get("max_width", 0.08)),
                close_force=float(gripper_cfg.get("close_force", 30.0)),
                grasp_force_threshold=float(gripper_cfg.get("grasp_threshold", 5.0)),
            )
            self.gripper.open()
            print(f"[GRASP] Physical gripper enabled (L={left}, R={right})")
        else:
            print("[GRASP] WARNING: Gripper joints not found; physical grasp unavailable")

    def attach(self, object_id: int) -> bool:
        """Legacy alias: close fingers and mark pending attached object."""
        if self.gripper is None:
            return False
        if not self.sim.is_valid_object(object_id):
            print(f"[GRASP] Invalid object {object_id}")
            return False
        self.close()
        self.holding = False
        self.attached_object_id = object_id
        print("[GRASP] Close command issued")
        return True

    def detach(self) -> bool:
        """Legacy alias: open fingers and clear attached object."""
        if self.gripper is None:
            return False
        self.open()
        self.holding = False
        self.attached_object_id = None
        return True

    def open(self) -> None:
        if self.gripper is not None:
            self.gripper.open()

    def close(self, force: Optional[float] = None) -> None:
        if self.gripper is not None:
            self.gripper.close(force=force)

    def is_motion_complete(self) -> bool:
        if self.gripper is None:
            return True
        return self.gripper.is_motion_complete()

    def verify_grasp(self) -> bool:
        if self.gripper is None:
            return False
        return self.gripper.verify_grasp()

    def get_state(self) -> GripperState:
        if self.gripper is None:
            return GripperState(width=0.0, force=0.0, is_closed=False, is_grasping=False)
        return self.gripper.get_state()

    def get_grasp_quality(self) -> float:
        if self.gripper is None:
            return 0.0
        return self.gripper.get_grasp_quality()

    def is_holding(self) -> bool:
        if self.gripper is not None:
            self.holding = self.gripper.verify_grasp()
            if not self.holding:
                self.attached_object_id = None
        return self.holding

    def get_attached_id(self) -> Optional[int]:
        return self.attached_object_id if self.is_holding() else None
