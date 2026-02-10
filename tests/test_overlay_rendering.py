"""Overlay rendering unit tests for structured sections and truncation."""

from types import SimpleNamespace


def test_overlay_sections_present():
    """Overlay builder generates all required sections."""
    from src.ui.overlay import OverlayBuilder
    from src.core.schema import ArmUIState

    builder = OverlayBuilder()
    scene_summary = SimpleNamespace(
        objects_on_table=[1, 2, 3],
        bin_zone_center=(0.4, 0.0, 0.75),
        clutter_score=0.65,
    )
    proposal = SimpleNamespace(
        source="gemini",
        action=SimpleNamespace(value="clean_table"),
        confidence=0.92,
        description="High object density detected",
    )

    text_lines = builder.build(
        state=ArmUIState.CONFIRMING,
        scene_summary=scene_summary,
        proposal=proposal,
        trust=0.78,
    )

    combined = "\n".join(text_lines)
    assert "SYSTEM STATE" in combined
    assert "PROPOSAL" in combined
    assert "Trust:" in combined


def test_overlay_truncates_long_strings():
    """Overlay doesn't exceed line width limits."""
    from src.ui.overlay import OverlayBuilder
    from src.core.schema import ArmUIState

    builder = OverlayBuilder(max_line_len=40)
    long_reason = "This rationale is intentionally extremely long to exceed overlay width limits"
    proposal = SimpleNamespace(
        source="gemini",
        action=SimpleNamespace(value="clean_table"),
        confidence=0.99,
        description=long_reason,
    )

    lines = builder.build(
        state=ArmUIState.CONFIRMING,
        scene_summary=SimpleNamespace(objects_on_table=[], bin_zone_center=None, clutter_score=0.0),
        proposal=proposal,
        trust=0.78,
    )

    assert all(len(line) <= 40 for line in lines)
    assert any(line.endswith("...") for line in lines)
