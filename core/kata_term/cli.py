"""`kata term`: run a shell in a pty and record its command lines and error kinds.

Opt-in: nothing is captured unless this runs. Each command line is masked (mask.py) before it
reaches the spool or the server. Events go to a JSONL spool first; the spool is flushed after each
command and at exit. A failed post keeps the events spooled and the session goes on silently.
Messages piggybacked on a post print one line for `nudge` and `stop`; `quiet_mark` prints nothing.
"""

from __future__ import annotations

import os
import sys
import urllib.request
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kata_term import client, mask, spool
from kata_term.session import run_session

USAGE_EXIT = 2
ACTIVE_ENV = "KATA_TERM_ACTIVE"
URL_ENV = "KATA_URL"
TOKEN_ENV = "KATA_TOKEN"
SHELL_ENV = "SHELL"
DEFAULT_SHELL = "/bin/sh"
XDG_STATE_ENV = "XDG_STATE_HOME"
DEFAULT_STATE_RELPATH = Path(".local", "state")
SPOOL_RELPATH = Path("kata", "term-spool.jsonl")
COMMAND_EVENT = "terminal.command"
ERROR_EVENT = "terminal.error"
NUDGE_KIND = "nudge"
STOP_KIND = "stop"

Runner = Callable[..., int]


def default_spool_path(env: Mapping[str, str]) -> Path:
    """Return the spool path: $XDG_STATE_HOME or ~/.local/state, then kata/term-spool.jsonl."""
    state_home = env.get(XDG_STATE_ENV)
    base = Path(state_home) if state_home else Path.home() / DEFAULT_STATE_RELPATH
    return base / SPOOL_RELPATH


def _record(spool_path: Path, event_type: str, payload: dict[str, Any]) -> None:
    """Append one event to the spool. The event id is a fresh uuid4 hex."""
    event = client.build_event(event_type, payload, datetime.now(UTC), uuid.uuid4().hex)
    spool.append(spool_path, event)


def _report(message: dict[str, Any]) -> None:
    """Print one stderr line for a nudge or stop message; other kinds print nothing."""
    kind = message.get("kind")
    if kind not in (NUDGE_KIND, STOP_KIND):
        return
    body = message.get("body")
    detail = body.get("detail") if isinstance(body, dict) else None
    text = ", ".join(f"{key} {value}" for key, value in (detail or {}).items())
    prefix = "kata: stop: " if kind == STOP_KIND else "kata: "
    print(prefix + text, file=sys.stderr)


def _flush(spool_path: Path, base_url: str, token: str, opener: client.Opener) -> None:
    """Post every spooled event in batches; drop the settled ones and print the messages.

    A ClientError stops posting: the unsettled events stay spooled and nothing is printed.
    """
    events = spool.read_all(spool_path)
    settled: set[str] = set()
    messages: list[dict[str, Any]] = []
    try:
        for start in range(0, len(events), client.MAX_BATCH):
            batch = events[start : start + client.MAX_BATCH]
            messages.extend(client.post_batch(base_url, token, batch, opener))
            settled.update(event["event_id"] for event in batch)
    except client.ClientError:
        pass  # the rest stays spooled; try again after the next command or at exit
    if settled:
        spool.rewrite_without(spool_path, settled)
    for message in messages:
        _report(message)


def main(
    argv: list[str],
    env: Mapping[str, str] = os.environ,
    opener: client.Opener = urllib.request.urlopen,
    runner: Runner = run_session,
    stdin_fd: int | None = None,
    stdout_fd: int | None = None,
) -> int:
    """Run `kata term`: `kata term [-- shell args...]`. Return the shell's exit code.

    The shell is the argv after `--`, else $SHELL, else /bin/sh. `runner` runs the pty session;
    the default fds are this process's stdin and stdout.
    """
    if env.get(ACTIVE_ENV):
        print("kata term: already inside a kata term session", file=sys.stderr)
        return USAGE_EXIT
    if argv and argv[0] != "--":
        print("usage: kata term [-- shell args...]", file=sys.stderr)
        return USAGE_EXIT
    base_url = env.get(URL_ENV)
    token = env.get(TOKEN_ENV)
    if not base_url or not token:
        print(f"kata term: {URL_ENV} and {TOKEN_ENV} must be set", file=sys.stderr)
        return USAGE_EXIT

    shell = argv[1:] or [env.get(SHELL_ENV) or DEFAULT_SHELL]
    masks = mask.load_masks(mask.default_mask_path(env))
    spool_path = default_spool_path(env)

    def on_command(line: str) -> None:
        _record(spool_path, COMMAND_EVENT, {"command": mask.mask_command(line, masks)})
        _flush(spool_path, base_url, token, opener)

    def on_error(kind: str) -> None:
        _record(spool_path, ERROR_EVENT, {"kind": kind})

    child_env = {**env, ACTIVE_ENV: "1"}
    in_fd = sys.stdin.fileno() if stdin_fd is None else stdin_fd
    out_fd = sys.stdout.fileno() if stdout_fd is None else stdout_fd
    try:
        return runner(shell, on_command, on_error, in_fd, out_fd, env=child_env)
    finally:
        _flush(spool_path, base_url, token, opener)
