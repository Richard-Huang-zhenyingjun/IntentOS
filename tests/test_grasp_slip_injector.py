"""Tests for GraspSlipInjector and the recovery path it exercises."""

from src.intentos.recovery import FailureClass, MAX_RETRIES_PER_NODE, RecoveryEngine
from src.robot.grasp_slip_injector import GraspSlipInjector
from src.task_graph.types import TaskNode


class _FakeGrasp:
    """Minimal stand-in for GraspController. verify_grasp() normally succeeds."""

    def __init__(self):
        self.calls = []
        self.holding = True
        self.attached_object_id = 7

    def verify_grasp(self):
        self.calls.append("verify")
        return True

    def close(self, force=None):
        self.calls.append(("close", force))

    def open(self):
        self.calls.append("open")

    def get_state(self):
        self.calls.append("get_state")
        return "STATE"

    def is_holding(self):
        return self.holding


def test_fails_only_on_configured_attempt():
    grasp = GraspSlipInjector(_FakeGrasp(), fail_on_attempts={1})
    assert grasp.verify_grasp() is False
    assert grasp.verify_grasp() is True


def test_fails_on_multiple_configured_attempts():
    grasp = GraspSlipInjector(_FakeGrasp(), fail_on_attempts={1, 3})
    assert grasp.verify_grasp() is False
    assert grasp.verify_grasp() is True
    assert grasp.verify_grasp() is False
    assert grasp.verify_grasp() is True


def test_always_never_holds():
    grasp = GraspSlipInjector(_FakeGrasp(), fail_on_attempts="always")
    for _ in range(5):
        assert grasp.verify_grasp() is False


def test_none_is_pure_passthrough():
    grasp = GraspSlipInjector(_FakeGrasp(), fail_on_attempts=None)
    assert grasp.verify_grasp() is True
    assert grasp.verify_grasp() is True


def test_reset_injection_restarts_counter():
    grasp = GraspSlipInjector(_FakeGrasp(), fail_on_attempts={1})
    assert grasp.verify_grasp() is False
    assert grasp.verify_grasp() is True
    grasp.reset_injection()
    assert grasp.verify_grasp() is False


def test_other_methods_pass_through():
    inner = _FakeGrasp()
    grasp = GraspSlipInjector(inner, fail_on_attempts={1})

    grasp.close(force=30.0)
    grasp.open()
    grasp.get_state()

    assert ("close", 30.0) in inner.calls
    assert "open" in inner.calls
    assert "get_state" in inner.calls


def test_unwrapped_attributes_pass_through():
    inner = _FakeGrasp()
    grasp = GraspSlipInjector(inner, fail_on_attempts={1})

    assert grasp.attached_object_id == 7
    assert grasp.holding is True


def _grasp_node():
    return TaskNode(
        node_id="grasp_0",
        action_type="grasp",
        parameters={"target": "object_4"},
        agent_id="arm",
        depends_on=[],
    )


def test_grasp_slip_classifies_transient_then_escalation():
    """A plain grasp slip retries through the configured budget, then escalates."""
    engine = RecoveryEngine()
    engine.reset_plan()
    node = _grasp_node()

    for attempt in range(1, MAX_RETRIES_PER_NODE):
        decision = engine.classify(node, graph=None, failure_reason="grasp slipped")
        assert decision.failure_class == FailureClass.TRANSIENT
        assert decision.retry_count == attempt

    final = engine.classify(node, graph=None, failure_reason="grasp slipped")
    assert final.failure_class == FailureClass.ESCALATION
    assert "intervention" in final.message.lower()
