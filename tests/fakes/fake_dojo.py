"""Fake `dojo` CLI: a python script run as `[sys.executable, <this file>, <subcommand>, <dir>, ...]`.

Prints the text formats measured on the real dojo binary (see core/kata_core/trainer/dojo_cli.py).
Items live in `<dir>/content/<unit>.jsonl`; ids are `<unit>-<n>`. Markers in a prompt:
FAKE_INVALID gives an error diagnostic that names the item id; FAKE_NOID gives an error with
no id in its message; FAKE_WARN gives a warning only (exit 0). A gap with a blank answer gives an
error that names the item id.
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

CONTENT_DIR = "content"
TITLE_CHARS = 80
INVALID_MARK = "FAKE_INVALID"
# When set, every `build` call appends its argv as one JSON list per line to this file.
ARGV_LOG_ENV = "FAKE_DOJO_ARGV_LOG"
NOID_MARK = "FAKE_NOID"
WARN_MARK = "FAKE_WARN"
PREFIX_RE = re.compile(r"[a-z][a-z0-9_-]*")
# Course ids for `init`: lowercase letters, digits and `-` only.
COURSE_ID_RE = re.compile(r"[a-z0-9-]+")
COURSE_FILE = "course.json"


def _read_items(workdir: Path) -> list[tuple[str, dict[str, Any]]]:
    """(id, item) pairs of every unit file, in file order."""
    out: list[tuple[str, dict[str, Any]]] = []
    for path in sorted((workdir / CONTENT_DIR).glob("*.jsonl")):
        for line in path.read_text().splitlines():
            if line:
                item = json.loads(line)
                out.append((item["id"], item))
    return out


def _init(course_id: str, title: str, workspace: Path) -> int:
    if not COURSE_ID_RE.fullmatch(course_id):
        sys.stderr.write(f"fake dojo: bad course id {course_id!r}: use lowercase letters, digits and '-'\n")
        return 2
    # Strict like the real dojo: no control characters, at most TITLE_CHARS characters.
    if len(title) > TITLE_CHARS or any(unicodedata.category(ch) == "Cc" for ch in title):
        sys.stderr.write(f"fake dojo: bad course title {title!r}\n")
        return 2
    course = workspace / course_id
    course.mkdir(parents=True, exist_ok=True)
    units = ["unit-1"]
    (course / COURSE_FILE).write_text(json.dumps({"id": course_id, "title": title, "units": units}))
    print(f"Created course {course_id} in {course}")
    return 0


def _next_number(workdir: Path, unit: str) -> int:
    path = workdir / CONTENT_DIR / f"{unit}.jsonl"
    if not path.exists():
        return 1
    return sum(1 for line in path.read_text().splitlines() if line) + 1


def _units(workdir: Path) -> list[str] | None:
    """Units of the course folder; None (after a message) when the folder has no course.json."""
    course_file = workdir / COURSE_FILE
    if not course_file.is_file():
        sys.stderr.write(f"fake dojo: no course.json in {workdir}\n")
        return None
    return list(json.loads(course_file.read_text())["units"])


def _next_id(workdir: Path, prefix: str) -> int:
    if not PREFIX_RE.fullmatch(prefix):
        sys.stderr.write(f"fake dojo: bad prefix {prefix!r}\n")
        raise SystemExit(2)
    if _units(workdir) is None:
        return 1
    print(f"{prefix}-{_next_number(workdir, prefix)}")
    return 0


def _add(workdir: Path, unit: str) -> int:
    units = _units(workdir)
    if units is None:
        return 1
    if unit not in units:
        sys.stderr.write(f"fake dojo: unit {unit!r} does not exist in course.json\n")
        return 1
    data = json.loads(sys.stdin.read())
    items = data if isinstance(data, list) else [data]
    for item in items:
        if not isinstance(item, dict) or "type" not in item:
            sys.stderr.write("fake dojo: shape error: item needs a type\n")
            return 1
    path = workdir / CONTENT_DIR / f"{unit}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    ids: list[str] = []
    number = _next_number(workdir, unit)
    with path.open("a") as out:
        for item in items:
            item_id = f"{unit}-{number}"
            number += 1
            ids.append(item_id)
            out.write(json.dumps({**item, "id": item_id}) + "\n")
    print(f"added {len(ids)} items to content/{unit}.jsonl: {ids[0]} .. {ids[-1]}")
    for item_id in ids:
        print(item_id)
    return 0


def _validate(workdir: Path) -> int:
    if _units(workdir) is None:
        return 2
    diagnostics: list[dict[str, Any]] = []
    for item_id, item in _read_items(workdir):
        prompt = str(item.get("prompt", ""))
        base = {"file": f"content/{item['unit']}.jsonl", "line": 1}
        if INVALID_MARK in prompt:
            message = f"{item_id}: fake marked invalid"
            diagnostics.append({"severity": "error", "code": "choice_few_options", **base, "message": message})
        if NOID_MARK in prompt:
            message = "answers list is empty"
            diagnostics.append({"severity": "error", "code": "gap_empty_answer", **base, "message": message})
        if any(not str(answer).strip() for answer in item.get("answers", [])):
            message = f"{item_id}: gap answer is empty"
            diagnostics.append({"severity": "error", "code": "gap_empty_answer", **base, "message": message})
        if WARN_MARK in prompt:
            message = f"{item_id}: fake warning"
            diagnostics.append({"severity": "warning", "code": "answer_in_prompt", **base, "message": message})
    errors = sum(1 for d in diagnostics if d["severity"] == "error")
    print(json.dumps({"ok": errors == 0, "errors": errors,
                      "warnings": len(diagnostics) - errors, "diagnostics": diagnostics}))
    return 1 if errors else 0


def _lock(workdir: Path) -> int:
    if any(INVALID_MARK in str(i.get("prompt", "")) for _, i in _read_items(workdir)):
        print("content/geo.jsonl:1: error: fake marked invalid")
        return 1
    count = len(_read_items(workdir))
    (workdir / "ids.lock").write_text(f"ids.lock: {count} ids, 0 retired\n")
    print(f"ids.lock: {count} ids, 0 retired")
    return 0


def _build(workdir: Path, outdir: Path) -> int:
    if any(INVALID_MARK in str(i.get("prompt", "")) for _, i in _read_items(workdir)):
        sys.stderr.write("fake dojo: content errors, not built\n")
        return 1
    course = workdir.name
    site = outdir / course
    (site / "data").mkdir(parents=True, exist_ok=True)
    (site / "index.html").write_text("<!doctype html>\n")
    (site / "data" / "content.json").write_text(json.dumps([i for _, i in _read_items(workdir)]))
    files = ["data/content.json", "manifest.json", "index.html"]
    (site / "manifest.json").write_text(json.dumps({"course": course, "files": files}))
    print(f"built {course} version 1 -> {site}")
    for name in sorted(files):
        print(f"  {course}/{name}")
    return 0


def _log_argv(argv: list[str]) -> None:
    log = os.environ.get(ARGV_LOG_ENV, "")
    if log:
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(argv) + "\n")


def main(argv: list[str]) -> int:
    subcommand, rest = argv[0], argv[1:]
    if subcommand == "init":
        # init <course_id> --title <T> --workspace <dir>
        return _init(rest[0], rest[2], Path(rest[4]))
    if subcommand == "next-id":
        return _next_id(Path(rest[0]), rest[1])
    if subcommand == "add":
        return _add(Path(rest[0]), rest[1])
    if subcommand == "validate":
        if not Path(rest[0]).is_dir():
            sys.stderr.write("fake dojo: no such dir\n")
            return 2
        return _validate(Path(rest[0]))
    if subcommand == "lock":
        return _lock(Path(rest[0]))
    if subcommand == "build":
        _log_argv(argv)
        return _build(Path(rest[0]), Path(rest[2]))
    sys.stderr.write(f"fake dojo: unknown subcommand {subcommand}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
