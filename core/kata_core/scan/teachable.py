"""Teachable-content check for scanned page text.

A block is teachable when it reads as learning material. Not teachable: text shorter than the limit,
contact details, cookie or consent notices, navigation link lists, footers, legal text and comment or
advertising boilerplate. Pure function: no I/O. The caller passes the limit (from [scan] min_block_chars).
"""

from __future__ import annotations

import re

_PHONE = re.compile(r"(?<!\w)\+?\d(?:[\s()-]{0,2}\d){8,}(?!\w)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_COOKIE = re.compile(
    r"\b(?:accept (?:all )?cookies|we use cookies|cookie (?:settings|policy|preferences|consent)"
    r"|manage (?:your )?(?:cookie|consent)s?)\b",
    re.IGNORECASE,
)
_FOOTER = re.compile(r"(?:©|\(c\)|\bcopyright\b\s*\d{4}|\ball rights reserved\b)", re.IGNORECASE)
_LEGAL = re.compile(
    r"\b(?:terms of (?:service|use)|terms and conditions|privacy policy"
    r"|governed by the laws? of)\b",
    re.IGNORECASE,
)
_BOILERPLATE = re.compile(
    r"\b(?:leave a (?:reply|comment)|advertisement|sponsored content"
    r"|share this (?:post|article)|subscribe to our newsletter)\b",
    re.IGNORECASE,
)
_NAV_SEPARATOR = re.compile(r"\s[|»·]\s")
_NAV_MAX_WORDS = 3
_NAV_MIN_LINKS = 4


def _is_nav_list(text: str) -> bool:
    """True for a run of short items joined by separators, or a column of short lines."""
    parts = [part.strip() for part in _NAV_SEPARATOR.split(text)]
    if len(parts) >= _NAV_MIN_LINKS and all(0 < len(p.split()) <= _NAV_MAX_WORDS for p in parts):
        return True
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return len(lines) >= _NAV_MIN_LINKS and all(len(line.split()) <= _NAV_MAX_WORDS for line in lines)


def teachable(text: str, min_chars: int) -> tuple[bool, str]:
    """Return (True, '') when `text` is teachable, else (False, reason)."""
    stripped = text.strip()
    if len(stripped) < min_chars:
        return False, "too short"
    if _PHONE.search(stripped):
        return False, "phone number"
    if _EMAIL.search(stripped):
        return False, "email address"
    if _COOKIE.search(stripped):
        return False, "cookie or consent notice"
    if _is_nav_list(stripped):
        return False, "navigation list"
    if _FOOTER.search(stripped):
        return False, "footer line"
    if _LEGAL.search(stripped):
        return False, "legal text"
    if _BOILERPLATE.search(stripped):
        return False, "comment or ad boilerplate"
    return True, ""
