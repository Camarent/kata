"""kata term CLI: opt-in wiring, masked command capture, spool flush, print nudges."""

import io
import json
import os
import urllib.request
from pathlib import Path
from typing import Any
from urllib.error import URLError

import pytest
from kata_term import cli, mask
from kata_term.cli import ACTIVE_ENV, TOKEN_ENV, URL_ENV, XDG_STATE_ENV, main

SECRET = "hunter2x"


class FakeOpener:
    """Stands in for urlopen: records each POST body and answers every event as accepted."""

    def __init__(self, messages: list[dict[str, Any]] | None = None, fail: bool = False) -> None:
        self.messages = messages or []
        self.fail = fail
        self.bodies: list[bytes] = []

    def __call__(self, request: urllib.request.Request, timeout: float) -> io.BytesIO:
        if self.fail:
            raise URLError("server down")
        assert request.data is not None
        self.bodies.append(request.data)
        events = json.loads(request.data)["events"]
        results = [{"event_id": event["event_id"], "status": "accepted"} for event in events]
        return io.BytesIO(json.dumps({"results": results, "messages": self.messages}).encode())


class FakeRunner:
    """Stands in for run_session: calls `script` with the callbacks and records the arguments."""

    def __init__(self, script: Any = None, code: int = 0) -> None:
        self.script = script
        self.code = code
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        argv: list[str],
        on_command: Any,
        on_error: Any,
        stdin_fd: int,
        stdout_fd: int,
        env: Any = None,
    ) -> int:
        self.calls.append({"argv": argv, "env": env})
        if self.script is not None:
            self.script(on_command, on_error, stdout_fd)
        return self.code


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """A complete environment: server set, state under tmp_path, mask list with one secret."""
    masks = tmp_path / "masks"
    masks.write_text(f"{SECRET}\n", encoding="utf-8")
    return {
        URL_ENV: "http://kata.test",
        TOKEN_ENV: "tok",
        XDG_STATE_ENV: str(tmp_path / "state"),
        mask.MASK_ENV: str(masks),
    }


def _spool(tmp_path: Path) -> Path:
    return tmp_path / "state" / "kata" / "term-spool.jsonl"


def _run(
    tmp_path: Path,
    env: dict[str, str],
    script: Any = None,
    opener: FakeOpener | None = None,
    argv: list[str] | None = None,
) -> tuple[int, FakeRunner, FakeOpener, bytes]:
    """Run main with fakes; return (exit code, runner, opener, bytes written to stdout)."""
    runner = FakeRunner(script)
    fake_opener = opener if opener is not None else FakeOpener()
    out_path = tmp_path / "stdout"
    out_fd = os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    try:
        code = main(
            argv if argv is not None else ["--", "sh"],
            env=env,
            opener=fake_opener,
            runner=runner,
            stdin_fd=0,
            stdout_fd=out_fd,
        )
    finally:
        os.close(out_fd)
    return code, runner, fake_opener, out_path.read_bytes()


def test_missing_server_env_returns_2_with_one_line(
    tmp_path: Path, env: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    del env[URL_ENV]
    code, runner, _, _ = _run(tmp_path, env)
    assert code == cli.USAGE_EXIT
    assert runner.calls == []
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert URL_ENV in err


def test_nested_run_returns_2_with_one_line(
    tmp_path: Path, env: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    env[ACTIVE_ENV] = "1"
    code, runner, _, _ = _run(tmp_path, env)
    assert code == cli.USAGE_EXIT
    assert runner.calls == []
    assert capsys.readouterr().err.count("\n") == 1


def test_child_gets_active_marker_and_shell_from_argv(tmp_path: Path, env: dict[str, str]) -> None:
    code, runner, _, _ = _run(tmp_path, env, argv=["--", "sh", "-c", "exit 0"])
    assert code == 0
    assert runner.calls[0]["argv"] == ["sh", "-c", "exit 0"]
    assert runner.calls[0]["env"][ACTIVE_ENV] == "1"
    assert ACTIVE_ENV not in env  # the caller's environment is not changed


def test_shell_defaults_to_env_shell_then_bin_sh(tmp_path: Path, env: dict[str, str]) -> None:
    _, runner, _, _ = _run(tmp_path, {**env, "SHELL": "/bin/zsh"}, argv=[])
    assert runner.calls[0]["argv"] == ["/bin/zsh"]
    _, runner, _, _ = _run(tmp_path, env, argv=[])
    assert runner.calls[0]["argv"] == ["/bin/sh"]


def test_unknown_argument_before_dash_dash_is_usage_error(
    tmp_path: Path, env: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    code, runner, _, _ = _run(tmp_path, env, argv=["sh"])
    assert code == cli.USAGE_EXIT
    assert runner.calls == []
    assert capsys.readouterr().err.startswith("usage:")


def test_masked_command_never_reaches_spool_post_stdout_or_stderr(
    tmp_path: Path, env: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    def script(on_command: Any, on_error: Any, stdout_fd: int) -> None:
        on_command(f"mysql -u root {SECRET}")
        on_error("not_found")
        os.write(stdout_fd, b"ok\n")

    code, _, opener, stdout = _run(tmp_path, env, script=script)
    assert code == 0
    captured = capsys.readouterr()
    spooled = _spool(tmp_path).read_text(encoding="utf-8")
    posted = b"".join(opener.bodies).decode("utf-8")
    assert SECRET not in spooled
    assert SECRET not in posted
    assert SECRET not in stdout.decode("utf-8")
    assert SECRET not in captured.out + captured.err
    assert "[masked]" in posted
    assert '"kind": "not_found"' in posted


def test_command_event_is_flushed_and_spool_emptied(tmp_path: Path, env: dict[str, str]) -> None:
    def script(on_command: Any, on_error: Any, stdout_fd: int) -> None:
        on_command("ls -la")

    _, _, opener, _ = _run(tmp_path, env, script=script)
    body = json.loads(opener.bodies[0])
    assert [event["type"] for event in body["events"]] == ["terminal.command"]
    assert body["events"][0]["payload"] == {"command": "ls -la"}
    assert not _spool(tmp_path).read_text(encoding="utf-8").strip()


def test_failed_post_keeps_events_spooled_and_is_silent(
    tmp_path: Path, env: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    def script(on_command: Any, on_error: Any, stdout_fd: int) -> None:
        on_command("ls")
        on_error("error")

    code, _, _, _ = _run(tmp_path, env, script=script, opener=FakeOpener(fail=True))
    assert code == 0
    kinds = [json.loads(line)["type"] for line in _spool(tmp_path).read_text().splitlines()]
    assert kinds == ["terminal.command", "terminal.error"]
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == ""


@pytest.mark.parametrize(
    ("kind", "detail", "expected"),
    [
        ("nudge", {"errors": 3.0, "window_seconds": 60.0}, "kata: errors 3.0, window_seconds 60.0\n"),
        ("stop", {"errors": 8.0}, "kata: stop: errors 8.0\n"),
        ("quiet_mark", {"idle_seconds": 90.0}, ""),
    ],
)
def test_piggyback_messages_print_per_kind(
    tmp_path: Path,
    env: dict[str, str],
    capsys: pytest.CaptureFixture[str],
    kind: str,
    detail: dict[str, float],
    expected: str,
) -> None:
    message = {"id": 1, "kind": kind, "body": {"at": "2026-11-21T10:00:00+00:00", "detail": detail}}
    _run(tmp_path, env, script=lambda on_command, on_error, fd: on_command("ls"),
         opener=FakeOpener(messages=[message]))
    captured = capsys.readouterr()
    assert captured.err == expected
    assert captured.out == ""


def test_real_session_returns_child_exit_code(tmp_path: Path, env: dict[str, str]) -> None:
    """Run the real pty session with no input: the child's exit code comes back."""
    in_r, in_w = os.pipe()
    os.close(in_w)
    out_fd = os.open(tmp_path / "stdout", os.O_WRONLY | os.O_CREAT)
    try:
        code = main(
            ["--", "sh", "-c", "exit 3"],
            env=env,
            opener=FakeOpener(),
            stdin_fd=in_r,
            stdout_fd=out_fd,
        )
    finally:
        os.close(in_r)
        os.close(out_fd)
    assert code == 3
