"""Config loader: TOML file plus KATA_<SECTION>_<KEY> env override.

The key set and the defaults live in config/kata.example.toml. This module
holds no default literals: every key the example defines must be present in
the loaded file, and env vars override the file value, cast to its type.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

CONFIG_ENV = "KATA_CONFIG"
ENV_PREFIX = "KATA"
EXAMPLE_PATH = Path(__file__).resolve().parents[2] / "config" / "kata.example.toml"

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}

# trainer.max_courses_per_user: this value means no limit; any value below it is rejected.
MAX_COURSES_UNLIMITED = 0
_COURSE_LIMIT_KEY = ("trainer", "max_courses_per_user")

# [local_capability]: per task class, the local model that answers it, or "cloud-only".
_CAPABILITY_SECTION = "local_capability"
CAPABILITY_VALUES = frozenset({"kata-l", "kata-m", "cloud-only"})


class ConfigError(Exception):
    """Config file missing, unreadable, incomplete, or holding a bad override."""


@dataclass(frozen=True)
class Config:
    sections: Mapping[str, Mapping[str, Any]]

    def get(self, section: str, key: str) -> Any:
        try:
            return self.sections[section][key]
        except KeyError as exc:
            raise ConfigError(f"no key {section}.{key}") from exc


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read config {path}: {exc}") from exc


def _cast(raw: str, template: Any, name: str) -> Any:
    try:
        if isinstance(template, bool):
            lowered = raw.strip().lower()
            if lowered in _TRUE:
                return True
            if lowered in _FALSE:
                return False
            raise ValueError(raw)
        if isinstance(template, int):
            return int(raw)
        if isinstance(template, float):
            return float(raw)
        if isinstance(template, list):
            # Comma-separated list; an unsplit string would make list membership a substring test.
            return [item.strip() for item in raw.split(",") if item.strip()]
        return raw
    except ValueError as exc:
        raise ConfigError(f"env override {name} is not a valid {type(template).__name__}") from exc


def _is_course_limit(value: Any) -> bool:
    # bool is an int subclass in Python; TOML true/false must not pass as a limit.
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return value >= MAX_COURSES_UNLIMITED


def load_config(
    path: str | os.PathLike[str] | None = None,
    env: Mapping[str, str] = os.environ,
) -> Config:
    """Load the config file at `path` (or env KATA_CONFIG), then apply env overrides."""
    file_arg = path if path is not None else env.get(CONFIG_ENV)
    if file_arg is None:
        raise ConfigError(f"no config path: pass path or set {CONFIG_ENV}")
    file_data = _read_toml(Path(file_arg))
    schema = _read_toml(EXAMPLE_PATH)

    sections: dict[str, Mapping[str, Any]] = {}
    for section, keys in schema.items():
        if not isinstance(keys, dict):
            raise ConfigError(f"example section {section} is not a table")
        given = file_data.get(section)
        if not isinstance(given, dict):
            raise ConfigError(f"missing section [{section}] in {file_arg}")
        values: dict[str, Any] = {}
        for field in keys:
            if field not in given:
                raise ConfigError(f"missing key {section}.{field} in {file_arg}")
            value = given[field]
            env_name = f"{ENV_PREFIX}_{section}_{field}".upper()
            if env_name in env:
                value = _cast(env[env_name], value, env_name)
            if (section, field) == _COURSE_LIMIT_KEY and not _is_course_limit(value):
                raise ConfigError(
                    f"{section}.{field} must be an integer >= {MAX_COURSES_UNLIMITED} "
                    f"(0 = unlimited), got a {type(value).__name__}"
                )
            if section == _CAPABILITY_SECTION and not (
                isinstance(value, str) and value in CAPABILITY_VALUES
            ):
                raise ConfigError(
                    f"{section}.{field} must be one of {sorted(CAPABILITY_VALUES)}, "
                    f"got a {type(value).__name__}"
                )
            values[field] = value
        sections[section] = MappingProxyType(values)
    return Config(sections=MappingProxyType(sections))
