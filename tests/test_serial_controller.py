from __future__ import annotations

import types

import numpy as np

from src.robot.hardware.serial_controller import SerialConfig, SerialController
from src.robot.hardware.serial_controller_fake import FakeSerialController


class MockSerialPort:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.written = []
        self.is_open = True
        self.timeout = None
        self.reset_count = 0
        self.flushed = 0

    def reset_input_buffer(self):
        self.reset_count += 1

    def write(self, data: bytes):
        self.written.append(data.decode("ascii"))

    def flush(self):
        self.flushed += 1

    def readline(self):
        if self.responses:
            return self.responses.pop(0).encode("ascii")
        return b""

    def close(self):
        self.is_open = False


def _controller(serial_port: MockSerialPort) -> SerialController:
    ctl = SerialController(SerialConfig(port="/dev/mock", arduino_reset_delay_s=0.0, max_retries=0))
    ctl._serial = serial_port
    ctl._connected = True
    return ctl


def test_connect_sends_ping_and_accepts_pong(monkeypatch):
    serial_port = MockSerialPort(["OK PONG\n"])
    fake_serial_module = types.SimpleNamespace(Serial=lambda *args, **kwargs: serial_port)
    monkeypatch.setitem(__import__("sys").modules, "serial", fake_serial_module)

    ctl = SerialController(SerialConfig(port="/dev/mock", arduino_reset_delay_s=0.0))

    assert ctl.connect()
    assert ctl.is_connected
    assert serial_port.written == ["PING\n"]


def test_ping_returns_true_on_ok_pong():
    ctl = _controller(MockSerialPort(["OK PONG\n"]))
    assert ctl.ping()


def test_send_joint_angles_uses_canonical_joint_protocol():
    serial_port = MockSerialPort(["OK\n"])
    ctl = _controller(serial_port)

    assert ctl.send_joint_angles(np.array([0, 1.234, -2.0]))
    assert serial_port.written == ["JOINT 0.00 1.23 -2.00\n"]


def test_joint_err_returns_false():
    ctl = _controller(MockSerialPort(["ERR out of range\n"]))
    assert not ctl.send_joint_angles(np.array([999.0]))


def test_home_uses_ack_timeout():
    serial_port = MockSerialPort(["OK\n"])
    ctl = _controller(serial_port)
    ctl._cfg = SerialConfig(port="/dev/mock", ack_timeout_s=9.0, max_retries=0)

    assert ctl.send_home()
    assert serial_port.timeout == 9.0
    assert serial_port.written == ["HOME\n"]


def test_gripper_commands_open_and_close():
    serial_port = MockSerialPort(["OK\n", "OK\n"])
    ctl = _controller(serial_port)

    assert ctl.send_gripper(True)
    assert ctl.send_gripper(False)
    assert serial_port.written == ["GRIPPER open\n", "GRIPPER close\n"]


def test_stop_fire_and_forget_never_reads():
    serial_port = MockSerialPort(["OK SHOULD_NOT_READ\n"])
    ctl = _controller(serial_port)

    ctl.send_stop()

    assert serial_port.written == ["STOP\n"]
    assert serial_port.responses == ["OK SHOULD_NOT_READ\n"]


def test_stop_never_raises_when_disconnected():
    ctl = SerialController(SerialConfig(port="/dev/mock"))
    ctl.send_stop()


def test_query_position_parses_degrees():
    ctl = _controller(MockSerialPort(["OK POS 1 2.5 -3\n"]))
    pos = ctl.query_position()
    assert np.allclose(pos, np.array([1.0, 2.5, -3.0]))


def test_query_limits_parses_pairs():
    ctl = _controller(MockSerialPort(["OK LIMITS -90 90 -45 45\n"]))
    assert ctl.query_limits() == [(-90.0, 90.0), (-45.0, 45.0)]


def test_timeout_returns_none_after_retries():
    serial_port = MockSerialPort([])
    ctl = SerialController(SerialConfig(port="/dev/mock", max_retries=1))
    ctl._serial = serial_port
    ctl._connected = True

    assert ctl.ping() is False
    assert serial_port.written == ["PING\n", "PING\n"]


def test_serial_io_error_marks_disconnected():
    class BadSerial(MockSerialPort):
        def write(self, data: bytes):
            raise RuntimeError("boom")

    ctl = _controller(BadSerial(["OK\n"]))
    assert ctl.ping() is False
    assert not ctl.is_connected


class TestFakeSerialController:
    def test_connect_succeeds(self):
        ctrl = FakeSerialController()
        assert ctrl.connect()
        assert ctrl.is_connected

    def test_ping_returns_true_when_connected(self):
        ctrl = FakeSerialController()
        ctrl.connect()
        assert ctrl.ping()

    def test_send_joint_angles_records_command(self):
        ctrl = FakeSerialController()
        ctrl.connect()
        angles = np.array([0.0, 45.0, 90.0, -45.0, 0.0, 0.0])
        assert ctrl.send_joint_angles(angles)
        assert any("JOINT" in cmd for cmd in ctrl.sent_commands)

    def test_stop_always_records_command(self):
        ctrl = FakeSerialController()
        ctrl.connect()
        ctrl.send_stop()
        assert "STOP" in ctrl.sent_commands

    def test_stop_never_raises_when_disconnected(self):
        ctrl = FakeSerialController()
        ctrl.send_stop()

    def test_joint_nak_returns_false(self):
        ctrl = FakeSerialController(simulate_nak_joint=True)
        ctrl.connect()
        assert not ctrl.send_joint_angles(np.zeros(6))

    def test_query_position_returns_array(self):
        ctrl = FakeSerialController()
        ctrl.connect()
        pos = ctrl.query_position()
        assert pos is not None
        assert isinstance(pos, np.ndarray)

    def test_command_format_joint(self):
        ctrl = FakeSerialController()
        ctrl.connect()
        ctrl.send_joint_angles(np.array([90.0, 0.0, 45.0, -30.0, 0.0, 0.0]))
        joint_cmds = [c for c in ctrl.sent_commands if c.startswith("JOINT")]
        assert len(joint_cmds) == 1
        parts = joint_cmds[0].split()
        assert parts[0] == "JOINT"
        assert len(parts) == 7
        assert parts[1] == "90.00"
