"""Error recovery and graceful degradation tests."""

from src.core.system_factory import build_system, load_config
from src.input.policies import DecisionPolicy, RoutingMode
from src.input.router import DecisionRouter
from src.input.source_base import DecisionSourceBase
from src.input.source_keyboard import KeyboardSource
from src.input.types import DecisionIntent, RawSourceReading, SourceType
from src.intelligence.proposer_heuristic import HeuristicProposer
from src.intelligence.proposer_gemini import GeminiProposer
from src.intelligence.proposer_registry import ProposerRegistry
from src.interfaces.intent_proposal import ActionType
from src.interfaces.scene_summary import ObjectInfo, SceneSummary
from src.external.gemini.client_fake import FakeGeminiClient


class _UnavailableEEGSource(DecisionSourceBase):
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
        return "eeg_unavailable"

    def is_available(self) -> bool:
        return False


def _messy_scene() -> SceneSummary:
    objects = tuple(
        ObjectInfo(object_id=i, pos_xyz=(0.1 * i, 0.02 * i, 0.65), on_table=True)
        for i in range(4)
    )
    return SceneSummary(
        table_id=1,
        table_position=(0.0, 0.0, 0.3),
        bin_zone_center=(0.4, 0.0, 0.75),
        bin_zone_radius=0.12,
        objects=objects,
        objects_on_table=objects,
        clutter_score=0.6,
        is_messy=True,
        timestamp_frame=1,
    )


def test_gemini_network_error_fallback():
    """Gemini network failure triggers heuristic fallback."""
    config = load_config("configs/default.yaml")
    config["gemini"]["enabled"] = True
    config["gemini"]["use_fake_client"] = True

    fake_client = FakeGeminiClient()
    fake_client.set_exception(ConnectionError("network failure"))

    registry = ProposerRegistry()
    registry.register("heuristic", HeuristicProposer(config), priority=0, is_fallback=True)
    registry.register("gemini", GeminiProposer(client=fake_client, config=config), priority=10)
    registry.set_blocked_states({"executing"})

    proposal = registry.propose(_messy_scene())
    assert proposal.source == "heuristic"
    assert proposal.action == ActionType.CLEAN_TABLE


def test_eeg_device_missing_uses_keyboard():
    """Missing EEG device falls back to keyboard input."""
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
    router.register_source("keyboard", keyboard)
    router.register_source("eeg", _UnavailableEEGSource())

    intent, source, _, _ = router.read_all()
    assert intent == DecisionIntent.CONFIRM
    assert source == SourceType.KEYBOARD


def test_physics_divergence_pauses_safely():
    """Physics NaN/Inf triggers safe pause, not crash."""
    config = load_config("configs/default.yaml")
    config.setdefault("simulator", {})
    config["simulator"]["use_gui"] = False
    config["gemini"]["enabled"] = False
    config["eeg"]["enabled"] = False
    config.setdefault("logging", {})
    config["logging"]["events_enabled"] = False

    orch = build_system(config)
    try:
        orch.controller.check_divergence = lambda: True
        snapshot = orch.step()
        assert snapshot.paused is True
        assert snapshot.state.value == "paused"
        assert "Physics divergence detected" in snapshot.what_happened
    finally:
        orch.close()
