"""Trainer CLI wrapper (D7): five calls to the external trainer binary, one JSON object per call on stdout.

Each call runs as `argv_prefix + [subcommand, --workdir, ...]`. The argv list is never passed to a
shell. Trust boundary: `argv_prefix` comes from config `[trainer] command` (a TOML array), so the
configured executable runs with the core's privileges. Review it like any other config-supplied
command (sec-auditor note).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class TrainerError(Exception):
    """The trainer failed: non-zero exit, timeout, missing executable, or output off the JSON contract."""


@dataclass(frozen=True)
class Diagnostic:
    item: str
    message: str


class TrainerCli(Protocol):
    def next_id(self, workdir: Path) -> str: ...

    def add(self, workdir: Path, item: str) -> str: ...

    def validate(self, workdir: Path) -> list[Diagnostic]: ...

    def lock(self, workdir: Path) -> None: ...

    def build(self, workdir: Path, outdir: Path) -> list[str]: ...


@dataclass(frozen=True)
class SubprocessTrainerCli:
    """Runs the trainer binary named by `argv_prefix`; `timeout` is in seconds per call."""

    argv_prefix: list[str]
    timeout: float

    def _call(self, subcommand: str, *args: str) -> dict[str, Any]:
        argv = [*self.argv_prefix, subcommand, *args]
        try:
            proc = subprocess.run(
                argv, capture_output=True, text=True, timeout=self.timeout, check=False
            )
        except subprocess.TimeoutExpired as exc:
            raise TrainerError(f"trainer {subcommand} timed out after {self.timeout}s") from exc
        except OSError as exc:
            raise TrainerError(f"trainer {subcommand} could not start: {exc}") from exc
        if proc.returncode != 0:
            raise TrainerError(
                f"trainer {subcommand} exited {proc.returncode}: {proc.stderr.strip()}"
            )
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise TrainerError(f"trainer {subcommand} printed invalid JSON") from exc
        if not isinstance(data, dict):
            raise TrainerError(f"trainer {subcommand} JSON is not an object")
        return data

    def next_id(self, workdir: Path) -> str:
        return _str_field(self._call("next-id", f"--workdir={workdir}"), "id", "next-id")

    def add(self, workdir: Path, item: str) -> str:
        data = self._call("add", f"--workdir={workdir}", f"--item={item}")
        return _str_field(data, "id", "add")

    def validate(self, workdir: Path) -> list[Diagnostic]:
        data = self._call("validate", f"--workdir={workdir}")
        raw = data.get("diagnostics")
        if not isinstance(raw, list):
            raise TrainerError("trainer validate: diagnostics is not a list")
        out: list[Diagnostic] = []
        for entry in raw:
            if not isinstance(entry, dict):
                raise TrainerError("trainer validate: diagnostic is not an object")
            out.append(
                Diagnostic(
                    item=_str_field(entry, "item", "validate"),
                    message=_str_field(entry, "message", "validate"),
                )
            )
        return out

    def lock(self, workdir: Path) -> None:
        if self._call("lock", f"--workdir={workdir}").get("ok") is not True:
            raise TrainerError("trainer lock did not report ok")

    def build(self, workdir: Path, outdir: Path) -> list[str]:
        data = self._call("build", f"--workdir={workdir}", f"--outdir={outdir}")
        files = data.get("files")
        if not isinstance(files, list) or not all(isinstance(f, str) for f in files):
            raise TrainerError("trainer build: files is not a list of strings")
        return list(files)


def _str_field(data: dict[str, Any], key: str, subcommand: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise TrainerError(f"trainer {subcommand}: {key} is not a string")
    return value
