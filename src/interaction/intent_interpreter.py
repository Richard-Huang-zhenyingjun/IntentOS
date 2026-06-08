"""
Lightweight LLM intent interpreter.
Maps free-form natural language to a small, fixed set of workspace intents.

This is NOT a planner. It only normalizes phrasing into one of the
canonical intents below. The planner still handles decomposition,
grounding, and validation.

Safety properties this module guarantees:
  1. Control tokens (stop / pause / resume) are intercepted BEFORE any
     rule or LLM interpretation. They never wait on a network call and
     can never be remapped to something else.
  2. Affirmation ("yes") is never produced from a negated phrase
     ("please don't", "no, don't do it").
  3. All phrase matching is word-boundary aware. No unbounded substrings.
  4. LLM output is constrained to the fixed allowlist. Unknown or invalid
     output routes to __CLARIFY__.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


# Canonical vocabulary. Everything else is checked against this.
CONTROL_INTENTS = ["stop", "pause", "resume"]

ACTION_INTENTS = [
    "clean the table",
    "move the red block to the bin",
    "move the blue block to the bin",
    "move the yellow block to the bin",
    "put the tool in the tray",
    "take out of bin",
]

CONVERSATIONAL_INTENTS = ["yes", "no"]
META_INTENTS = ["explain", "show plan", "show debug", "hide debug"]

KNOWN_INTENTS = (
    CONTROL_INTENTS + ACTION_INTENTS + CONVERSATIONAL_INTENTS + META_INTENTS
)

_LLM_ALLOWED = ACTION_INTENTS + CONVERSATIONAL_INTENTS

_CONTROL_TRIGGERS = {
    "stop": [r"\bstop\b", r"\bhalt\b", r"\bfreeze\b", r"\babort\b", r"\bwait\b"],
    "pause": [r"\bpause\b", r"\bhold on\b", r"\bhold up\b"],
    "resume": [r"\bresume\b", r"\bcontinue\b", r"\bcarry on\b", r"\bkeep going\b"],
}


def _detect_control(text_lower: str) -> str | None:
    """Return a control intent if the text is a control command, else None."""
    for pattern in _CONTROL_TRIGGERS["stop"]:
        if re.search(pattern, text_lower):
            return "stop"
    for pattern in _CONTROL_TRIGGERS["pause"]:
        if re.search(pattern, text_lower):
            return "pause"
    for pattern in _CONTROL_TRIGGERS["resume"]:
        if re.search(pattern, text_lower):
            return "resume"
    return None


_NEGATION_MARKERS = [
    r"\bdon'?t\b",
    r"\bdo not\b",
    r"\bnever\b",
    r"\bcancel\b",
    r"\bnope\b",
    r"\bnah\b",
    r"\bno\b",
    r"\bforget it\b",
    r"\bnever mind\b",
    r"\bnevermind\b",
]


def _is_negated(text_lower: str) -> bool:
    """True if the utterance carries a negation marker."""
    return any(re.search(pattern, text_lower) for pattern in _NEGATION_MARKERS)


def _phrases(*words: str) -> list[str]:
    """Build word-boundary regex patterns from literal phrases."""
    return [rf"\b{re.escape(word)}\b" for word in words]


_CLARIFY_RULES = _phrases(
    "make some room",
    "make room",
    "make space",
    "free space",
    "create space",
    "free up",
    "tidy up a bit",
    "tidy this up",
    "put things away",
    "put it away",
    "put them away",
    "put stuff away",
    "clear some space",
    "clear space",
)

_CLEAN_TABLE_RULES = _phrases(
    "clean the table",
    "clear the table",
    "tidy the table",
    "clear everything",
    "clear it all",
    "put the loose stuff away",
    "loose stuff away",
)

_AFFIRM_RULES = _phrases(
    "yes",
    "yeah",
    "yep",
    "yup",
    "sure",
    "okay",
    "ok",
    "go ahead",
    "do it",
    "affirmative",
    "sounds good",
)

_DENY_RULES = _phrases(
    "nope",
    "nah",
    "cancel that",
    "never mind",
    "nevermind",
    "don't",
    "dont",
    "forget it",
)

_TAKE_OUT_RULES = _phrases(
    "take out",
    "get out",
    "remove from",
    "out of bin",
    "bring back",
    "retrieve",
)


class IntentInterpreter:
    def __init__(self, gemini_adapter=None):
        self._gemini = gemini_adapter
        self._enabled = gemini_adapter is not None

    def interpret(
        self,
        user_text: str,
        last_object=None,
        last_action=None,
    ) -> str:
        text_lower = user_text.lower().strip()

        control = _detect_control(text_lower)
        if control is not None:
            return control

        if text_lower in {intent.lower() for intent in KNOWN_INTENTS}:
            return user_text

        if _is_negated(text_lower):
            if any(re.search(pattern, text_lower) for pattern in _DENY_RULES):
                return "no"
            return "__CLARIFY__"

        if any(re.search(pattern, text_lower) for pattern in _CLARIFY_RULES):
            if self._enabled:
                return self._interpret_with_llm(
                    user_text,
                    text_lower,
                    last_object=last_object,
                    last_action=last_action,
                )
            return "__CLARIFY__"

        if any(re.search(pattern, text_lower) for pattern in _AFFIRM_RULES):
            return "yes"

        if any(re.search(pattern, text_lower) for pattern in _CLEAN_TABLE_RULES):
            return "clean the table"

        if any(re.search(pattern, text_lower) for pattern in _TAKE_OUT_RULES):
            return "take out of bin"

        if self._looks_like_known_planner_goal(text_lower):
            return user_text

        if not self._enabled:
            return "__CLARIFY__"
        return self._interpret_with_llm(
            user_text,
            text_lower,
            last_object=last_object,
            last_action=last_action,
        )

    def _interpret_with_llm(
        self,
        user_text: str,
        text_lower: str,
        last_object=None,
        last_action=None,
    ) -> str:
        try:
            from src.interaction.translation_prompt import build_prompt

            prompt = build_prompt(user_text)
            result = self._gemini.generate(
                prompt=prompt,
                timeout_s=3.0,
            )
            interpreted = result.strip().lower()

            if interpreted in {"unknown", "none", "unclear", "__clarify__"}:
                logger.info("Intent flagged unknown by LLM: %r", user_text)
                return "__CLARIFY__"

            if interpreted in CONTROL_INTENTS:
                logger.warning(
                    "LLM emitted control token %r via interpret path; clarifying",
                    interpreted,
                )
                return "__CLARIFY__"

            for intent in _LLM_ALLOWED:
                if interpreted == intent.lower():
                    if interpreted != text_lower:
                        logger.info("Intent interpreted: %r -> %r", user_text, intent)
                    return intent

            logger.info("Intent unmapped, routing to clarify: %r", user_text)
            return "__CLARIFY__"
        except Exception as exc:
            logger.debug("Intent interpretation failed: %s", exc)
            return "__CLARIFY__"

    @staticmethod
    def _looks_like_known_planner_goal(text_lower: str) -> bool:
        """
        Pass straight to the planner only for concrete object-manipulation
        commands or explicit whole-table commands.
        """
        whole_table_patterns = [
            r"\bclean (the )?table\b",
            r"\bclear (the )?table\b",
            r"\btidy (the )?table\b",
        ]
        for pattern in whole_table_patterns:
            if re.search(pattern, text_lower):
                return True

        object_words = [
            "block",
            "tool",
            "screwdriver",
            "cup",
            "red",
            "blue",
            "yellow",
        ]
        has_object = any(
            re.search(rf"\b{re.escape(word)}\b", text_lower)
            for word in object_words
        )

        action_words = ["move", "put", "take", "grab", "place", "drop"]
        has_action = any(
            re.search(rf"\b{re.escape(word)}\b", text_lower)
            for word in action_words
        )

        destination_words = ["bin", "tray"]
        has_destination = any(
            re.search(rf"\b{re.escape(word)}\b", text_lower)
            for word in destination_words
        )

        return has_object and has_action and has_destination
