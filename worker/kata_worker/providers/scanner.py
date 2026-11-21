"""Secret scanner: find likely secrets in text before it leaves the machine.

`scan` returns where each finding starts and which rule matched. It never returns the matched
text, so a finding cannot leak the secret it reports. The rules are fixed in this module.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    kind: str
    offset: int


@dataclass(frozen=True)
class _Rule:
    kind: str
    pattern: re.Pattern[str]
    min_entropy: float = 0.0


_ENTROPY_TOKEN = re.compile(r"[A-Za-z0-9+/_=-]{20,}")

RULES: tuple[_Rule, ...] = (
    _Rule("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    _Rule("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36}")),
    _Rule("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    _Rule("password_assignment", re.compile(r"(?i)password\s*[:=]\s*\S+")),
    _Rule("high_entropy", _ENTROPY_TOKEN, min_entropy=4.0),
)


def _entropy(token: str) -> float:
    """Shannon entropy of `token` in bits per character."""
    total = len(token)
    counts = (token.count(ch) for ch in set(token))
    return -sum((n / total) * math.log2(n / total) for n in counts)


def scan(text: str) -> list[Finding]:
    """Findings in `text`, ordered by offset. Each finding holds only the rule kind and offset.

    Rules run in RULES order. A match that overlaps an earlier finding is dropped, so one
    secret reports once under the most specific rule.
    """
    findings: list[Finding] = []
    claimed: list[tuple[int, int]] = []
    for rule in RULES:
        for match in rule.pattern.finditer(text):
            start, end = match.span()
            if any(start < hi and lo < end for lo, hi in claimed):
                continue
            if rule.min_entropy and _entropy(match.group(0)) < rule.min_entropy:
                continue
            claimed.append((start, end))
            findings.append(Finding(kind=rule.kind, offset=start))
    return sorted(findings, key=lambda f: (f.offset, f.kind))
