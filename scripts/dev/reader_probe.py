"""Live probe of the reader container: feed hostile files through the spool, check the sandbox, write a report.

Usage:
  python3 -I scripts/dev/reader_probe.py --make-corpus DIR
  python3 -I scripts/dev/reader_probe.py --run --compose-file F --env-file E --project P --files DIR --report PATH
  python3 -I scripts/dev/reader_probe.py --check-report PATH

--make-corpus writes five synthetic hostile files (stdlib only).
--run feeds each file of --files through the worker's /spool/in (body .bin first, marker .json last),
polls the reader's /spool/out/<id>/result.json, runs two sandbox checks inside the reader container,
and writes the markdown report. Every docker call goes through an injected runner; the clock is injected.
--check-report exits 0 only when the report passes the rules in check_report().

Report sections: '## Files' (table), '## Sandbox checks' ('connect: blocked|OPEN', 'write: blocked|OPEN'),
'## Findings' (one bullet per row not at its expected status or sandbox check not blocked, else 'none'), '## End to end' ('Status: done|pending').
A hostile file (EXPECTED_REFUSAL) is expected to be refused with its own code; every other row must be done.
Exit codes: 0 pass, 1 a check failed, 2 a missing file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import struct
import subprocess
import sys
import time
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

WORKER_SERVICE = "worker"
READER_SERVICE = "reader"
IN_DIR = "/spool/in"
OUT_DIR = "/spool/out"
RESULT_NAME = "result.json"
SPOOL_VERSION = 1
SPOOL_OK = "ok"  # status of a successful result.json (reader/kata_reader/extract.py)
POLL_SECONDS = 1.0
TIMEOUT_SECONDS = 120.0
BLOCKED = "blocked"
OPEN = "OPEN"
ERROR = "error"  # a check whose exec failed: it did not run, so it is neither blocked nor OPEN
DONE = "done"
PENDING = "pending"
MEDIA_BY_SUFFIX = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
# The reader's refusal status of each synthetic hostile file (make_corpus). A refusal is the expected
# result for these rows; a real file must be done. Keep in step with the reader's extract() codes.
EXPECTED_REFUSAL = {
    "empty.pdf": "bad_type",
    "bad_magic.pdf": "bad_type",
    "truncated.pdf": "bad_file",
    "huge_declared.png": "bad_file",
    "trailing_junk.png": "bad_file",
}

SECTION_FILES = "Files"
SECTION_SANDBOX = "Sandbox checks"
SECTION_FINDINGS = "Findings"
SECTION_END = "End to end"
REQUIRED_SECTIONS = (SECTION_FILES, SECTION_SANDBOX, SECTION_FINDINGS, SECTION_END)
TABLE_LINE = re.compile(r"^\s*\|")
SEPARATOR_ROW = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")
CHECK_LINE = re.compile(r"^(connect|write):\s*(\S+)\s*$")

# Runs inside the worker container: body first, marker last, so a marker means the body is complete.
WRITE_SPOOL = """
import sys
d, doc_id, marker = sys.argv[1:4]
body = sys.stdin.buffer.read()
with open(f"{d}/{doc_id}.bin", "xb") as f:
    f.write(body)
with open(f"{d}/{doc_id}.json", "x", encoding="utf-8") as f:
    f.write(marker)
"""
# Runs inside the reader container. Prints 'blocked' when the connect fails, 'OPEN' when it works.
CONNECT_CHECK = """
import socket
s = socket.socket()
s.settimeout(3)
try:
    s.connect(("192.0.2.1", 80))
except OSError:
    print("blocked")
else:
    print("OPEN")
"""
# Prints 'blocked' when a write outside /tmp and /spool/out fails, 'OPEN' when it succeeds.
WRITE_CHECK = """
import os
path = "/probe-write-check.txt"
try:
    with open(path, "w") as f:
        f.write("probe")
except OSError:
    print("blocked")
else:
    os.remove(path)
    print("OPEN")
"""

# A runner runs argv inside one compose service with stdin, returns (exit code, stdout).
Runner = Callable[[str, list[str], bytes], tuple[int, bytes]]


class Clock(Protocol):
    def now(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


@dataclass(frozen=True)
class Row:
    name: str
    media: str
    status: str
    pages: int


def make_corpus(directory: Path) -> list[Path]:
    """Write the five hostile files into directory and return their paths."""
    directory.mkdir(parents=True, exist_ok=True)
    png_head = b"\x89PNG\r\n\x1a\n"
    huge_ihdr = struct.pack(">II", 0x7FFFFFFF, 0x7FFFFFFF) + b"\x08\x02\x00\x00\x00"
    huge_png = png_head + struct.pack(">I", 13) + b"IHDR" + huge_ihdr + struct.pack(">I", 0)
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND"))
    files = {
        "empty.pdf": b"",
        "bad_magic.pdf": b"NOTAPDF-" + b"x" * 64,
        "truncated.pdf": b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog",
        "huge_declared.png": huge_png,
        "trailing_junk.png": png_head + iend + b"JUNK" * 16,
    }
    paths = []
    for name, data in files.items():
        path = directory / name
        path.write_bytes(data)
        paths.append(path)
    return paths


def make_compose_runner(compose_file: Path, env_file: Path, project: str) -> Runner:
    """Runner that execs argv in a compose service through docker compose."""
    base = ["docker", "compose", "-f", str(compose_file), "--env-file", str(env_file), "-p", project]

    def run(service: str, argv: list[str], stdin: bytes) -> tuple[int, bytes]:
        proc = subprocess.run(
            [*base, "exec", "-T", service, *argv], input=stdin, capture_output=True, check=False
        )
        return proc.returncode, proc.stdout

    return run


def _feed(runner: Runner, data: bytes, doc_id: str, media: str) -> bool:
    marker = json.dumps(
        {
            "v": SPOOL_VERSION,
            "id": doc_id,
            "media_type": media,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        },
        sort_keys=True,
    )
    code, _ = runner(WORKER_SERVICE, ["python", "-I", "-c", WRITE_SPOOL, IN_DIR, doc_id, marker], data)
    return code == 0


def _await_result(
    runner: Runner, doc_id: str, clock: Clock, poll_seconds: float, timeout_seconds: float
) -> bytes | None:
    """Poll out/<id>/result.json until it exists or the timeout passes. Returns None on timeout."""
    deadline = clock.now() + timeout_seconds
    while True:
        code, out = runner(READER_SERVICE, ["cat", f"{OUT_DIR}/{doc_id}/{RESULT_NAME}"], b"")
        if code == 0:
            return out
        if clock.now() >= deadline:
            return None
        clock.sleep(poll_seconds)


def _row(name: str, media: str, runner: Runner, data: bytes, clock: Clock, poll: float, timeout: float) -> Row:
    doc_id = secrets.token_hex(16)
    if not _feed(runner, data, doc_id, media):
        return Row(name, media, "feed_error", 0)
    raw = _await_result(runner, doc_id, clock, poll, timeout)
    if raw is None:
        return Row(name, media, "timeout", 0)
    try:
        result = json.loads(raw)
        if result["status"] == SPOOL_OK:
            return Row(name, media, DONE, len(result["pages"]))
        return Row(name, media, str(result.get("error") or "error"), 0)
    except (ValueError, KeyError, TypeError):
        return Row(name, media, "bad_result", 0)


def run_probe(
    files: list[Path],
    runner: Runner,
    clock: Clock,
    poll_seconds: float = POLL_SECONDS,
    timeout_seconds: float = TIMEOUT_SECONDS,
) -> list[Row]:
    """Feed each file through the spool and return one row per file."""
    rows = []
    for path in files:
        media = MEDIA_BY_SUFFIX[path.suffix.lower()]
        rows.append(_row(path.name, media, runner, path.read_bytes(), clock, poll_seconds, timeout_seconds))
    return rows


def run_sandbox_checks(runner: Runner) -> dict[str, str]:
    """Run the connect and write checks in the reader container. A check whose exec fails is ERROR."""
    results = {}
    for name, snippet in (("connect", CONNECT_CHECK), ("write", WRITE_CHECK)):
        code, out = runner(READER_SERVICE, ["python", "-I", "-c", snippet], b"")
        if code != 0:
            results[name] = ERROR
        else:
            results[name] = BLOCKED if out.decode().strip() == BLOCKED else OPEN
    return results


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def _cells(line: str) -> list[str]:
    """The cells of one markdown table row; escaped pipes (see _cell) do not split a cell."""
    return re.split(r"(?<!\\)\|", line.strip())[1:-1]


def expected_status(name: str) -> str:
    """The status a row must have: its refusal code for a hostile file, else done."""
    return EXPECTED_REFUSAL.get(name, DONE)


def build_report(rows: list[Row], checks: dict[str, str]) -> str:
    """The markdown report for one run."""
    findings = [f"- {row.name}: {row.status}" for row in rows if row.status != expected_status(row.name)]
    findings += [f"- sandbox {name}: {value}" for name, value in checks.items() if value != BLOCKED]
    end_status = DONE if rows and all(row.status == expected_status(row.name) for row in rows) else PENDING
    lines = ["# Reader live probe", "", f"## {SECTION_FILES}", "", "| file | media type | status | pages |", "|---|---|---|---|"]
    lines += [f"| {_cell(r.name)} | {r.media} | {_cell(r.status)} | {r.pages} |" for r in rows]
    lines += ["", f"## {SECTION_SANDBOX}", ""]
    lines += [f"{name}: {checks[name]}" for name in ("connect", "write")]
    lines += ["", f"## {SECTION_FINDINGS}", ""]
    lines += findings or ["- none"]
    lines += ["", f"## {SECTION_END}", "", f"Status: {end_status}", ""]
    return "\n".join(lines)


def _sections(text: str) -> dict[str, list[str]]:
    """Map each '## ' heading to the lines under it."""
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = sections.setdefault(line[3:].strip(), [])
        elif current is not None:
            current.append(line)
    return sections


def check_report(text: str) -> list[str]:
    """Problems with a report, one message each. Empty list means the report passes."""
    sections = _sections(text)
    problems = [f"missing section: {name}" for name in REQUIRED_SECTIONS if name not in sections]
    if SECTION_FILES in sections:
        table = [line for line in sections[SECTION_FILES] if TABLE_LINE.match(line) and not SEPARATOR_ROW.match(line)]
        if len(table) < 2:
            problems.append("Files: no rows")
        for line in table[1:]:  # table[0] is the header row
            cells = _cells(line)
            if len(cells) != 4:  # file, media type, status, pages
                problems.append(f"Files: malformed row: {line.strip()}")
                continue
            name, status = cells[0].strip(), cells[2].strip()
            expected = expected_status(name)
            if status != expected:
                problems.append(f"file {name}: {status}, must be {expected}")
    if SECTION_SANDBOX in sections:
        found = {}
        for line in sections[SECTION_SANDBOX]:
            match = CHECK_LINE.match(line)
            if match:
                found[match.group(1)] = match.group(2)
        for name in ("connect", "write"):
            if name not in found:
                problems.append(f"sandbox {name}: no result line")
            elif found[name] != BLOCKED:
                problems.append(f"sandbox {name}: {found[name]}, must be {BLOCKED}")
    if SECTION_END in sections and f"Status: {DONE}" not in (line.strip() for line in sections[SECTION_END]):
        problems.append(f"end to end: not 'Status: {DONE}'")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live probe of the reader container.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--make-corpus", type=Path, metavar="DIR", help="write the five hostile files to DIR")
    group.add_argument("--run", action="store_true", help="feed the files and write the report")
    group.add_argument("--check-report", type=Path, metavar="PATH", help="check a report file")
    parser.add_argument("--compose-file", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--project")
    parser.add_argument("--files", type=Path, metavar="DIR")
    parser.add_argument("--report", type=Path, metavar="PATH")
    args = parser.parse_args(argv)

    if args.make_corpus is not None:
        make_corpus(args.make_corpus)
        return 0
    if args.check_report is not None:
        if not args.check_report.is_file():
            print(f"reader_probe: no such file: {args.check_report}", file=sys.stderr)
            return 2
        problems = check_report(args.check_report.read_text(encoding="utf-8"))
        for message in problems:
            print(f"reader_probe: {message}", file=sys.stderr)
        return 1 if problems else 0
    missing = [flag for flag, value in (("--compose-file", args.compose_file), ("--env-file", args.env_file),
                                        ("--project", args.project), ("--files", args.files),
                                        ("--report", args.report)) if value is None]
    if missing:
        parser.error(f"--run needs {', '.join(missing)}")
    runner = make_compose_runner(args.compose_file, args.env_file, args.project)
    files = sorted(p for p in args.files.iterdir() if p.is_file() and p.suffix.lower() in MEDIA_BY_SUFFIX)
    rows = run_probe(files, runner, SystemClock())
    checks = run_sandbox_checks(runner)
    args.report.write_text(build_report(rows, checks), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
