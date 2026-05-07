"""
Hardware bridge tests. All use MockSerialPort - no physical arm required.
"""
from __future__ import annotations

import numpy as np
from unittest.mock import MagicMock

from src.core.authorization import AuthScope, AuthorizationManager
from src.execution.primitive_executor import ExecutorStatus, PrimitiveExecutor
from src.external.openvla.action_translator_fake import FakeActionTranslator
from src.interfaces.primitive import Primitive, PrimitiveType
from src.robot.simulator import ArmState
from src.robot.world_state import WorldState


class RecordingBackend:
    def __init__(self):
        self.commands = []

    def apply_joints(self, commands):
        self.commands.append(commands)

    def emergency_stop(self):
        pass

    def is_connected(self):
        return True


def _openvla_metadata():
    return {
        "delta_position": [0.01, 0.0, -0.02],
        "delta_rotation": [0.0, 0.0, 0.0],
        "gripper": 0.0,
    }


def _world():
    return WorldState(
        arm=ArmState(
            joint_positions=np.zeros(7),
            ee_position=np.array([0.3, 0.0, 0.8]),
            ee_orientation=np.array([0.0, 0.0, 0.0, 1.0]),
        ),
        object=None,
        target_id=None,
        holding=False,
        attached_id=None,
    )


def _auth():
    auth = AuthorizationManager()
    auth.issue(
        source="test",
        quality=1.0,
        scope=AuthScope.TASK_SESSION,
        autonomy_level="A2_TASK_CONFIRM",
        max_objects=0,
    )
    return auth


class TestSimBackend:
    def test_applies_joints_to_mujoco(self):
        from src.execution.hardware_bridge import JointCommand, SimBackend

        mock_data = MagicMock()
        mock_data.qpos = np.zeros(6)
        backend = SimBackend(MagicMock(), mock_data)

        backend.apply_joints([JointCommand.from_radians(0, 1.57)])

        assert abs(mock_data.qpos[0] - 1.57) < 1e-6

    def test_is_always_connected(self):
        from src.execution.hardware_bridge import SimBackend

        backend = SimBackend(MagicMock(), MagicMock())
        assert backend.is_connected()


class TestRealArmBackend:
    def test_delegates_joint_array_to_controller(self):
        from src.execution.hardware_bridge import JointCommand, RealArmBackend
        from src.robot.hardware.arm_controller import HardwareArmController
        from src.robot.hardware.serial_controller_fake import FakeSerialController

        serial = FakeSerialController()
        serial.connect()
        ctrl = HardwareArmController(serial_ctrl=serial, max_step_deg=180.0)
        backend = RealArmBackend(ctrl)

        cmds = [
            JointCommand.from_radians(0, 1.57),
            JointCommand.from_radians(1, 0.78),
        ]
        backend.apply_joints(cmds)

        assert serial.sent_commands == ["JOINT 89.95 44.69 0.00 0.00 0.00 0.00"]

    def test_command_format_matches_canonical_firmware_protocol(self):
        from src.execution.hardware_bridge import JointCommand, RealArmBackend
        from src.robot.hardware.arm_controller import HardwareArmController
        from src.robot.hardware.serial_controller_fake import FakeSerialController

        serial = FakeSerialController()
        serial.connect()
        ctrl = HardwareArmController(serial_ctrl=serial)
        backend = RealArmBackend(ctrl)

        backend.apply_joints([JointCommand.from_radians(i, 0.0) for i in range(6)])

        assert serial.sent_commands[0] == "JOINT 0.00 0.00 0.00 0.00 0.00 0.00"
        assert not any(command.startswith("MOVE") for command in serial.sent_commands)

    def test_emergency_stop_sends_stop_command(self):
        from src.execution.hardware_bridge import RealArmBackend
        from src.robot.hardware.arm_controller import HardwareArmController
        from src.robot.hardware.serial_controller_fake import FakeSerialController

        serial = FakeSerialController()
        serial.connect()
        ctrl = HardwareArmController(serial_ctrl=serial)
        backend = RealArmBackend(ctrl)

        backend.emergency_stop()

        assert "STOP" in serial.sent_commands

    def test_emergency_stop_never_raises(self):
        from src.execution.hardware_bridge import RealArmBackend
        from src.robot.hardware.arm_controller import HardwareArmController
        from src.robot.hardware.serial_controller_fake import FakeSerialController

        backend = RealArmBackend(HardwareArmController(serial_ctrl=FakeSerialController()))
        backend.emergency_stop()

    def test_apply_joints_logs_rejection_without_raising(self):
        from src.execution.hardware_bridge import JointCommand, RealArmBackend
        from src.robot.hardware.arm_controller import HardwareArmController
        from src.robot.hardware.serial_controller_fake import FakeSerialController

        serial = FakeSerialController(simulate_nak_joint=True)
        serial.connect()
        backend = RealArmBackend(HardwareArmController(serial_ctrl=serial))

        backend.apply_joints([JointCommand.from_radians(0, 0.0)])

        assert serial.sent_commands


class TestHardwareBridge:
    def test_clamps_to_joint_limits(self):
        from src.execution.hardware_bridge import HardwareBridge, SimBackend

        mock_data = MagicMock()
        mock_data.qpos = np.zeros(6)
        backend = SimBackend(MagicMock(), mock_data)

        limits = [(-1.57, 1.57)] * 6
        bridge = HardwareBridge(backend, joint_limits=limits)
        bridge.execute(np.array([3.14, 0.0, 0.0, 0.0, 0.0, 0.0]))

        assert abs(mock_data.qpos[0] - 1.57) < 1e-6

    def test_sim_backend_is_default_in_config(self):
        import yaml

        with open("configs/hardware.yaml") as f:
            cfg = yaml.safe_load(f)
        assert cfg["hardware"]["backend"] == "simulator", (
            "hardware.backend must default to 'simulator' - real arm is inactive until connected"
        )

    def test_joint_command_converts_radians_to_degrees(self):
        from src.execution.hardware_bridge import JointCommand

        cmd = JointCommand.from_radians(2, np.pi / 2)
        assert cmd.joint_idx == 2
        assert cmd.angle_rad == np.pi / 2
        assert cmd.angle_deg == 90.0

    def test_bridge_clamps_before_backend(self):
        from src.execution.hardware_bridge import HardwareBridge

        backend = RecordingBackend()
        bridge = HardwareBridge(backend, joint_limits=[(-0.5, 0.5), (-1.0, 1.0)])

        bridge.execute(np.array([2.0, -2.0, 0.25]))

        commands = backend.commands[0]
        assert [cmd.angle_rad for cmd in commands] == [0.5, -1.0, 0.25]

    def test_non_finite_joint_rejected(self):
        from src.execution.hardware_bridge import HardwareBridge

        backend = RecordingBackend()
        bridge = HardwareBridge(backend)

        try:
            bridge.execute(np.array([0.0, np.nan]))
        except ValueError as exc:
            assert "Non-finite" in str(exc)
        else:
            assert False, "Expected ValueError"


class TestExecutorBridgeIntegration:
    def test_executor_uses_hardware_bridge_when_present(self):
        from src.execution.hardware_bridge import HardwareBridge

        bridge_backend = RecordingBackend()
        bridge = HardwareBridge(bridge_backend)

        class ControllerSpy:
            joint_calls = 0

            def move_to_joint_positions(self, _target):
                self.joint_calls += 1
                return True

        executor = PrimitiveExecutor(
            controller=ControllerSpy(),
            grasp=object(),
            action_translator=FakeActionTranslator(),
            authorization_manager=_auth(),
            hardware_bridge=bridge,
        )
        primitive = Primitive(type=PrimitiveType.OPENVLA_TRAJECTORY, metadata=_openvla_metadata())

        executor.start_plan([primitive])
        status = executor.tick(_world())

        assert status == ExecutorStatus.RUNNING
        assert len(bridge_backend.commands) == 1
        assert executor.controller.joint_calls == 0
        assert len(bridge_backend.commands[0]) == 7

    def test_apply_joints_delegates_to_hardware_bridge_execute(self):
        class BridgeSpy:
            def __init__(self):
                self.calls = []

            def execute(self, joint_positions):
                self.calls.append(np.array(joint_positions, dtype=float))

        bridge = BridgeSpy()
        executor = PrimitiveExecutor(
            controller=object(),
            grasp=object(),
            hardware_bridge=bridge,
        )

        used_bridge = executor._apply_joints(np.array([0.1, 0.2]))

        assert used_bridge is True
        assert len(bridge.calls) == 1
        assert np.allclose(bridge.calls[0], np.array([0.1, 0.2]))

    def test_executor_reports_bridge_errors(self):
        from src.execution.hardware_bridge import HardwareBridge

        class FailingBackend(RecordingBackend):
            def apply_joints(self, _commands):
                raise RuntimeError("bridge failed")

        executor = PrimitiveExecutor(
            controller=object(),
            grasp=object(),
            action_translator=FakeActionTranslator(),
            authorization_manager=_auth(),
            hardware_bridge=HardwareBridge(FailingBackend()),
        )
        primitive = Primitive(type=PrimitiveType.OPENVLA_TRAJECTORY, metadata=_openvla_metadata())

        executor.start_plan([primitive])
        status = executor.tick(_world())

        assert status == ExecutorStatus.FAILED
        assert executor.last_error_code == "openvla_hardware_bridge_error"
