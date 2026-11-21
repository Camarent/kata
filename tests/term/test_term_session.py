"""PTY session: run a child in a pty, capture command lines and error kinds, shut down cleanly."""

import os
import shlex
import threading
from collections.abc import Callable
from pathlib import Path

import pytest
from kata_term.session import ERROR_KINDS, _send, run_session


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


def _run_typing_after(
    argv: list[str],
    marker: bytes,
    typed: bytes,
    on_command: Callable[[str], None],
) -> tuple[int, bytes]:
    """Run `argv`; once the child prints `marker`, type `typed` into it. Return (code, output).

    The typing happens on a helper thread that reads the output, so the child has
    already reached the marker (and changed its tty mode) before any byte is sent.
    An exception from `on_command` propagates after the session has cleaned up.
    """
    in_r, in_w = os.pipe()
    out_r, out_w = os.pipe()
    output = bytearray()

    def type_when_marked() -> None:
        typed_already = False
        try:
            while chunk := os.read(out_r, 4096):
                output.extend(chunk)
                if not typed_already and marker in output:
                    os.write(in_w, typed)
                    typed_already = True
        finally:
            os.close(out_r)
            os.close(in_w)

    typist = threading.Thread(target=type_when_marked)
    typist.start()
    try:
        code = run_session(argv, on_command, lambda _kind: None, in_r, out_w)
    finally:
        os.close(out_w)  # EOF for the typist, so it can finish
        os.close(in_r)
        typist.join()
    return code, bytes(output)


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


def test_line_typed_with_echo_off_is_not_captured() -> None:
    # A password prompt: the child turns echo off, then reads the secret line.
    commands: list[str] = []
    code, output = _run_typing_after(
        ["sh", "-c", "stty -echo; echo ready; read x; echo got:$x"],
        b"ready",
        b"hunter2\n",
        commands.append,
    )
    assert code == 0
    assert b"got:hunter2" in output  # the child still receives the secret
    assert commands == []  # but the session never reports it


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


def test_stdin_eof_forwards_eof_byte_and_child_exits_cleanly() -> None:
    code, output, _, _ = _run(["sh", "-c", "read x; echo eof:[$x]"], b"")
    assert code == 0
    assert b"eof:[]" in output  # Ctrl-D reached the child as an empty read


def test_child_exiting_mid_write_returns_without_error() -> None:
    # Input stays under the pipe buffer, so the test itself never blocks on the write.
    code, _, _, _ = _run(["sh", "-c", "exit 0"], b"y\n" * 2000)
    assert code == 0  # whichever side sees the exit first, the session ends cleanly


def test_send_reports_false_once_read_side_is_gone() -> None:
    r, w = os.pipe()
    try:
        assert _send(w, b"x") is True
        os.close(r)
        assert _send(w, b"x") is False
    finally:
        os.close(w)


def test_failed_spawn_raises_and_leaks_no_fds(
    fd_count: Callable[[], int],
) -> None:
    before = fd_count()
    with pytest.raises(FileNotFoundError):
        _run(["/nonexistent/no-such-binary"], b"")
    assert fd_count() == before


def test_child_is_killed_when_relay_raises(tmp_path: Path) -> None:
    # The child records its pid, then waits; a callback error ends the relay while it still runs.
    pid_file = tmp_path / "pid"
    script = f"echo $$ > {shlex.quote(str(pid_file))}; echo ready; read x; exec sleep 60"

    def refuse(line: str) -> None:
        raise RuntimeError(line)

    with pytest.raises(RuntimeError):
        _run_typing_after(["sh", "-c", script], b"ready", b"ls\n", refuse)
    pid = int(pid_file.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)  # killed and reaped: the pid no longer exists


@pytest.fixture
def fd_count() -> Callable[[], int]:
    def count() -> int:
        return len(os.listdir("/proc/self/fd"))

    return count
