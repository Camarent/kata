"""Adapter for the public `dojo` CLI (dojo-kit release), measured on the real binary (2026-11-23).

Each call runs as `argv_prefix + [subcommand, <dir>, ...]`. The argv list is never passed to a
shell. Trust boundary: `argv_prefix` comes from config `[trainer] command`, as in cli.py.
Exit codes: 0 ok; 1 content errors (diagnostics on stdout, or stderr for shape errors);
2 usage or I/O errors.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kata_core.trainer.cli import Diagnostic, TrainerError

# An item id as `dojo` prints it: `<unit>-<n>`. Only used to find the id inside a diagnostic message.
ID_IN_MESSAGE = re.compile(r"(?<![\w-])([A-Za-z][\w-]*-\d+)(?![\w-])")
# A unit name: letters, digits, `_` and `-`. Anything else (`/`, `..`, whitespace, shell characters) is refused.
UNIT_NAME = re.compile(r"[A-Za-z0-9_-]+")
# `dojo add` prints: `added N items to content/<unit>.jsonl: <first> .. <last>`, then the ids.
ADDED_HEADER = re.compile(r"^added \d+ items? to .*?: (\S+) \.\. (\S+)$", re.MULTILINE)
INDEX_FILE = "index.html"
MANIFEST_FILE = "manifest.json"


@dataclass(frozen=True)
class DojoTrainerCli:
    """Runs the `dojo` binary named by `argv_prefix`; `timeout` is in seconds per call."""

    argv_prefix: list[str]
    timeout: float

    def _run(
        self, subcommand: str, args: list[str], stdin: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        argv = [*self.argv_prefix, subcommand, *args]
        try:
            return subprocess.run(
                argv,
                input=stdin,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TrainerError(f"dojo {subcommand} timed out after {self.timeout}s") from exc
        except OSError as exc:
            raise TrainerError(f"dojo {subcommand} could not start: {exc}") from exc

    def next_id(self, workdir: Path, unit: str) -> str:
        _check_unit(unit)
        proc = self._run("next-id", [str(workdir), unit])
        _require_zero("next-id", proc)
        lines = proc.stdout.strip().splitlines()
        if len(lines) != 1 or not lines[0].startswith(f"{unit}-"):
            raise TrainerError(f"dojo next-id printed no id for unit {unit!r}")
        return lines[0]

    def add(self, workdir: Path, item: str) -> str:
        unit = _unit_of(item)
        proc = self._run("add", [str(workdir), unit], stdin=item)
        _require_zero("add", proc)
        match = ADDED_HEADER.search(proc.stdout)
        if match is None or match.group(1) != match.group(2):
            raise TrainerError("dojo add printed no single id")
        added = match.group(1)
        if not added.startswith(f"{unit}-"):
            raise TrainerError(f"dojo add gave id {added!r} for unit {unit!r}")
        return added

    def validate(self, workdir: Path) -> list[Diagnostic]:
        proc = self._run("validate", [str(workdir), "--json"])
        if proc.returncode not in (0, 1):
            raise _failure("validate", proc)
        data = _json_object(proc.stdout, "validate")
        raw = data.get("diagnostics")
        if not isinstance(raw, list):
            raise TrainerError("dojo validate: diagnostics is not a list")
        errors = data.get("errors")
        if proc.returncode == 1 and (not isinstance(errors, int) or errors < 1):
            raise TrainerError("dojo validate exited 1 but reports no errors")
        out: list[Diagnostic] = []
        for entry in raw:
            if not isinstance(entry, dict):
                raise TrainerError("dojo validate: diagnostic is not an object")
            message = _text_field(entry, "message", "validate")
            out.append(Diagnostic(item=_item_of(entry, message), message=message))
        return out

    def lock(self, workdir: Path) -> None:
        _require_zero("lock", self._run("lock", [str(workdir)]))

    def build(self, workdir: Path, outdir: Path) -> list[str]:
        _require_zero("build", self._run("build", [str(workdir), "--out", str(outdir)]))
        course_dir = _only_course_dir(outdir)
        return _artifact_files(course_dir)


def _check_unit(unit: str) -> None:
    if not UNIT_NAME.fullmatch(unit) or unit.startswith("-"):
        raise TrainerError(f"invalid unit {unit!r}")


def _unit_of(item: str) -> str:
    """The unit positional comes from the item's own `unit` field; it is required."""
    try:
        data = json.loads(item)
    except json.JSONDecodeError as exc:
        raise TrainerError("dojo add: item is not JSON") from exc
    unit = data.get("unit") if isinstance(data, dict) else None
    if not isinstance(unit, str):
        raise TrainerError("dojo add: item has no unit")
    _check_unit(unit)
    return unit


def _require_zero(subcommand: str, proc: subprocess.CompletedProcess[str]) -> None:
    if proc.returncode != 0:
        raise _failure(subcommand, proc)


def _failure(subcommand: str, proc: subprocess.CompletedProcess[str]) -> TrainerError:
    detail = (proc.stderr or proc.stdout).strip()
    return TrainerError(f"dojo {subcommand} exited {proc.returncode}: {detail}")


def _json_object(text: str, subcommand: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TrainerError(f"dojo {subcommand} printed invalid JSON") from exc
    if not isinstance(data, dict):
        raise TrainerError(f"dojo {subcommand} JSON is not an object")
    return data


def _text_field(entry: dict[str, Any], key: str, subcommand: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str):
        raise TrainerError(f"dojo {subcommand}: {key} is not a string")
    return value


def _item_of(entry: dict[str, Any], message: str) -> str:
    """The item id named in the message; without one, the `file:line` of the diagnostic."""
    found = ID_IN_MESSAGE.search(message)
    if found is not None:
        return found.group(1)
    return f"{entry.get('file')}:{entry.get('line')}"


def _only_course_dir(outdir: Path) -> Path:
    """A build writes exactly one course folder `<outdir>/<course_id>/`."""
    dirs = sorted(p for p in outdir.iterdir() if p.is_dir()) if outdir.is_dir() else []
    if len(dirs) != 1:
        raise TrainerError(f"dojo build wrote {len(dirs)} course dirs, expected 1")
    return dirs[0]


def _artifact_files(course_dir: Path) -> list[str]:
    """Course files as paths relative to the out dir: the manifest's `files` list when present, else a walk."""
    names = _manifest_files(course_dir)
    if names is None:
        walked = list(course_dir.rglob("*"))
        for path in walked:
            if path.is_symlink():
                raise TrainerError(f"dojo build: {path.relative_to(course_dir).as_posix()!r} is a symlink")
        names = sorted(p.relative_to(course_dir).as_posix() for p in walked if p.is_file())
    for name in names:
        _check_artifact(course_dir, name)
    return [f"{course_dir.name}/{name}" for name in names]


def _check_artifact(course_dir: Path, name: str) -> None:
    """A listed file must be a real file inside the course dir: no absolute path, no `..`, no symlink."""
    path = course_dir / name
    if Path(name).is_absolute() or ".." in Path(name).parts or not path.is_file():
        raise TrainerError(f"dojo build: file {name!r} is missing or outside the course dir")
    if path.is_symlink() or not path.resolve().is_relative_to(course_dir.resolve()):
        raise TrainerError(f"dojo build: file {name!r} is a symlink or outside the course dir")


def _manifest_files(course_dir: Path) -> list[str] | None:
    manifest = course_dir / MANIFEST_FILE
    if not manifest.is_file():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TrainerError("dojo build: manifest.json is unreadable") from exc
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, list) or not all(isinstance(f, str) for f in files):
        return None
    return sorted({*files, INDEX_FILE})
