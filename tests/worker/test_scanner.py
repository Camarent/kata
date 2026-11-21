"""Secret scanner: one table row per rule, clean-text rows, and the no-text-in-finding rule.

Sample secrets are built from string parts at run time, so this file holds no literal secret.
"""

from __future__ import annotations

import dataclasses

import pytest
from kata_worker.providers.scanner import RULES, Finding, scan

AWS_KEY = "AKIA" + "ABCDEFGH" + "IJKLMNOP"
GITHUB_TOKEN = "gh" + "p_" + "a1B2c3D4e5" + "F6g7H8i9J0" + "k1L2m3N4o5" + "P6q7R8"
PRIVATE_KEY_HEADER = "-----BEGIN " + "OPENSSH PRIVATE KEY-----"
PASSWORD_LINE = "password" + ": hunter2"
HIGH_ENTROPY = "q8Zr1Lx0Pk7Vn3Bm9Wc2Ty6Hd4Js5Ga"

# (text, expected finding kinds in order). One row per rule, then clean-text rows.
TABLE = [
    (f"key {AWS_KEY} end", ["aws_access_key"]),
    (f"token={GITHUB_TOKEN}", ["github_token"]),
    (f"{PRIVATE_KEY_HEADER}\nbody", ["private_key"]),
    (PASSWORD_LINE, ["password_assignment"]),
    (f"value {HIGH_ENTROPY} end", ["high_entropy"]),
    ("the quick brown fox jumps over the lazy dog", []),
    ("", []),
    ("reset your password later", []),
]


@pytest.mark.parametrize(("text", "kinds"), TABLE)
def test_scan_finds_expected_kinds(text: str, kinds: list[str]) -> None:
    assert [f.kind for f in scan(text)] == kinds


def test_table_covers_every_rule() -> None:
    covered = {kind for _, kinds in TABLE for kind in kinds}
    assert covered == {rule.kind for rule in RULES}


def test_offset_points_at_the_secret() -> None:
    prefix = "config dump: "
    findings = scan(prefix + AWS_KEY)
    assert findings == [Finding(kind="aws_access_key", offset=len(prefix))]


def test_finding_holds_no_text() -> None:
    assert [f.name for f in dataclasses.fields(Finding)] == ["kind", "offset"]
    finding = scan(f"x {AWS_KEY}")[0]
    assert not any(AWS_KEY in str(value) for value in dataclasses.astuple(finding))


def test_findings_are_frozen() -> None:
    finding = scan(PASSWORD_LINE)[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        finding.offset = 5  # type: ignore[misc]  # reason: test asserts the write fails at run time


def test_low_entropy_long_token_is_not_flagged() -> None:
    assert scan("a" * 40) == []
