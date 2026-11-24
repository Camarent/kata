"""Run modelctl for one modelhost control job: a fixed argv, no shell, a timeout, a capped output.

The kind and the engine come from `kata_core.modelhost.spec`; the argv is built here from a fixed
table, so a payload never adds a word to the command line. Refusals raise ValueError before any
process starts.
"""

from __future__ import annotations

import os
import signal
import subprocess  # nosec B404 - fixed argv list, no shell
import threading
import time
from collections.abc import Callable
from typing import IO

from kata_core.config import Config, load_config
from kata_core.modelhost.spec import MEASURE_KIND, STATUS_KIND, UP_KIND, USE_KIND, validate_payload

ARGV_FOR_KIND: dict[str, tuple[str, ...]] = {
    UP_KIND: ("up",),
    MEASURE_KIND: ("measure",),
    STATUS_KIND: ("status",),
}
USE_SUBCOMMAND = "use"
TIMEOUT_MESSAGE = "modelctl timed out after {seconds}s"
NOT_INSTALLED_MESSAGE = "modelctl is not installed here: set [modelhost] modelctl_path and modelhost_dir"
NO_DIR_MESSAGE = "modelhost_dir does not exist: {path}"
READ_CHUNK_BYTES = 65536
KILL_GRACE_SECONDS = 1.0

Runner = Callable[[list[str], str, int, int], subprocess.CompletedProcess[bytes]]


def _keep_head(stream: IO[bytes], limit: int) -> bytes:
    """Read `stream` to EOF in chunks; keep its first `limit` bytes and discard the rest."""
    kept = bytearray()
    while chunk := stream.read(READ_CHUNK_BYTES):
        kept += chunk[: limit - len(kept)]
    return bytes(kept)


def _read_head_into(stream: IO[bytes], limit: int, sink: list[bytes]) -> None:
    """Reader thread body: put the head of `stream` into `sink`, then close the pipe at EOF."""
    try:
        sink.append(_keep_head(stream, limit))
    finally:
        stream.close()


def _kill_group(proc: subprocess.Popen[bytes]) -> None:
    """SIGKILL the child's process group: the child and any grandchild that kept its stdout open."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass  # the group already ended


def _run_process(argv: list[str], cwd: str, timeout: int, max_bytes: int) -> subprocess.CompletedProcess[bytes]:
    """Spawn argv (a list, never a shell string); keep at most `max_bytes` of stdout.

    The child gets its own process group. Stdout is read in a thread, so a chatty child never
    fills memory. The whole run, the child and its stdout readers, must end within `timeout`;
    past it the group is killed and TimeoutExpired is raised.
    """
    proc = subprocess.Popen(  # nosec B603 - argv list, shell=False
        argv,
        cwd=cwd,
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    stdout = proc.stdout
    if stdout is None:  # cannot happen: stdout=PIPE above
        _kill_group(proc)
        proc.wait()
        raise OSError("modelctl stdout pipe is missing")
    kept: list[bytes] = []
    reader = threading.Thread(target=_read_head_into, args=(stdout, max_bytes, kept), daemon=True)
    deadline = time.monotonic() + timeout
    reader.start()
    try:
        returncode = proc.wait(timeout=timeout)
        reader.join(max(0.0, deadline - time.monotonic()))
        if reader.is_alive():  # a grandchild still holds stdout open past the deadline
            raise subprocess.TimeoutExpired(argv, timeout)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        proc.wait()
        reader.join(KILL_GRACE_SECONDS)
        raise
    return subprocess.CompletedProcess(argv, returncode, stdout=b"".join(kept), stderr=None)


class ControlRunner:
    """Runs one modelctl subcommand per control job and returns (ok, text)."""

    def __init__(self, cfg: Config, *, runner: Runner = _run_process) -> None:
        self._modelctl = str(cfg.get("modelhost", "modelctl_path"))
        self._cwd = str(cfg.get("modelhost", "modelhost_dir"))
        self._timeout = int(cfg.get("modelhost", "control_timeout_seconds"))
        self._max_bytes = int(cfg.get("modelhost", "max_text_bytes"))
        self._runner = runner

    def argv(self, kind: str, payload: str) -> list[str]:
        """The full argv for `kind`; raise ValueError for an unknown kind or a bad payload."""
        data = validate_payload(kind, payload)
        if kind == USE_KIND:
            words: tuple[str, ...] = (USE_SUBCOMMAND, str(data["engine"]))
        else:
            words = ARGV_FOR_KIND[kind]
        return [self._modelctl, *words]

    def run(self, kind: str, payload: str) -> tuple[bool, str]:
        """Run modelctl for `kind`; return (ok, text). ValueError before any spawn on a bad request."""
        argv = self.argv(kind, payload)
        if not self._modelctl or not self._cwd:
            return False, NOT_INSTALLED_MESSAGE
        if not os.path.isdir(self._cwd):
            return False, NO_DIR_MESSAGE.format(path=self._cwd)
        try:
            done = self._runner(argv, self._cwd, self._timeout, self._max_bytes)
        except subprocess.TimeoutExpired:
            return False, TIMEOUT_MESSAGE.format(seconds=self._timeout)
        except OSError as exc:
            return False, f"modelctl could not start: {exc.strerror or exc}"
        text = done.stdout.decode("utf-8", errors="replace")
        return done.returncode == 0, text


def default_runner() -> ControlRunner:
    """A ControlRunner built from the config file named by the environment (KATA_CONFIG)."""
    return ControlRunner(load_config())
