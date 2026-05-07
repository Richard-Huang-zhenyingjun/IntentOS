"""
AttentionBudget - rate-limits human interruption.

This class decides whether to interrupt the human now or defer until a natural
pause. Safety events always bypass the budget.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional


logger = logging.getLogger(__name__)

# TUNING TARGETS (adjust from measurement data):
# MAX_CONFIRMATIONS_PER_MINUTE: start at 3.0, lower if human reports feeling rushed.
# MIN_COOLDOWN_BETWEEN_INTERRUPTS_S: start at 20.0, raise if confirmation feels too frequent.
# LOAD_PER_CONFIRM: 0.25 is the baseline; lower only if the system becomes too conservative.
# LOAD_DECAY_PER_SECOND: 0.05 lets load clear in about 20s; lower if humans need more recovery.
#
# Current values are baseline defaults pending 5+ real 3C/3D sessions. Do not
# treat them as final tuning until session logs show comfort, response time,
# deferred interrupt frequency, and confirmations/minute.
MAX_CONFIRMATIONS_PER_MINUTE = 3.0
MIN_COOLDOWN_BETWEEN_INTERRUPTS_S = 20.0
LOAD_PER_CONFIRM = 0.25
LOAD_DECAY_PER_SECOND = 0.05


class InterruptClass:
    SAFETY = "safety"
    CHECKPOINT = "checkpoint"
    INFO = "info"


@dataclass
class InterruptRequest:
    request_id: str
    interrupt_class: str
    message: str
    created_at: float
    deferred: bool = False


class AttentionBudget:
    """Rate-limits human interruption while never blocking safety events."""

    def __init__(
        self,
        max_confirms_per_minute: float = MAX_CONFIRMATIONS_PER_MINUTE,
        cooldown_s: float = MIN_COOLDOWN_BETWEEN_INTERRUPTS_S,
    ):
        self._max_per_minute = max_confirms_per_minute
        self._cooldown_s = cooldown_s
        self._confirm_times: deque[float] = deque(maxlen=100)
        self._last_interrupt_at: float = 0.0
        self._cognitive_load: float = 0.0
        self._deferred: list[InterruptRequest] = []

    def can_interrupt(
        self,
        interrupt_class: str,
        current_time: Optional[float] = None,
    ) -> bool:
        """Return True if the system may interrupt the human now."""
        now = current_time if current_time is not None else time.monotonic()

        if interrupt_class == InterruptClass.SAFETY:
            return True
        if interrupt_class == InterruptClass.INFO:
            return False

        self._update_load(now)

        recent = sum(1 for confirm_time in self._confirm_times if now - confirm_time < 60.0)
        if recent >= self._max_per_minute:
            logger.debug("Attention budget: rate limit reached (%d/min)", recent)
            return False

        if now - self._last_interrupt_at < self._cooldown_s:
            logger.debug(
                "Attention budget: cooldown active (%.1fs remaining)",
                self._cooldown_s - (now - self._last_interrupt_at),
            )
            return False

        if self._cognitive_load > 0.8:
            logger.debug(
                "Attention budget: cognitive load too high (%.2f)",
                self._cognitive_load,
            )
            return False

        return True

    def record_interrupt(self, current_time: Optional[float] = None) -> None:
        """Call when an interrupt is actually shown to the human."""
        now = current_time if current_time is not None else time.monotonic()
        self._update_load(now)
        self._confirm_times.append(now)
        self._last_interrupt_at = now
        self._cognitive_load = min(1.0, self._cognitive_load + LOAD_PER_CONFIRM)
        rate = sum(
            1 for confirm_time in self._confirm_times if now - confirm_time < 60.0
        )
        logger.info(
            "Attention event: confirmation recorded | "
            "load=%.2f | rate=%.1f/min | cooldown=%.0fs",
            self._cognitive_load,
            float(rate),
            self._cooldown_s,
        )

    def defer(self, request: InterruptRequest) -> None:
        """Queue an interrupt for the next natural pause."""
        request.deferred = True
        self._deferred.append(request)
        logger.info("Interrupt deferred: %s", request.message[:60])

    def flush_deferred(
        self,
        current_time: Optional[float] = None,
    ) -> list[InterruptRequest]:
        """Return queued interrupts if the budget allows at a segment boundary."""
        now = current_time if current_time is not None else time.monotonic()
        if not self._deferred:
            return []
        if not self.can_interrupt(InterruptClass.CHECKPOINT, now):
            return []

        flushed = list(self._deferred)
        self._deferred.clear()
        return flushed

    @property
    def cognitive_load(self) -> float:
        self._update_load(time.monotonic())
        return self._cognitive_load

    def _update_load(self, current_time: float) -> None:
        """Decay cognitive load over time."""
        elapsed = max(0.0, current_time - self._last_interrupt_at)
        self._cognitive_load = max(
            0.0,
            self._cognitive_load - LOAD_DECAY_PER_SECOND * elapsed,
        )
