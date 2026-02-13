"""
Runtime invariant checker for false_executions == 0.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class InvariantChecker:
    """
    Tracks execution attempts and verifies false_executions == 0.

    A false execution is a motor command sent without a valid token.
    """

    def __init__(self):
        self._total_executions = 0
        self._authorized_executions = 0
        self._blocked_executions = 0
        self._false_executions = 0

    def record_execution_attempt(
        self,
        has_valid_token: bool,
        executed: bool,
        token_id: str = "",
    ) -> None:
        """Record one execution attempt outcome."""
        self._total_executions += 1

        if has_valid_token and executed:
            self._authorized_executions += 1
        elif not has_valid_token and not executed:
            self._blocked_executions += 1
        elif has_valid_token and not executed:
            # Legitimate failure (IK/convergence/etc.), not a false execution.
            return
        else:
            self._false_executions += 1
            logger.critical(
                "FALSE EXECUTION DETECTED! token_id=%s total_false=%d",
                token_id,
                self._false_executions,
            )

    def assert_invariant(self) -> None:
        """Raise if false_executions is non-zero."""
        assert self._false_executions == 0, (
            f"INVARIANT VIOLATED: false_executions = {self._false_executions}. "
            f"Total attempts: {self._total_executions}, "
            f"authorized: {self._authorized_executions}, "
            f"blocked: {self._blocked_executions}"
        )

    @property
    def false_executions(self) -> int:
        return self._false_executions

    @property
    def summary(self) -> dict:
        return {
            "total_attempts": self._total_executions,
            "authorized": self._authorized_executions,
            "blocked": self._blocked_executions,
            "false_executions": self._false_executions,
            "invariant_holds": self._false_executions == 0,
        }

