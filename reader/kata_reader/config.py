"""Reader config: only the [reader] table of the toml file named by env KATA_CONFIG.

The reader reads no secret and no other section. Every key the reader needs must be present:
a missing key is a ConfigError that names it, and __main__ exits 2 with that message.
"""

from __future__ import annotations

import dataclasses
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kata_reader.limits import Limits

CONFIG_ENV = "KATA_CONFIG"
DEFAULT_CONFIG = "/config/kata.toml"
SECTION = "reader"
LIMIT_KEYS = tuple(field.name for field in dataclasses.fields(Limits))
SPOOL_KEYS = ("poll_seconds", "spool_dir")


class ConfigError(Exception):
    """The config file or its [reader] table cannot be used."""


@dataclass(frozen=True)
class ReaderConfig:
    limits: Limits
    poll_seconds: float
    spool_dir: Path


def load(path: str | Path) -> ReaderConfig:
    """Read the [reader] table at path. Raises ConfigError for a missing file or key."""
    try:
        with open(path, "rb") as handle:
            doc = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read config {path}: {exc}") from exc
    block: Any = doc.get(SECTION)
    if not isinstance(block, dict):
        raise ConfigError(f"config {path} has no [{SECTION}] table")
    for key in (*LIMIT_KEYS, *SPOOL_KEYS):
        if key not in block:
            raise ConfigError(f"[{SECTION}] is missing key {key!r}")
    limits = Limits(**{key: block[key] for key in LIMIT_KEYS})
    return ReaderConfig(
        limits=limits,
        poll_seconds=block["poll_seconds"],
        spool_dir=Path(block["spool_dir"]),
    )
