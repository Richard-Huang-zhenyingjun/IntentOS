"""IntentInterpreter wrapper with short-term conversation memory."""
from __future__ import annotations

import logging
import re

from src.interaction.conversation_context import ConversationContext
from src.interaction.intent_interpreter import (
    ACTION_INTENTS,
    KNOWN_INTENTS,
    IntentInterpreter,
    _DENY_RULES,
    _detect_control,
    _is_negated,
)

logger = logging.getLogger(__name__)

_RECORDABLE = {intent.lower() for intent in ACTION_INTENTS}


class ContextAwareInterpreter:
    """IntentInterpreter plus short-term follow-up resolution."""

    def __init__(self, gemini_adapter=None):
        self._base = IntentInterpreter(gemini_adapter=gemini_adapter)
        self._ctx = ConversationContext()

    def interpret(self, user_text: str) -> str:
        text_lower = user_text.lower().strip()

        control = _detect_control(text_lower)
        if control is not None:
            return control

        if text_lower in {intent.lower() for intent in KNOWN_INTENTS}:
            self._maybe_record(user_text)
            return user_text

        if _is_negated(text_lower):
            if any(re.search(pattern, text_lower) for pattern in _DENY_RULES):
                return "no"
            return "__CLARIFY__"

        resolved = self._ctx.resolve(text_lower)
        if resolved is not None:
            logger.info("Context resolved %r -> %r", user_text, resolved)
            self._ctx.record(resolved)
            return resolved

        result = self._base.interpret(
            user_text,
            last_object=self._ctx.last_object,
            last_action=self._ctx.last_action,
        )
        self._maybe_record(result)
        return result

    def _maybe_record(self, intent: str) -> None:
        if intent and intent.lower() in _RECORDABLE:
            self._ctx.record(intent)

    @property
    def context(self) -> ConversationContext:
        return self._ctx

    def reset_context(self) -> None:
        self._ctx.reset()
