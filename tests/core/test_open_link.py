"""Open-link signer: roundtrip, tamper, wrong key, expiry, malformed tokens, constant-time compare."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from pathlib import Path

import pytest
from kata_core.config import Config, ConfigError
from kata_core.trainer import open_link
from kata_core.trainer.open_link import load_signing_key, sign, verify

KEY = b"k" * 32
OTHER_KEY = b"o" * 32
NOW = 1_700_000_000
EXPIRES = NOW + 3600


def test_roundtrip_returns_user_and_course() -> None:
    token = sign(KEY, "user-1", "course-9", EXPIRES)
    assert verify(KEY, token, NOW) == ("user-1", "course-9")


def test_token_is_valid_until_expiry_instant() -> None:
    token = sign(KEY, "u", "c", EXPIRES)
    assert verify(KEY, token, EXPIRES - 1) == ("u", "c")
    assert verify(KEY, token, EXPIRES) is None


def test_tampered_payload_is_rejected() -> None:
    token = sign(KEY, "user-1", "course-9", EXPIRES)
    payload, mac = token.split(".")
    other = sign(KEY, "user-2", "course-9", EXPIRES).split(".")[0]
    assert other != payload
    assert verify(KEY, f"{other}.{mac}", NOW) is None


def test_tampered_mac_is_rejected() -> None:
    token = sign(KEY, "user-1", "course-9", EXPIRES)
    payload, mac = token.split(".")
    flipped = ("A" if mac[0] != "A" else "B") + mac[1:]
    assert verify(KEY, f"{payload}.{flipped}", NOW) is None


def test_wrong_key_is_rejected() -> None:
    token = sign(KEY, "user-1", "course-9", EXPIRES)
    assert verify(OTHER_KEY, token, NOW) is None


def test_expired_token_is_rejected() -> None:
    token = sign(KEY, "user-1", "course-9", EXPIRES)
    assert verify(KEY, token, EXPIRES + 1) is None


@pytest.mark.parametrize(
    "token",
    [
        "",
        "no-dot-at-all",
        "a.b.c",
        "x" * 40 + ".",
        ".",
    ],
)
def test_malformed_token_is_rejected(token: str) -> None:
    assert verify(KEY, token, NOW) is None


def test_extra_dots_are_rejected_even_when_prefix_is_valid() -> None:
    token = sign(KEY, "user-1", "course-9", EXPIRES)
    assert verify(KEY, token + ".extra", NOW) is None


def test_payload_with_wrong_shape_is_rejected() -> None:
    payload = json.dumps(["only-one-field"]).encode()
    mac = hmac.new(KEY, payload, hashlib.sha256).digest()

    def b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    assert verify(KEY, f"{b64(payload)}.{b64(mac)}", NOW) is None


def test_comparison_uses_hmac_compare_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[bytes, bytes]] = []
    real = open_link.hmac.compare_digest

    def spy(a: bytes, b: bytes) -> bool:
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(open_link.hmac, "compare_digest", spy)
    token = sign(KEY, "user-1", "course-9", EXPIRES)
    assert verify(KEY, token, NOW) == ("user-1", "course-9")
    assert len(calls) == 1


def _cfg(key_file: str) -> Config:
    return Config(sections={"trainer": {"open_link_key_file": key_file}})


def test_load_signing_key_reads_and_strips_file(tmp_path: Path) -> None:
    key_file = tmp_path / "key"
    key_file.write_bytes(KEY + b"\n")
    assert load_signing_key(_cfg(str(key_file))) == KEY


def test_load_signing_key_rejects_empty_path() -> None:
    with pytest.raises(ConfigError, match="empty"):
        load_signing_key(_cfg(""))


def test_load_signing_key_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read"):
        load_signing_key(_cfg(str(tmp_path / "absent")))


def test_load_signing_key_rejects_short_key(tmp_path: Path) -> None:
    key_file = tmp_path / "key"
    key_file.write_bytes(b"short\n")
    with pytest.raises(ConfigError, match="shorter than 32 bytes"):
        load_signing_key(_cfg(str(key_file)))
