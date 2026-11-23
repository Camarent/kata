"""Mask secrets in terminal command text.

Dependency-free by design (docs/decisions.md: client masking uses a small pattern list). Nothing
here logs or prints the text, the patterns or load errors: a bad mask list is skipped silently.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

MASK_TOKEN = "[masked]"
MASK_ENV = "KATA_TERM_MASKS"
DEFAULT_MASK_RELPATH = Path(".config", "kata", "term-masks")

_TOKEN_CHARS = r"[A-Za-z0-9+/_-]"

# Built-in patterns, applied after the user list. Each hit becomes MASK_TOKEN.
BUILTIN_PATTERNS: tuple[re.Pattern[str], ...] = (
    # -p secret / --password secret, with a space or '='. First, so --password=x is not split.
    re.compile(r"(?<!\S)(?:-p|--password)(?:\s+|=)[^\s'\"]+"),
    # KEY=value, TOKEN=value, password=value and similar assignments.
    re.compile(r"(?i)\b\w*(?:key|token|secret|password|passwd)\w*=[^\s'\"]+"),
    # HTTP bearer credentials.
    re.compile(r"(?i)\bbearer\s+[^\s'\"]+"),
    # Long tokens with both letters and digits (high entropy, not plain words or paths).
    re.compile(
        rf"(?<!{_TOKEN_CHARS})(?=\S*\d)(?=\S*[A-Za-z]){_TOKEN_CHARS}{{32,}}(?!{_TOKEN_CHARS})"
    ),
)


def load_masks(path: Path) -> list[re.Pattern[str]]:
    """Read one regex or literal per line; blank and '#' lines and invalid regexes are skipped.

    A missing file returns an empty list. Nothing is echoed for a skipped line.
    """
    if not path.is_file():
        return []
    try:
        # errors="replace": one bad byte only damages its own line, not the whole list.
        lines = path.read_bytes().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return []
    masks: list[re.Pattern[str]] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            pattern = re.compile(line)
        except (re.error, OverflowError):
            continue
        if pattern.fullmatch(""):
            continue  # would insert the token between every character
        masks.append(pattern)
    return masks


def mask_command(text: str, masks: list[re.Pattern[str]]) -> str:
    """Replace every user-list match and every built-in pattern hit with MASK_TOKEN."""
    masked = text
    for pattern in (*masks, *BUILTIN_PATTERNS):
        masked = pattern.sub(MASK_TOKEN, masked)
    return masked


def default_mask_path(env: Mapping[str, str]) -> Path:
    """Return the mask list path: $KATA_TERM_MASKS when set, else ~/.config/kata/term-masks."""
    override = env.get(MASK_ENV)
    if override:
        return Path(override)
    return Path.home() / DEFAULT_MASK_RELPATH
