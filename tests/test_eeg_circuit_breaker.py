"""EEG circuit-breaker behavior and keyboard fallback tests."""

from src.input.eeg.circuit_breaker import EEGCircuitBreaker
from src.input.policies import DecisionPolicy, RoutingMode
from src.input.router import DecisionRouter
from src.input.source_base import DecisionSourceBase
from src.input.source_keyboard import KeyboardSource
from src.input.types import DecisionIntent, RawSourceReading, SourceType


class _FailingEEGSource(DecisionSourceBase):
    """Minimal EEG-like source gated by a circuit breaker."""

    def __init__(self, breaker: EEGCircuitBreaker):
        self.breaker = breaker

    def read_raw(self) -> RawSourceReading:
        return RawSourceReading(
            intent=DecisionIntent.CONFIRM,
            source_type=SourceType.EEG,
            quality=0.9,
            raw_pressed=True,
        )

    def source_type(self) -> SourceType:
        return SourceType.EEG

    def name(self) -> str:
        return "eeg_failing"

    def is_available(self) -> bool:
        return self.breaker.is_allowing


def test_eeg_circuit_breaker_trips():
    """Circuit breaker opens after repeated failures."""
    config = {
        "eeg": {
            "circuit_breaker": {
                "error_threshold": 3,
                "cooldown_sec": 60.0,
                "window_sec": 30.0,
            }
        }
    }
    breaker = EEGCircuitBreaker(config)

    breaker.record_error("device read failure")
    breaker.record_error("device read failure")
    breaker.record_error("device read failure")

    assert breaker.get_state() == "OPEN"
    assert breaker.is_allowing is False


def test_keyboard_fallback_when_eeg_breaker_open():
    """When EEG is unavailable, router still accepts keyboard confirm."""
    policy = DecisionPolicy(
        mode=RoutingMode.ANY,
        min_quality=0.65,
        debounce_frames=0,
        confirm_hold_frames=1,
        dual_window_ms=900,
        dual_sources=["keyboard", "eeg"],
        allowed_sources=["keyboard", "eeg"],
    )
    router = DecisionRouter(policy)

    keyboard = KeyboardSource({"keyboard": {"confirm_key": "c", "cancel_key": "x"}})
    keyboard.set_key_state(confirm=True, cancel=False)

    breaker = EEGCircuitBreaker(
        {
            "eeg": {
                "circuit_breaker": {
                    "error_threshold": 1,
                    "cooldown_sec": 60.0,
                    "window_sec": 30.0,
                }
            }
        }
    )
    breaker.record_error("device unavailable")

    router.register_source("keyboard", keyboard)
    router.register_source("eeg", _FailingEEGSource(breaker))

    intent, source_type, _, raw_intents = router.read_all()

    assert intent == DecisionIntent.CONFIRM
    assert source_type == SourceType.KEYBOARD
    assert "keyboard" in raw_intents
    assert "eeg" not in raw_intents
