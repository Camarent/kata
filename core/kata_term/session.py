"""Run a command in a pty, relay bytes both ways, and report command lines and error kinds.

Stdlib only. `on_command` gets the raw line typed on stdin (masking is the caller's job, see
mask.py). `on_error` gets a kind from ERROR_KINDS, never the output text. Output is only
relayed to `stdout_fd` and scanned; the scan keeps a short tail so a pattern split across two
reads still matches. Nothing here logs or prints.
"""

from __future__ import annotations

import os
import select
import subprocess
from collections.abc import Callable, Mapping

POLL_SECONDS = 0.1  # bounded select timeout: the loop re-checks the child at this rate
READ_SIZE = 4096
EOF_BYTE = b"\x04"  # Ctrl-D: tells the child its stdin ended
ERASE_CHARS = ("\x7f", "\x08")  # DEL and BS erase one character of the line buffer
LINE_END = ("\r", "\n")

# (text to find, kind reported to on_error). Kinds only: the matched text is never passed on.
ERROR_PATTERNS: tuple[tuple[str, str], ...] = (
    ("command not found", "not_found"),
    ("Traceback (most recent call last)", "traceback"),
    ("Permission denied", "permission"),
    ("error:", "error"),
)
ERROR_KINDS: frozenset[str] = frozenset(kind for _, kind in ERROR_PATTERNS)
_TAIL_LEN = max(len(text) for text, _ in ERROR_PATTERNS) - 1


def run_session(
    argv: list[str],
    on_command: Callable[[str], None],
    on_error: Callable[[str], None],
    stdin_fd: int,
    stdout_fd: int,
    env: Mapping[str, str] | None = None,
) -> int:
    """Run `argv` on a pty until the child exits; return its exit code.

    `env` is the child's environment; None inherits this process's environment.
    """
    master, slave = os.openpty()
    try:
        proc = subprocess.Popen(
            argv,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            start_new_session=True,
            close_fds=True,
            env=env,
        )
    except BaseException:
        os.close(master)
        os.close(slave)
        raise
    os.close(slave)  # the child holds its own copy now
    try:
        _relay(master, proc, stdin_fd, stdout_fd, on_command, on_error)
        return proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        os.close(master)


def _relay(
    master: int,
    proc: subprocess.Popen[bytes],
    stdin_fd: int,
    stdout_fd: int,
    on_command: Callable[[str], None],
    on_error: Callable[[str], None],
) -> None:
    """Pump bytes until the pty closes or the child exits."""
    line: list[str] = []
    tail = ""
    stdin_open = True
    while True:
        watched = [master, stdin_fd] if stdin_open else [master]
        ready, _, _ = select.select(watched, [], [], POLL_SECONDS)
        if master in ready:
            try:
                data = os.read(master, READ_SIZE)
            except OSError:  # EIO: the child closed its side of the pty
                return
            if not data:
                return
            _write_all(stdout_fd, data)
            tail = _scan_errors(data.decode("utf-8", errors="replace"), tail, on_error)
        elif proc.poll() is not None:
            return
        if stdin_open and stdin_fd in ready:
            data = os.read(stdin_fd, READ_SIZE)
            if not data:
                stdin_open = False
                _send(master, EOF_BYTE)
            else:
                if not _send(master, data):
                    stdin_open = False
                    continue
                _feed_line(data.decode("utf-8", errors="replace"), line, on_command)


def _feed_line(text: str, line: list[str], on_command: Callable[[str], None]) -> None:
    """Edit the line buffer with typed characters; report each completed non-empty line."""
    for char in text:
        if char in LINE_END:
            if line and "".join(line).strip():
                on_command("".join(line))
            line.clear()
        elif char in ERASE_CHARS:
            if line:
                line.pop()
        else:
            line.append(char)


def _scan_errors(text: str, tail: str, on_error: Callable[[str], None]) -> str:
    """Report each error kind whose pattern ends in `text`, not in the kept tail; return new tail."""
    window = tail + text
    old = len(tail)
    for needle, kind in ERROR_PATTERNS:
        # Start one character before the new text so a match ending in `text` is found.
        if window.find(needle, max(0, old - len(needle) + 1)) != -1:
            on_error(kind)
    return window[-_TAIL_LEN:] if _TAIL_LEN else ""


def _send(master: int, data: bytes) -> bool:
    """Write to the child's side; False when the child has already gone."""
    try:
        _write_all(master, data)
    except OSError:
        return False
    return True


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]
