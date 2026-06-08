"""Fault injector that makes selected grasp verification attempts fail."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class GraspSlipInjector:
    """
    Wrap a GraspController and inject verify_grasp() failures.

    Every method delegates to the wrapped controller except verify_grasp(),
    which can be forced to fail on configured 1-based attempt numbers or on
    every attempt with fail_on_attempts="always".
    """

    def __init__(self, inner, fail_on_attempts=None):
        self._inner = inner
        self._always = fail_on_attempts == "always"
        if self._always or fail_on_attempts is None:
            self._fail_on = set()
        else:
            self._fail_on = set(int(attempt) for attempt in fail_on_attempts)
        self._verify_attempts = 0

    def verify_grasp(self) -> bool:
        """Pass through to the real verify, unless this attempt is injected."""
        self._verify_attempts += 1
        attempt = self._verify_attempts

        if self._always or attempt in self._fail_on:
            logger.info(
                "[SLIP-INJECT] Forcing grasp slip on verify attempt %d",
                attempt,
            )
            print(f"[SLIP-INJECT] Grip slipped on attempt {attempt} (injected)")
            return False

        return self._inner.verify_grasp()

    def reset_injection(self) -> None:
        """Reset the attempt counter between separate plans or sessions."""
        self._verify_attempts = 0

    def attach(self, object_id):
        return self._inner.attach(object_id)

    def detach(self):
        return self._inner.detach()

    def open(self):
        return self._inner.open()

    def close(self, force=None):
        return self._inner.close(force=force)

    def is_motion_complete(self):
        return self._inner.is_motion_complete()

    def get_state(self):
        return self._inner.get_state()

    def get_grasp_quality(self):
        return self._inner.get_grasp_quality()

    def is_holding(self):
        return self._inner.is_holding()

    def get_attached_id(self):
        return self._inner.get_attached_id()

    def __getattr__(self, name):
        return getattr(self._inner, name)
