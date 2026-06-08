"""Tests for conversation memory and follow-up resolution."""

import pytest

from src.interaction.conversation_context import ConversationContext
from src.interaction.context_aware_interpreter import ContextAwareInterpreter


def test_records_move_and_resolves_followup_color():
    ctx = ConversationContext()
    ctx.record("move the blue block to the bin")

    assert ctx.last_object == "blue block"
    assert ctx.last_action == "move_to_bin"
    assert ctx.resolve("now the yellow one") == "move the yellow block to the bin"


def test_resolves_too_followup():
    ctx = ConversationContext()
    ctx.record("move the blue block to the bin")

    assert ctx.resolve("the red one too") == "move the red block to the bin"


def test_resolves_bare_color_reference():
    ctx = ConversationContext()
    ctx.record("move the blue block to the bin")

    assert ctx.resolve("the yellow one") == "move the yellow block to the bin"


def test_resolves_same_with_tool():
    ctx = ConversationContext()
    ctx.record("move the blue block to the bin")

    assert ctx.resolve("same with the tool") == "put the tool in the tray"


def test_put_it_back_reverses():
    ctx = ConversationContext()
    ctx.record("move the blue block to the bin")

    assert ctx.resolve("put it back") == "take out of bin"


def test_no_context_returns_none():
    ctx = ConversationContext()

    assert ctx.resolve("now the yellow one") is None


def test_full_command_not_treated_as_followup():
    ctx = ConversationContext()
    ctx.record("move the blue block to the bin")

    assert ctx.resolve("move the yellow block to the bin") is None


@pytest.fixture
def interp():
    return ContextAwareInterpreter(gemini_adapter=None)


def test_live_failing_sequence_now_works(interp):
    assert (
        interp.interpret("move the blue block to the bin")
        == "move the blue block to the bin"
    )
    assert interp.interpret("now the yellow one") == "move the yellow block to the bin"
    assert interp.interpret("the red one too") == "move the red block to the bin"


def test_followup_works_without_llm(interp):
    interp.interpret("move the red block to the bin")

    assert interp.interpret("now the blue one") == "move the blue block to the bin"


def test_negation_still_guarded_with_context(interp):
    interp.interpret("move the blue block to the bin")
    result = interp.interpret("don't move the yellow one")

    assert result != "move the yellow block to the bin"
    assert result in {"no", "__CLARIFY__"}


def test_control_token_still_first_with_context(interp):
    interp.interpret("move the blue block to the bin")

    assert interp.interpret("stop") == "stop"


def test_followup_with_no_prior_clarifies(interp):
    assert interp.interpret("now the yellow one") == "__CLARIFY__"


def test_clean_table_still_works(interp):
    assert interp.interpret("clean the table") == "clean the table"


def test_explicit_full_commands_unchanged(interp):
    assert (
        interp.interpret("move the yellow block to the bin")
        == "move the yellow block to the bin"
    )
    assert interp.interpret("put the tool in the tray") == "put the tool in the tray"
