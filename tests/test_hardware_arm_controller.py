"""Tests for HardwareArmController using FakeSerialController."""
import numpy as np
import pytest

from src.robot.hardware.arm_controller import HardwareArmController
from src.robot.hardware.serial_controller_fake import FakeSerialController


@pytest.fixture
def fake_ctrl():
    serial = FakeSerialController()
    serial.connect()
    return HardwareArmController(serial_ctrl=serial)


class TestLimitClamping:
    def test_within_limits_passes(self, fake_ctrl):
        assert fake_ctrl.move_to_joint_positions(np.zeros(6))

    def test_beyond_limit_clamped_not_rejected(self, fake_ctrl):
        positions_rad = np.array([np.radians(180), 0, 0, 0, 0, 0])
        assert fake_ctrl.move_to_joint_positions(positions_rad)
        sent = [c for c in fake_ctrl._serial.sent_commands if c.startswith("JOINT")]
        assert sent
        angle_sent = float(sent[-1].split()[1])
        assert abs(angle_sent - 90.0) < 0.1

    def test_stat_increments_on_clamp(self, fake_ctrl):
        positions_rad = np.array([np.radians(180), 0, 0, 0, 0, 0])
        fake_ctrl.move_to_joint_positions(positions_rad)
        assert fake_ctrl.stats.moves_clamped >= 1


class TestStepSegmentation:
    def test_large_step_segmented(self, fake_ctrl):
        positions_rad = np.array([np.radians(30), 0, 0, 0, 0, 0])
        assert fake_ctrl.move_to_joint_positions(positions_rad)
        assert fake_ctrl.stats.moves_segmented == 1
        sent = [c for c in fake_ctrl._serial.sent_commands if c.startswith("JOINT")]
        assert len(sent) == 3
        assert abs(float(sent[-1].split()[1]) - 30.0) < 0.1

    def test_segment_steps_respect_max_step(self, fake_ctrl):
        positions_rad = np.array([np.radians(90), 0, 0, 0, 0, 0])
        assert fake_ctrl.move_to_joint_positions(positions_rad)
        sent = [c for c in fake_ctrl._serial.sent_commands if c.startswith("JOINT")]
        angles = [float(cmd.split()[1]) for cmd in sent]
        deltas = np.diff([0.0] + angles)
        assert max(abs(delta) for delta in deltas) <= 10.1

    def test_small_step_accepted(self, fake_ctrl):
        positions_rad = np.array([np.radians(10), 0, 0, 0, 0, 0])
        assert fake_ctrl.move_to_joint_positions(positions_rad)

    def test_cumulative_small_steps_accepted(self, fake_ctrl):
        for i in range(3):
            pos = np.array([np.radians((i + 1) * 10), 0, 0, 0, 0, 0])
            assert fake_ctrl.move_to_joint_positions(pos)


class TestEmergencyStop:
    def test_stop_never_raises_when_disconnected(self):
        serial = FakeSerialController()
        ctrl = HardwareArmController(serial_ctrl=serial)
        ctrl.emergency_stop()
        assert "STOP" in serial.sent_commands

    def test_stop_increments_stat(self, fake_ctrl):
        fake_ctrl.emergency_stop()
        assert fake_ctrl.stats.emergency_stops == 1


class TestUnitConversion:
    def test_get_position_returns_radians(self, fake_ctrl):
        pos = fake_ctrl.get_joint_positions()
        assert np.allclose(pos, np.zeros(6))

    def test_move_converts_radians_to_degrees_in_command(self, fake_ctrl):
        serial = FakeSerialController()
        serial.connect()
        ctrl = HardwareArmController(serial_ctrl=serial, max_step_deg=60.0)
        ctrl.move_to_joint_positions(np.array([np.radians(45), 0, 0, 0, 0, 0]))
        sent = [c for c in serial.sent_commands if c.startswith("JOINT")]
        angle_sent = float(sent[-1].split()[1])
        assert abs(angle_sent - 45.0) < 0.1


def test_connect_loads_firmware_limits():
    serial = FakeSerialController()
    ctrl = HardwareArmController(serial_ctrl=serial)
    assert ctrl.connect()
    assert ctrl._limits_deg == [(-90.0, 90.0)] * 6


def test_nak_tracks_stat():
    serial = FakeSerialController(simulate_nak_joint=True)
    serial.connect()
    ctrl = HardwareArmController(serial_ctrl=serial)
    assert not ctrl.move_to_joint_positions(np.zeros(6))
    assert ctrl.stats.naks_received == 1


def test_nak_does_not_update_current_position():
    class FailOnSecond(FakeSerialController):
        def send_joint_angles(self, angles_deg):
            self.sent_commands.append(
                "JOINT " + " ".join(f"{float(angle):.2f}" for angle in angles_deg)
            )
            return len(self.sent_commands) < 2

    serial = FailOnSecond()
    serial.connect()
    ctrl = HardwareArmController(serial_ctrl=serial)

    assert not ctrl.move_to_joint_positions(np.array([np.radians(30), 0, 0, 0, 0, 0]))
    assert np.allclose(ctrl.current_position_rad, np.zeros(6))


class TestSegmentation:
    """Verifies the clamped-step bypass is fixed."""

    def test_large_move_is_segmented_not_rejected(self):
        serial = FakeSerialController()
        serial.connect()
        ctrl = HardwareArmController(serial_ctrl=serial, max_step_deg=10.0)

        target = np.array([np.radians(90), 0, 0, 0, 0, 0])
        result = ctrl.move_to_joint_positions(target)

        assert result, "Large move should succeed via segmentation, not be rejected"
        joint_cmds = [c for c in serial.sent_commands if c.startswith("JOINT")]
        assert len(joint_cmds) >= 9, (
            f"Expected >= 9 segments for 90 degree move at 10 degree/step, got {len(joint_cmds)}"
        )
        assert ctrl.stats.moves_segmented == 1
        assert ctrl.stats.moves_succeeded == 1

    def test_clamped_target_still_applies_step_limit(self):
        serial = FakeSerialController()
        serial.connect()
        ctrl = HardwareArmController(
            serial_ctrl=serial,
            limits_deg=[(-90, 90)] + [(-90, 90)] * 5,
            max_step_deg=10.0,
        )

        target = np.array([np.radians(180), 0, 0, 0, 0, 0])
        result = ctrl.move_to_joint_positions(target)

        assert result, "Clamped move should succeed via segmentation"
        joint_cmds = [c for c in serial.sent_commands if c.startswith("JOINT")]
        angles = [float(c.split()[1]) for c in joint_cmds]
        for i in range(1, len(angles)):
            step = abs(angles[i] - angles[i - 1])
            assert step <= 10.1, (
                f"Step between segments {i - 1} and {i} was {step:.2f} degrees > 10 degrees"
            )
        assert abs(angles[-1] - 90.0) < 0.1, (
            f"Final angle should be 90 degrees (limit), got {angles[-1]:.2f} degrees"
        )

    def test_small_move_not_segmented(self):
        serial = FakeSerialController()
        serial.connect()
        ctrl = HardwareArmController(serial_ctrl=serial, max_step_deg=15.0)

        target = np.array([np.radians(10), 0, 0, 0, 0, 0])
        result = ctrl.move_to_joint_positions(target)

        assert result
        joint_cmds = [c for c in serial.sent_commands if c.startswith("JOINT")]
        assert len(joint_cmds) == 1, "Small move should send exactly one command"
        assert ctrl.stats.moves_segmented == 0

    def test_nak_mid_segment_halts_and_returns_false(self):
        serial = FakeSerialController(simulate_nak_joint=True)
        serial.connect()
        ctrl = HardwareArmController(serial_ctrl=serial, max_step_deg=10.0)

        target = np.array([np.radians(90), 0, 0, 0, 0, 0])
        result = ctrl.move_to_joint_positions(target)

        assert not result, "Move should fail when firmware NAKs"
        assert np.allclose(ctrl._current_deg, np.zeros(6))
        assert ctrl.stats.naks_received >= 1

    def test_segments_follow_straight_joint_space_path(self):
        serial = FakeSerialController()
        serial.connect()
        ctrl = HardwareArmController(serial_ctrl=serial, max_step_deg=10.0)

        target = np.array([np.radians(30), np.radians(20), 0, 0, 0, 0])
        ctrl.move_to_joint_positions(target)

        joint_cmds = [c for c in serial.sent_commands if c.startswith("JOINT")]
        for cmd in joint_cmds[:-1]:
            parts = cmd.split()
            j0 = float(parts[1])
            j1 = float(parts[2])
            if abs(j1) > 0.1:
                ratio = j0 / j1
                assert abs(ratio - 1.5) < 0.2, (
                    f"Expected j0/j1 ratio around 1.5, got {ratio:.2f}"
                )

    def test_compute_segments_is_pure(self):
        ctrl = HardwareArmController(serial_ctrl=FakeSerialController(), max_step_deg=10.0)
        current = np.zeros(6)
        target = np.array([30.0, 20.0, 0.0, 0.0, 0.0, 0.0])

        first = ctrl._compute_segments(current, target)
        second = ctrl._compute_segments(current, target)

        assert len(first) == len(second)
        for left, right in zip(first, second):
            assert np.allclose(left, right)

    def test_clamp_runs_before_segment_computation(self):
        class OrderTrackingController(HardwareArmController):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.order = []

            def _clamp_to_limits(self, target_deg):
                self.order.append("clamp")
                return super()._clamp_to_limits(target_deg)

            def _compute_segments(self, current_deg, target_deg):
                self.order.append("segments")
                return super()._compute_segments(current_deg, target_deg)

        serial = FakeSerialController()
        serial.connect()
        ctrl = OrderTrackingController(serial_ctrl=serial, max_step_deg=10.0)

        ctrl.move_to_joint_positions(np.array([np.radians(90), 0, 0, 0, 0, 0]))

        assert ctrl.order[:2] == ["clamp", "segments"]


class TestRealArmBackendWrapper:
    """Verify RealArmBackend delegates to HardwareArmController correctly."""

    def test_real_arm_backend_uses_joint_protocol(self):
        from src.execution.hardware_bridge import JointCommand, RealArmBackend

        serial = FakeSerialController()
        serial.connect()
        ctrl = HardwareArmController(serial_ctrl=serial, max_step_deg=15.0)
        backend = RealArmBackend(ctrl)

        cmds = [JointCommand.from_radians(i, 0.0) for i in range(6)]
        backend.apply_joints(cmds)

        assert any(c.startswith("JOINT") for c in serial.sent_commands), (
            "RealArmBackend must use JOINT protocol via HardwareArmController"
        )
        assert not any(c.startswith("MOVE") for c in serial.sent_commands), (
            "Old protocol must not appear because it conflicts with firmware"
        )

    def test_emergency_stop_delegates(self):
        from src.execution.hardware_bridge import RealArmBackend

        serial = FakeSerialController()
        serial.connect()
        ctrl = HardwareArmController(serial_ctrl=serial)
        backend = RealArmBackend(ctrl)

        backend.emergency_stop()
        assert "STOP" in serial.sent_commands
