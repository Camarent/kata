"""Trainer CLI contract: the errors, the diagnostic record and the Protocol every trainer adapter meets.

The adapter for the dojo binary lives in `dojo_cli.py`. Each adapter runs its argv list (from config
`[trainer] command`) without a shell; that config value is a trust boundary (sec-auditor note).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class TrainerError(Exception):
    """The trainer failed: non-zero exit, timeout, missing executable, or output off the JSON contract."""


@dataclass(frozen=True)
class Diagnostic:
    item: str
    message: str


class TrainerCli(Protocol):
    def next_id(self, workdir: Path, unit: str) -> str: ...

    def add(self, workdir: Path, item: str) -> str: ...

    def validate(self, workdir: Path) -> list[Diagnostic]: ...

    def lock(self, workdir: Path) -> None: ...

    def build(self, workdir: Path, outdir: Path) -> list[str]: ...
