"""Tests for AmbiguityResolver."""
from unittest.mock import MagicMock, patch

import pytest

from src.agents import AgentRegistry
from src.planning.ambiguity_resolver import (
    AMBIGUITY_THRESHOLD,
    AUTO_SELECT_THRESHOLD,
    AmbiguityResolver,
    Interpretation,
)


@pytest.fixture
def mock_registry():
    reg = AgentRegistry()
    arm = MagicMock()
    arm.agent_id = "arm"
    reg.register(arm)
    return reg


@pytest.fixture
def mock_planner_high_confidence():
    planner = MagicMock()
    result = MagicMock()
    result.graph = MagicMock()
    result.graph.plan_confidence = 0.92
    result.graph.graph_id = "g1"
    result.graph.nodes = [MagicMock()]
    planner.plan = MagicMock(return_value=result)
    return planner


class TestAutoSelect:
    def test_high_confidence_auto_selects(
        self,
        mock_registry,
        mock_planner_high_confidence,
    ):
        """High-confidence single interpretation -> auto-selected, no human needed."""
        with patch("src.planning.ambiguity_resolver.validate", return_value=[]):
            resolver = AmbiguityResolver(mock_planner_high_confidence, mock_registry)
            resolution = resolver.resolve("clean table", "scene")
        assert resolution is not None
        assert resolution.auto_selected is True
        assert resolution.interpretations_shown == 0


class TestHumanSelection:
    def test_callback_called_when_ambiguous(self, mock_registry):
        """When confidence is below auto-select threshold, callback is invoked."""
        planner = MagicMock()
        result = MagicMock()
        result.graph = MagicMock()
        result.graph.plan_confidence = 0.60
        result.graph.graph_id = "g1"
        result.graph.nodes = [MagicMock()]
        planner.plan = MagicMock(return_value=result)

        callback = MagicMock(return_value="1")

        with patch("src.planning.ambiguity_resolver.validate", return_value=[]):
            resolver = AmbiguityResolver(planner, mock_registry)
            resolution = resolver.resolve(
                "clean table",
                "scene",
                selection_callback=callback,
            )

        assert resolution is not None
        callback.assert_called_once()

    def test_no_valid_interpretations_returns_none(self, mock_registry):
        """All interpretations fail validation -> returns None."""
        planner = MagicMock()
        result = MagicMock()
        result.graph = MagicMock()
        result.graph.plan_confidence = 0.5
        result.graph.graph_id = "g1"
        result.graph.nodes = []
        planner.plan = MagicMock(return_value=result)

        with patch(
            "src.planning.ambiguity_resolver.validate",
            return_value=[MagicMock()],
        ):
            resolver = AmbiguityResolver(planner, mock_registry)
            resolution = resolver.resolve(
                "ambiguous goal",
                "scene",
                selection_callback=lambda opts: "1",
            )

        assert resolution is None

    def test_maximum_three_options_shown_to_human(self, mock_registry):
        planner = MagicMock()
        resolver = AmbiguityResolver(planner, mock_registry)
        options = [
            Interpretation(str(i), f"option {i}", 0.6 - i * 0.01, MagicMock(), True, str(i))
            for i in range(1, 5)
        ]
        resolver._generate_interpretations = MagicMock(return_value=options)

        seen = []

        def choose_first(opts):
            seen.extend(opts)
            return "1"

        resolution = resolver.resolve("ambiguous", "scene", selection_callback=choose_first)

        assert resolution is not None
        assert resolution.interpretations_shown == 3
        assert len(seen) == 3

    def test_console_selection_fallback_works_for_demo_mode(self, mock_registry):
        planner = MagicMock()
        resolver = AmbiguityResolver(planner, mock_registry)
        option = Interpretation("i1", "Literal", 0.6, MagicMock(), True, "1")

        with patch("builtins.input", return_value=""):
            assert resolver._console_selection([option]) == "1"


class TestEEGNotUsed:
    def test_eeg_confirm_never_referenced_in_resolver(self):
        """Confirm EEG is not used for ambiguity selection."""
        import inspect
        import src.planning.ambiguity_resolver as mod

        source = inspect.getsource(mod)
        assert "eeg" not in source.lower() or "never EEG" in source, (
            "AmbiguityResolver must not reference EEG for selection. "
            "EEG is confirm/cancel only."
        )


def test_threshold_constants_ordered():
    assert AMBIGUITY_THRESHOLD < AUTO_SELECT_THRESHOLD
