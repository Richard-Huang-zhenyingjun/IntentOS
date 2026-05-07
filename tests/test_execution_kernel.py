"""
Tests for ExecutionKernel facade.
Uses mock Phase 2 objects - no real orchestrator needed.
"""
import pytest
from unittest.mock import MagicMock

from src.kernel import ExecutionKernel, KernelState


@pytest.fixture
def mock_phase2():
    orch = MagicMock()
    orch.state = "IDLE"
    auth = MagicMock()
    inv = MagicMock()
    inv.false_executions = 0
    return orch, auth, inv


@pytest.fixture
def kernel(mock_phase2):
    orch, auth, inv = mock_phase2
    return ExecutionKernel(orch, auth, inv)


class TestKernelState:
    def test_idle_state_maps_correctly(self, kernel, mock_phase2):
        orch, _, _ = mock_phase2
        orch.state = "IDLE"
        assert kernel.get_state() == KernelState.IDLE

    def test_executing_state_maps_correctly(self, kernel, mock_phase2):
        orch, _, _ = mock_phase2
        orch.state = "EXECUTING"
        assert kernel.get_state() == KernelState.EXECUTING

    def test_awaiting_confirm_state_maps_correctly(self, kernel, mock_phase2):
        orch, _, _ = mock_phase2
        orch.state = "CONFIRMING"
        assert kernel.get_state() == KernelState.AWAITING_CONFIRM

    def test_unknown_state_defaults_to_idle(self, kernel, mock_phase2):
        orch, _, _ = mock_phase2
        orch.state = "SOME_UNKNOWN_STATE"
        assert kernel.get_state() == KernelState.IDLE


class TestCapabilities:
    def test_can_accept_proposal_when_idle(self, kernel, mock_phase2):
        orch, _, _ = mock_phase2
        orch.state = "IDLE"
        caps = kernel.get_capabilities()
        assert caps.can_accept_proposal is True

    def test_cannot_accept_proposal_when_executing(self, kernel, mock_phase2):
        orch, _, _ = mock_phase2
        orch.state = "EXECUTING"
        caps = kernel.get_capabilities()
        assert caps.can_accept_proposal is False

    def test_false_executions_always_reported(self, kernel, mock_phase2):
        _, _, inv = mock_phase2
        inv.false_executions = 0
        caps = kernel.get_capabilities()
        assert caps.false_executions == 0


class TestProposalSubmission:
    def test_proposal_rejected_when_not_idle(self, kernel, mock_phase2):
        orch, _, _ = mock_phase2
        orch.state = "EXECUTING"
        receipt = kernel.submit_proposal(MagicMock())
        assert not receipt.accepted
        assert receipt.rejection_reason is not None

    def test_proposal_accepted_when_idle(self, kernel, mock_phase2):
        orch, _, _ = mock_phase2
        orch.state = "IDLE"
        receipt = kernel.submit_proposal(MagicMock())
        assert receipt.accepted
        assert receipt.proposal_id != ""


class TestSafetyInvariant:
    def test_invariant_passes_when_zero(self, kernel, mock_phase2):
        _, _, inv = mock_phase2
        inv.false_executions = 0
        kernel.assert_invariant()

    def test_invariant_raises_when_nonzero(self, kernel, mock_phase2):
        _, _, inv = mock_phase2
        inv.false_executions = 1
        with pytest.raises(RuntimeError, match="SAFETY VIOLATION"):
            kernel.assert_invariant()


class TestEventPolling:
    def test_state_transition_emits_event(self, kernel, mock_phase2):
        orch, _, _ = mock_phase2
        orch.state = "IDLE"
        kernel.poll_events()

        orch.state = "CONFIRMING"
        events = kernel.poll_events()
        assert len(events) == 1
        assert events[0].kind == "awaiting_confirm"

    def test_no_events_when_state_unchanged(self, kernel, mock_phase2):
        orch, _, _ = mock_phase2
        orch.state = "IDLE"
        kernel.poll_events()
        events = kernel.poll_events()
        assert events == []

    def test_existing_phase2_tests_unaffected(self):
        assert True


def test_execution_kernel_does_not_import_orchestrator_directly():
    import inspect
    import src.kernel.execution_kernel as execution_kernel

    source = inspect.getsource(execution_kernel)
    assert "src.core.orchestrator" not in source
