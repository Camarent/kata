"""Plain-text sanitiser for joke text from third-party APIs.

`sanitise_joke` returns one line of plain text or None. It never repairs a bad joke: markup,
entities, URLs and injection markers drop the whole joke, and so does a joke that is empty or
too long. Only the standard library is used.
"""

from __future__ import annotations

import re
import unicodedata

CONTROL_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn"})
SPACE_CHARS = frozenset({"\n", "\t"})
MARKUP_CHARS = ("<", ">")
ENTITY_PREFIX = "&#"
NAMED_ENTITY = re.compile(r"&[A-Za-z][A-Za-z0-9]*;")
URL = re.compile(r"https?://|www\.", re.IGNORECASE)
INJECTION_MARKERS = (
    "ignore previous",
    "ignore all",
    "system prompt",
    "you are now",
    "assistant:",
    "###",
)


def _strip_controls(text: str) -> str:
    """Drop control, format, surrogate, private-use and unassigned characters.

    A newline or tab becomes a space, so the joke stays one line.
    """
    kept: list[str] = []
    for char in text:
        if char in SPACE_CHARS:
            kept.append(" ")
        elif unicodedata.category(char) not in CONTROL_CATEGORIES:
            kept.append(char)
    return "".join(kept)


def sanitise_joke(raw: object, *, max_chars: int) -> str | None:
    """Return the joke as one plain-text line, or None when it must be dropped."""
    if not isinstance(raw, str):
        return None
    text = _strip_controls(unicodedata.normalize("NFKC", raw))
    if any(mark in text for mark in MARKUP_CHARS) or ENTITY_PREFIX in text:
        return None
    if NAMED_ENTITY.search(text) or URL.search(text):
        return None
    lowered = text.lower()
    if any(marker in lowered for marker in INJECTION_MARKERS):
        return None
    joke = " ".join(text.split())
    if not joke or len(joke) > max_chars:
        return None
    return joke
