"""ConversationContext - short-term memory for follow-up commands."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


_KNOWN_OBJECTS = {
    "red": "red block",
    "blue": "blue block",
    "yellow": "yellow block",
    "block": None,
    "tool": "tool",
    "screwdriver": "tool",
}

_COLOR_WORDS = ("red", "blue", "yellow")

_CONTINUATION_MARKERS = (
    "now",
    "next",
    "then",
    "also",
    "too",
    "as well",
    "same",
    "do the",
    "and the",
)

_PRONOUN_MARKERS = ("it", "that", "this", "that one", "this one", "the one")

_REVERSE_MARKERS = ("back", "out", "return", "undo")


def _canonical_move_intent(object_label: str) -> Optional[str]:
    """Map an object to its canonical move/put intent."""
    if object_label == "tool":
        return "put the tool in the tray"
    if object_label in ("red block", "blue block", "yellow block"):
        return f"move the {object_label} to the bin"
    return None


@dataclass
class _State:
    last_object: Optional[str] = None
    last_action: Optional[str] = None


class ConversationContext:
    """Track last object/action and resolve follow-up references."""

    def __init__(self):
        self._state = _State()

    def record(self, canonical_intent: str) -> None:
        """Update memory after a concrete canonical intent is dispatched."""
        intent = canonical_intent.lower().strip()
        match = re.match(r"move the (red|blue|yellow) block to the bin", intent)
        if match:
            self._state.last_object = f"{match.group(1)} block"
            self._state.last_action = "move_to_bin"
            return

        if intent == "put the tool in the tray":
            self._state.last_object = "tool"
            self._state.last_action = "put_in_tray"
            return

        if intent == "take out of bin":
            self._state.last_action = "take_from_bin"
            return

        if intent == "clean the table":
            self._state.last_action = "move_to_bin"
            self._state.last_object = None
            return

    def reset(self) -> None:
        self._state = _State()

    def resolve(self, text_lower: str) -> Optional[str]:
        """Resolve a follow-up into a canonical intent, or None."""
        if self._state.last_action is None and self._state.last_object is None:
            return None

        has_continuation = any(marker in text_lower for marker in _CONTINUATION_MARKERS)
        named_color = next(
            (color for color in _COLOR_WORDS if re.search(rf"\b{color}\b", text_lower)),
            None,
        )
        mentions_tool = bool(
            re.search(r"\btool\b", text_lower)
            or re.search(r"\bscrewdriver\b", text_lower)
        )
        has_pronoun = any(
            re.search(rf"\b{re.escape(pronoun)}\b", text_lower)
            for pronoun in _PRONOUN_MARKERS
        )
        wants_reverse = any(
            re.search(rf"\b{re.escape(marker)}\b", text_lower)
            for marker in _REVERSE_MARKERS
        )

        if wants_reverse and (
            has_pronoun or named_color or mentions_tool or has_continuation
        ):
            if self._state.last_action in ("move_to_bin", "put_in_tray"):
                return "take out of bin"

        target_object = None
        if named_color:
            target_object = f"{named_color} block"
        elif mentions_tool:
            target_object = "tool"

        if target_object is not None and self._state.last_action is not None:
            says_destination = bool(
                re.search(r"\bbin\b", text_lower)
                or re.search(r"\btray\b", text_lower)
            )
            looks_like_followup = has_continuation or self._is_short_reference(
                text_lower
            )
            if looks_like_followup and not says_destination:
                return _canonical_move_intent(target_object)

        if has_pronoun and self._state.last_object is not None:
            if wants_reverse:
                return "take out of bin"
            if self._state.last_action == "move_to_bin":
                return _canonical_move_intent(self._state.last_object)
            if self._state.last_action == "put_in_tray":
                return "put the tool in the tray"

        return None

    @staticmethod
    def _is_short_reference(text_lower: str) -> bool:
        """Return True for short reference-like utterances, not full commands."""
        words = text_lower.split()
        if len(words) > 5:
            return False
        verbs = ("move", "put", "take", "grab", "place", "drop", "clean", "clear")
        if any(re.search(rf"\b{verb}\b", text_lower) for verb in verbs):
            return False
        return True

    @property
    def last_object(self) -> Optional[str]:
        return self._state.last_object

    @property
    def last_action(self) -> Optional[str]:
        return self._state.last_action
