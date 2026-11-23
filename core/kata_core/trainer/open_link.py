"""Signed open links for built courses: HMAC-SHA256 over a JSON payload, verified in constant time.

A token is `base64url(payload).base64url(mac)` with payload `[user_id, course_id, expires_at]`.
`now` is passed in by the caller, so checks need no clock.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from pathlib import Path

from kata_core.config import Config, ConfigError

MIN_KEY_BYTES = 32
_SEP = "."


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _mac(key: bytes, payload: bytes) -> bytes:
    return hmac.new(key, payload, hashlib.sha256).digest()


def sign(key: bytes, user_id: str, course_id: str, expires_at: int) -> str:
    """Return a token for `user_id` and `course_id`, valid while `now < expires_at`."""
    payload = json.dumps([user_id, course_id, expires_at], separators=(",", ":")).encode("utf-8")
    return _SEP.join((_b64encode(payload), _b64encode(_mac(key, payload))))


def verify(key: bytes, token: str, now: int) -> tuple[str, str] | None:
    """Return `(user_id, course_id)` for a valid, unexpired token; None for anything else."""
    parts = token.split(_SEP)
    if len(parts) != 2:
        return None
    try:
        payload = _b64decode(parts[0])
        mac = _b64decode(parts[1])
    except ValueError:  # binascii.Error is a ValueError
        return None
    if not hmac.compare_digest(_mac(key, payload), mac):
        return None
    try:
        user_id, course_id, expires_at = json.loads(payload)
    except (ValueError, TypeError):
        return None
    if not isinstance(user_id, str) or not isinstance(course_id, str):
        return None
    if not isinstance(expires_at, int) or isinstance(expires_at, bool):
        return None
    if now >= expires_at:
        return None
    return user_id, course_id


def load_signing_key(cfg: Config) -> bytes:
    """Read the key file named by `[trainer] open_link_key_file`. Raise ConfigError when unusable."""
    path = str(cfg.get("trainer", "open_link_key_file"))
    if not path:
        raise ConfigError("trainer.open_link_key_file is empty")
    try:
        # CodeQL py/path-injection false positive: `path` comes from server config
        # [trainer] open_link_key_file only, never from request input. Callers
        # (course_open.py, course_serve.py) pass the server Config, not client data.
        key = Path(path).read_bytes().strip()
    except OSError as exc:
        raise ConfigError(f"cannot read open link key {path}: {exc}") from exc
    if len(key) < MIN_KEY_BYTES:
        raise ConfigError(f"open link key {path} is shorter than {MIN_KEY_BYTES} bytes")
    return key
