"""Shared action pin rule for the GitHub workflows: owner/name@<40 hex> with the tag as a comment."""

from __future__ import annotations

import re

# Full commit SHA pin with the tag as a trailing comment: owner/name@<40 hex> # vN.
# A tag-only ref, a branch name or a bare SHA without the tag comment does not match.
SHA_PIN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40} # v\d+$")
# The value after `uses:`, trailing comment included (YAML parsing drops the comment).
USES_LINE = re.compile(r"^\s*(?:-\s+)?uses:\s*(\S.*?)\s*$", re.MULTILINE)


def uses_failures(uses: list[str]) -> list[str]:
    return [value for value in uses if not SHA_PIN.match(value)]


def pin_failures(text: str) -> list[str]:
    uses = USES_LINE.findall(text)
    assert uses, "the workflow must use at least one action"
    return uses_failures(uses)
