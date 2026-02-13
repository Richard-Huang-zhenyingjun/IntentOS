"""Tests for the runtime invariant checker."""

from __future__ import annotations

import pytest

from src.core.invariant_checker import InvariantChecker


class TestInvariantChecker:
    def test_starts_clean(self):
        c = InvariantChecker()
        assert c.false_executions == 0
        c.assert_invariant()

    def test_authorized_execution_passes(self):
        c = InvariantChecker()
        c.record_execution_attempt(has_valid_token=True, executed=True, token_id="t1")
        assert c.false_executions == 0
        c.assert_invariant()

    def test_blocked_execution_passes(self):
        c = InvariantChecker()
        c.record_execution_attempt(has_valid_token=False, executed=False, token_id="")
        assert c.false_executions == 0
        c.assert_invariant()

    def test_false_execution_detected(self):
        c = InvariantChecker()
        c.record_execution_attempt(has_valid_token=False, executed=True, token_id="bad")
        assert c.false_executions == 1
        with pytest.raises(AssertionError, match="INVARIANT VIOLATED"):
            c.assert_invariant()

    def test_multiple_authorized_no_false(self):
        c = InvariantChecker()
        for i in range(100):
            c.record_execution_attempt(
                has_valid_token=True,
                executed=True,
                token_id=f"t{i}",
            )
        assert c.false_executions == 0
        c.assert_invariant()

    def test_mixed_authorized_and_blocked(self):
        c = InvariantChecker()
        c.record_execution_attempt(has_valid_token=True, executed=True)
        c.record_execution_attempt(has_valid_token=False, executed=False)
        c.record_execution_attempt(has_valid_token=True, executed=True)
        c.record_execution_attempt(has_valid_token=False, executed=False)
        assert c.false_executions == 0
        c.assert_invariant()

    def test_summary_accurate(self):
        c = InvariantChecker()
        c.record_execution_attempt(has_valid_token=True, executed=True)
        c.record_execution_attempt(has_valid_token=True, executed=True)
        c.record_execution_attempt(has_valid_token=False, executed=False)
        s = c.summary
        assert s["total_attempts"] == 3
        assert s["authorized"] == 2
        assert s["blocked"] == 1
        assert s["false_executions"] == 0
        assert s["invariant_holds"] is True

    def test_failed_execution_with_valid_token_is_not_false(self):
        """Token valid but execution failed (IK/convergence) is not false execution."""
        c = InvariantChecker()
        c.record_execution_attempt(has_valid_token=True, executed=False)
        assert c.false_executions == 0
        c.assert_invariant()

