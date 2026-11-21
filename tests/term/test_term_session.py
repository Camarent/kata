"""PTY session: run a child in a pty, capture command lines and error kinds, shut down cleanly."""

import os
from collections.abc import Callable

import pytest
from kata_term.session import ERROR_KINDS, run_session


def _run(argv: list[str], stdin: bytes) -> tuple[int, bytes, list[str], list[str]]:
    """Run `argv` with `stdin` as its input; return (exit code, output, commands, error kinds).

    Every pipe fd is closed in the finally block, so a failing test leaks nothing.
    """
    in_r, in_w = os.pipe()
    out_r, out_w = os.pipe()
    commands: list[str] = []
    errors: list[str] = []
    try:
        os.write(in_w, stdin)
        os.close(in_w)
        in_w = -1
        code = run_session(argv, commands.append, errors.append, in_r, out_w)
        os.close(out_w)
        out_w = -1
        output = b""
        while chunk := os.read(out_r, 4096):
            output += chunk
        return code, output, commands, errors
    finally:
        for fd in (in_r, in_w, out_r, out_w):
            if fd >= 0:
                os.close(fd)


def test_returns_child_exit_code() -> None:
    code, _, _, _ = _run(["sh", "-c", "exit 3"], b"")
    assert code == 3


def test_relays_child_output_to_stdout() -> None:
    _, output, _, _ = _run(["sh", "-c", "echo hello"], b"")
    assert b"hello" in output


def test_relays_stdin_bytes_to_child() -> None:
    _, output, _, _ = _run(["sh", "-c", "read x; echo got:$x"], b"abc\n")
    assert b"got:abc" in output


def test_captures_typed_command_line() -> None:
    _, _, commands, _ = _run(["sh", "-c", "read x"], b"ls -l\n")
    assert commands == ["ls -l"]


def test_backspace_edits_line_buffer() -> None:
    _, _, commands, _ = _run(["sh", "-c", "read x"], b"lx\x7fs\n")
    assert commands == ["ls"]


def test_empty_lines_are_skipped() -> None:
    _, _, commands, _ = _run(["sh", "-c", "read a; read b"], b"\n\nls\n")
    assert commands == ["ls"]


@pytest.mark.parametrize(
    ("line", "kind"),
    [
        ("sh: foo: command not found", "not_found"),
        ("Traceback (most recent call last):", "traceback"),
        ("cat: x: Permission denied", "permission"),
        ("fatal error: boom", "error"),
    ],
)
def test_reports_error_kind_not_text(line: str, kind: str) -> None:
    script = f"printf '%s\\n' '{line}'"
    _, output, _, errors = _run(["sh", "-c", script], b"")
    assert errors == [kind]
    assert line.encode() in output  # the output itself still reaches stdout
    assert set(errors) <= ERROR_KINDS


def test_no_error_for_plain_output() -> None:
    _, _, _, errors = _run(["sh", "-c", "echo all good"], b"")
    assert errors == []


def test_child_is_reaped_after_session() -> None:
    _run(["sh", "-c", "exit 0"], b"")
    with pytest.raises(ChildProcessError):
        os.waitpid(-1, os.WNOHANG)


def test_session_closes_its_fds(
    fd_count: Callable[[], int],
) -> None:
    before = fd_count()
    _run(["sh", "-c", "echo x"], b"")
    assert fd_count() == before


@pytest.fixture
def fd_count() -> Callable[[], int]:
    def count() -> int:
        return len(os.listdir("/proc/self/fd"))

    return count
