"""
Lightweight LLM intent interpreter.
Maps free-form natural language to workspace intents.

This is NOT a planner. It only maps language to one of
a small set of known workspace intentions. The planner
still handles decomposition and validation.

Examples:
  "can you make some space"    -> "clean the table"
  "move that thing away"       -> "move nearest object to bin"
  "put the loose stuff away"   -> "clean the table"
  "grab the thing near tray"   -> "move nearest object to tray"
  "yes please"                 -> "yes"
  "go ahead"                   -> "yes"
  "stop that"                  -> "stop"
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


KNOWN_INTENTS = [
    "clean the table",
    "move the nearest item to the bin",
    "move the nearest item to the tray",
    "take out of bin",
    "yes",
    "no",
    "stop",
    "pause",
    "resume",
    "explain",
    "show plan",
    "show debug",
    "hide debug",
]

_SPATIAL_RULES = [
    # Vague space-making requests require clarification before moving objects.
    (
        [
            "make some room",
            "make room",
            "make space",
            "free space",
            "create space",
            "free up",
            "tidy up a bit",
        ],
        "__CLARIFY__",
    ),

    # Clean table variants
    (["clean the table"], "clean the table"),
    (
        [
            "put things away",
            "put it away",
            "put them away",
            "put stuff away",
            "put the loose stuff away",
            "loose stuff away",
        ],
        "clean the table",
    ),
    (
        [
            "clear the table",
            "clear everything",
            "clear it all",
            "clear all",
            "clear the middle",
            "clear middle",
        ],
        "clean the table",
    ),
    (
        ["move things", "move the stuff", "move objects", "move everything"],
        "clean the table",
    ),

    # Confirmation variants
    (
        [
            "yeah",
            "yep",
            "yup",
            "sure",
            "ok",
            "okay",
            "go ahead",
            "do it",
            "please",
            "affirmative",
        ],
        "yes",
    ),
    (
        [
            "nope",
            "nah",
            "cancel that",
            "never mind",
            "stop that",
            "don't",
            "forget it",
        ],
        "no",
    ),

    # Take out variants
    (
        [
            "take out",
            "get out",
            "remove from",
            "out of bin",
            "bring back",
            "retrieve",
        ],
        "take out of bin",
    ),
]

SYSTEM_PROMPT = """You interpret workspace commands into one of these intents:
- "clean the table"
- "move the [color] block to the bin"
- "put the tool in the tray"
- "take out of bin"
- "yes" / "no"

Never invent actions not in this list.
Respond with ONLY the intent string.

If the user's request does not clearly match exactly one of the allowed
intents, output the single word: unknown. Never guess the closest one.
A vague request like "make some room" or "tidy up a bit" is unknown unless
the user names objects or says clean/clear the table.
"""


class IntentInterpreter:
    """
    Wraps Gemini to interpret free-form language into workspace intents.
    Falls back to passthrough if LLM unavailable.
    """

    def __init__(self, gemini_adapter=None):
        self._gemini = gemini_adapter
        self._enabled = gemini_adapter is not None

    def interpret(self, user_text: str) -> str:
        """
        Map user text to a known workspace intent.
        Returns original text if no mapping found or LLM unavailable.
        """
        text_lower = user_text.lower().strip()
        if text_lower in {i.lower() for i in KNOWN_INTENTS}:
            return user_text

        for phrases, intent in _SPATIAL_RULES:
            if any(phrase in text_lower for phrase in phrases):
                return intent

        if not self._enabled or self._looks_like_known_planner_goal(text_lower):
            return user_text

        try:
            result = self._gemini.generate(
                prompt=f"{SYSTEM_PROMPT}\n\nUser: {user_text}\nIntent:",
                timeout_s=3.0,
            )
            interpreted = result.strip().lower()
            if interpreted in {"unknown", "none", "unclear", "__clarify__"}:
                logger.info("Intent flagged unknown by LLM: %r", user_text)
                return "__CLARIFY__"
            allowed = [
                "clean the table",
                "move the red block to the bin",
                "move the blue block to the bin",
                "move the yellow block to the bin",
                "put the tool in the tray",
                "take out of bin",
                "yes",
                "no",
            ]
            for intent in allowed:
                if interpreted == intent.lower():
                    if interpreted != text_lower:
                        logger.info("Intent interpreted: %r -> %r", user_text, intent)
                    return intent
            logger.info("Intent unmapped, routing to clarify: %r", user_text)
            return "__CLARIFY__"
        except Exception as e:
            logger.debug("Intent interpretation failed: %s", e)
            return "__CLARIFY__"

    @staticmethod
    def _looks_like_known_planner_goal(text_lower: str) -> bool:
        """Let existing planner patterns pass through without LLM rewriting."""
        object_words = [
            "block",
            "tool",
            "red",
            "blue",
            "yellow",
            "screwdriver",
            "cup",
        ]
        action_words = [
            "move",
            "put",
            "take",
            "grab",
            "clean",
            "clear",
            "tidy",
            "home",
        ]
        destination_words = ["bin", "tray", "table"]
        return (
            any(word in text_lower for word in object_words)
            or any(word in text_lower for word in action_words)
            or any(word in text_lower for word in destination_words)
        )
