"""Tests for AttentionBudget."""
import logging

from src.intentos import AttentionBudget, InterruptClass, InterruptRequest
from src.intentos.attention_budget import LOAD_DECAY_PER_SECOND, LOAD_PER_CONFIRM


def request(request_id="r1", cls=InterruptClass.CHECKPOINT):
    return InterruptRequest(
        request_id=request_id,
        interrupt_class=cls,
        message=f"message {request_id}",
        created_at=0.0,
    )


def test_safety_always_can_interrupt_even_during_cooldown_and_rate_limit():
    budget = AttentionBudget(max_confirms_per_minute=1, cooldown_s=100.0)
    budget.record_interrupt(current_time=10.0)

    assert budget.can_interrupt(InterruptClass.SAFETY, current_time=10.1)


def test_info_never_interrupts():
    budget = AttentionBudget(cooldown_s=0.0)

    assert not budget.can_interrupt(InterruptClass.INFO, current_time=100.0)


def test_rate_limit_enforced_for_confirmations_in_last_minute():
    budget = AttentionBudget(max_confirms_per_minute=2, cooldown_s=0.0)
    budget.record_interrupt(current_time=10.0)
    budget.record_interrupt(current_time=20.0)

    assert not budget.can_interrupt(InterruptClass.CHECKPOINT, current_time=30.0)
    assert budget.can_interrupt(InterruptClass.CHECKPOINT, current_time=71.0)


def test_cooldown_enforced_between_non_safety_interrupts():
    budget = AttentionBudget(max_confirms_per_minute=10, cooldown_s=20.0)
    budget.record_interrupt(current_time=100.0)

    assert not budget.can_interrupt(InterruptClass.CHECKPOINT, current_time=119.0)
    assert budget.can_interrupt(InterruptClass.CHECKPOINT, current_time=121.0)


def test_high_cognitive_load_blocks_non_safety():
    budget = AttentionBudget(max_confirms_per_minute=10, cooldown_s=0.0)
    for idx in range(4):
        budget.record_interrupt(current_time=float(idx))

    assert budget._cognitive_load > 0.8
    assert not budget.can_interrupt(InterruptClass.CHECKPOINT, current_time=3.1)
    assert budget.can_interrupt(InterruptClass.SAFETY, current_time=3.1)


def test_record_interrupt_adds_load_and_tracks_time():
    budget = AttentionBudget(cooldown_s=0.0)

    budget.record_interrupt(current_time=10.0)

    assert budget._last_interrupt_at == 10.0
    assert list(budget._confirm_times) == [10.0]
    assert budget._cognitive_load == LOAD_PER_CONFIRM


def test_record_interrupt_logs_measurement_event(caplog):
    budget = AttentionBudget(cooldown_s=20.0)

    with caplog.at_level(logging.INFO):
        budget.record_interrupt(current_time=10.0)

    assert "Attention event: confirmation recorded" in caplog.text
    assert "load=0.25" in caplog.text
    assert "rate=1.0/min" in caplog.text
    assert "cooldown=20s" in caplog.text


def test_cognitive_load_decays_over_time():
    budget = AttentionBudget(cooldown_s=0.0)
    budget.record_interrupt(current_time=10.0)

    budget.can_interrupt(InterruptClass.CHECKPOINT, current_time=12.0)

    assert budget._cognitive_load == LOAD_PER_CONFIRM - 2.0 * LOAD_DECAY_PER_SECOND


def test_cognitive_load_decays_toward_zero_not_negative():
    budget = AttentionBudget(cooldown_s=0.0)
    budget.record_interrupt(current_time=10.0)

    budget.can_interrupt(InterruptClass.CHECKPOINT, current_time=100.0)

    assert budget._cognitive_load == 0.0


def test_defer_marks_request_and_queues_it():
    budget = AttentionBudget()
    req = request()

    budget.defer(req)

    assert req.deferred
    assert budget._deferred == [req]


def test_flush_deferred_returns_requests_when_budget_allows():
    budget = AttentionBudget(max_confirms_per_minute=10, cooldown_s=0.0)
    req1 = request("r1")
    req2 = request("r2")
    budget.defer(req1)
    budget.defer(req2)

    flushed = budget.flush_deferred(current_time=100.0)

    assert flushed == [req1, req2]
    assert budget._deferred == []


def test_flush_deferred_keeps_queue_when_budget_blocks():
    budget = AttentionBudget(max_confirms_per_minute=1, cooldown_s=0.0)
    req = request()
    budget.record_interrupt(current_time=10.0)
    budget.defer(req)

    flushed = budget.flush_deferred(current_time=20.0)

    assert flushed == []
    assert budget._deferred == [req]


def test_flush_empty_queue_returns_empty_list():
    budget = AttentionBudget()

    assert budget.flush_deferred(current_time=100.0) == []
