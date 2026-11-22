"""Core job runner: claims core-run jobs of any user and runs their registered handler.

Handlers and output hooks are discovered, not listed here. Every `kata_core.<pkg>.job_kinds`
module exposes `HANDLERS: dict[str, Handler]` and `OUTPUT_HOOKS: dict[str, OutputHook]`.
This module never imports a feature package by name.

Every function runs on the caller's connection and leaves the transaction open: the caller
commits. `run_once` marks a failed handler's job failed and returns, so the caller's commit
keeps the failure.
"""

from __future__ import annotations

import importlib
import itertools
import logging
import pkgutil
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg

import kata_core
from kata_core.config import Config
from kata_core.jobs.queue import JOB_COLUMNS, Job, complete, fail
from kata_core.storage.provision import connect

log = logging.getLogger(__name__)

JOB_KINDS_SUBMODULE = "job_kinds"

Handler = Callable[[psycopg.Connection[Any], Job], None]
OutputHook = Callable[[psycopg.Connection[Any], Job, dict[str, Any]], None]


@dataclass(frozen=True)
class Registry:
    handlers: dict[str, Handler] = field(default_factory=dict)
    output_hooks: dict[str, OutputHook] = field(default_factory=dict)


def load_registry() -> Registry:
    """Import every `kata_core.<pkg>.job_kinds` module and merge its HANDLERS and OUTPUT_HOOKS.

    Raises ValueError when two modules register the same kind.
    """
    handlers: dict[str, Handler] = {}
    hooks: dict[str, OutputHook] = {}
    for info in pkgutil.iter_modules(kata_core.__path__):
        if not info.ispkg:
            continue
        modname = f"{kata_core.__name__}.{info.name}.{JOB_KINDS_SUBMODULE}"
        try:
            module = importlib.import_module(modname)
        except ModuleNotFoundError as exc:
            if exc.name == modname:
                continue  # this package has no job_kinds module
            raise
        _merge(handlers, getattr(module, "HANDLERS", {}), modname)
        _merge(hooks, getattr(module, "OUTPUT_HOOKS", {}), modname)
    return Registry(handlers=handlers, output_hooks=hooks)


def _merge(target: dict[str, Any], source: dict[str, Any], modname: str) -> None:
    for kind, item in source.items():
        if kind in target:
            raise ValueError(f"job kind {kind!r} registered twice (second in {modname})")
        target[kind] = item


def _claim(
    conn: psycopg.Connection[Any],
    kinds: tuple[str, ...],
    now: datetime,
    lease_seconds: int,
) -> Job | None:
    """Lease the oldest job of any user with a kind in `kinds`: queued, or lease expired."""
    picked = conn.execute(
        "SELECT id FROM jobs "
        "WHERE kind = ANY(%s) AND (status = 'queued' "
        "OR (status = 'leased' AND lease_expires_at <= %s)) "
        "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED",
        (list(kinds), now),
    ).fetchone()
    if picked is None:
        return None
    row = conn.execute(
        f"UPDATE jobs SET status = 'leased', lease_expires_at = %s, attempts = attempts + 1 "  # nosec B608 - JOB_COLUMNS is a module constant, no user input reaches the SQL text
        f"WHERE id = %s RETURNING {JOB_COLUMNS}",
        (now + timedelta(seconds=lease_seconds), picked[0]),
    ).fetchone()
    if row is None:
        raise RuntimeError("_claim: UPDATE ... RETURNING returned no row for the picked job")
    return Job(*row)


def run_once(
    conn: psycopg.Connection[Any],
    registry: Registry,
    now: datetime,
    lease_seconds: int,
) -> Job | None:
    """Claim one job whose kind has a handler, run it, and mark it done or failed.

    Returns the claimed job, or None when no core-run job is claimable. A handler error is
    logged, its partial writes are rolled back to a savepoint, and the job is marked failed.
    """
    if not registry.handlers:
        return None
    job = _claim(conn, tuple(registry.handlers), now, lease_seconds)
    if job is None:
        return None
    handler = registry.handlers[job.kind]
    try:
        with conn.transaction():
            handler(conn, job)
    except Exception:
        log.exception("job %s (%s) failed", job.id, job.kind)
        fail(conn, job.id, job.user_id)
        return job
    complete(conn, job.id, job.user_id, None)
    return job


def run_output_hook(
    conn: psycopg.Connection[Any],
    registry: Registry,
    job: Job,
    output: dict[str, Any],
) -> None:
    """Run the output hook registered for `job.kind` on the caller's transaction."""
    hook = registry.output_hooks.get(job.kind)
    if hook is None:
        raise ValueError(f"no output hook for job kind {job.kind!r}")
    hook(conn, job, output)


def serve(
    cfg: Config,
    registry: Registry,
    *,
    clock: Callable[[], datetime],
    sleep: Callable[[float], None],
    rounds: Iterable[None],
    database: str | None = None,
) -> None:
    """Poll core-run jobs once per round, one transaction per round, sleeping between rounds.

    `rounds` yields once per poll; the loop ends when it is exhausted (the process runs
    until stopped when it never ends). `database` overrides `[database] name` (tests).
    A round that raises (for example a database restart) is logged and the loop goes on.
    """
    lease_seconds = cfg.get("jobs", "lease_seconds")
    poll_seconds = cfg.get("jobs", "runner_poll_seconds")
    for _ in rounds:
        try:
            with connect(cfg, database) as conn:
                run_once(conn, registry, clock(), lease_seconds)
        except Exception:
            log.exception("job runner round failed; retrying after the poll interval")
        sleep(poll_seconds)


def run_forever(cfg: Config, registry: Registry) -> None:
    """Production loop: wall clock, real sleep, never ends."""
    serve(
        cfg,
        registry,
        clock=lambda: datetime.now(tz=UTC),
        sleep=time.sleep,
        rounds=itertools.repeat(None),
    )
