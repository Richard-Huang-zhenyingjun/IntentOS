"""Regression tests for the revised IntentInterpreter.

Covers the three classes of bug the rewrite fixes:
  1. Control tokens (stop/pause/resume) intercepted before rules/LLM.
  2. Negated phrases never map to affirmation.
  3. Word-boundary matching - no unbounded-substring misreads.
Plus vocabulary-reconciliation invariants.
"""

import pytest

from src.interaction.intent_interpreter import (
    ACTION_INTENTS,
    CONTROL_INTENTS,
    KNOWN_INTENTS,
    _LLM_ALLOWED,
    IntentInterpreter,
)


@pytest.fixture
def interp():
    """Interpreter with no LLM - exercises rule + clarify paths only."""
    return IntentInterpreter(gemini_adapter=None)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("stop", "stop"),
        ("stop that", "stop"),
        ("halt", "stop"),
        ("freeze", "stop"),
        ("abort", "stop"),
        ("wait", "stop"),
        ("wait stop", "stop"),
        ("pause", "pause"),
        ("hold on", "pause"),
        ("resume", "resume"),
        ("continue", "resume"),
        ("keep going", "resume"),
    ],
)
def test_control_tokens_detected(interp, text, expected):
    assert interp.interpret(text) == expected


def test_stop_does_not_require_llm(interp):
    """Even with the LLM disabled, stop resolves instantly."""
    assert interp.interpret("stop") == "stop"


def test_stop_wins_over_other_content(interp):
    """An utterance containing stop halts, regardless of other words."""
    assert interp.interpret("stop, move the blue block later") == "stop"


def test_control_not_fired_by_substring(interp):
    """Boundary matching: 'stop' must not fire inside another word."""
    assert interp.interpret("put the stockpile away") != "stop"


@pytest.mark.parametrize(
    "text",
    [
        "please don't",
        "please don't move the red block",
        "no, don't do it",
        "do not go ahead",
        "never do that",
    ],
)
def test_negated_phrase_never_affirms(interp, text):
    assert interp.interpret(text) != "yes"


def test_polite_refusal_clarifies_not_affirms(interp):
    result = interp.interpret("please don't move the red block")
    assert result in {"no", "__CLARIFY__"}
    assert result != "yes"


def test_clean_affirmations_still_work(interp):
    for text in ["yeah", "yep", "sure", "go ahead", "do it", "okay"]:
        assert interp.interpret(text) == "yes", text


def test_clean_denials_still_work(interp):
    for text in ["nope", "nah", "cancel that", "never mind", "forget it"]:
        assert interp.interpret(text) == "no", text


def test_ok_substring_does_not_affirm(interp):
    """'ok' must not be read from unrelated words as yes."""
    assert interp.interpret("the bookshelf is full") != "yes"


def test_vague_tidy_routes_to_clarify(interp):
    for text in [
        "make some room",
        "tidy up a bit",
        "clear some space",
        "put things away",
        "free up",
    ]:
        assert interp.interpret(text) == "__CLARIFY__", text


def test_explicit_clean_table_works(interp):
    for text in [
        "clean the table",
        "clear the table",
        "clear everything",
        "put the loose stuff away",
    ]:
        assert interp.interpret(text) == "clean the table", text


def test_clarify_wins_over_clean(interp):
    assert interp.interpret("clear some space") == "__CLARIFY__"


def test_take_out_of_bin(interp):
    for text in ["take out", "bring back", "retrieve", "out of bin"]:
        assert interp.interpret(text) == "take out of bin", text


def test_concrete_command_passes_to_planner(interp):
    assert (
        interp.interpret("move the blue block to the bin")
        == "move the blue block to the bin"
    )


def test_control_intents_not_in_llm_allowlist():
    """Control tokens must never be reachable via the LLM path."""
    for control in CONTROL_INTENTS:
        assert control not in _LLM_ALLOWED


def test_llm_allowlist_is_subset_of_known():
    for intent in _LLM_ALLOWED:
        assert intent in KNOWN_INTENTS


def test_action_intents_in_known():
    for intent in ACTION_INTENTS:
        assert intent in KNOWN_INTENTS


def test_no_duplicate_known_intents():
    assert len(KNOWN_INTENTS) == len(set(KNOWN_INTENTS))


class _StubGemini:
    def __init__(self, reply):
        self._reply = reply

    def generate(self, prompt, timeout_s):
        return self._reply


def test_llm_emitting_control_token_is_rejected():
    interp = IntentInterpreter(gemini_adapter=_StubGemini("stop"))
    assert interp.interpret("zxcv qwer") == "__CLARIFY__"


def test_llm_unknown_routes_to_clarify():
    interp = IntentInterpreter(gemini_adapter=_StubGemini("unknown"))
    assert interp.interpret("zxcv qwer") == "__CLARIFY__"


def test_llm_valid_intent_passes():
    interp = IntentInterpreter(gemini_adapter=_StubGemini("clean the table"))
    assert interp.interpret("zxcv qwer") == "clean the table"


def test_llm_novel_action_rejected():
    interp = IntentInterpreter(gemini_adapter=_StubGemini("launch the rocket"))
    assert interp.interpret("zxcv qwer") == "__CLARIFY__"
