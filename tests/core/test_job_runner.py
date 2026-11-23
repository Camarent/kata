"""Core job runner against a real Postgres: registry, claim, done/failed marks, output hooks."""

from __future__ import annotations

import importlib
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import kata_core
import psycopg
import pytest
from kata_core.jobs.queue import enqueue, get_job
from kata_core.jobs.runner import Registry, load_registry, run_once, run_output_hook, serve
from support.scratch_db import ScratchDatabase

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
LEASE_SECONDS = 60
KIND = "course.build"


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    user_id: int = row[0]
    return user_id


def _ok_handler(calls: list[int]) -> Any:
    def handler(conn: psycopg.Connection[Any], job: Any) -> None:
        calls.append(job.id)

    return handler


def _failing_handler(conn: psycopg.Connection[Any], job: Any) -> None:
    conn.execute("INSERT INTO users (name) VALUES ('partial-write')")
    raise RuntimeError("boom")


def test_run_once_done_on_success(db: ScratchDatabase) -> None:
    calls: list[int] = []
    registry = Registry(handlers={KIND: _ok_handler(calls)})
    with db.connect() as conn:
        user = _user(conn, "alice")
        job_id = enqueue(conn, user, "build", kind=KIND)

        ran = run_once(conn, registry, T0, LEASE_SECONDS)

        assert ran is not None
        assert ran.id == job_id
        assert calls == [job_id]
        job = get_job(conn, job_id, user)
        assert job is not None
        assert job.status == "done"


def test_run_once_marks_failed_and_rolls_back_partial_writes(db: ScratchDatabase) -> None:
    registry = Registry(handlers={KIND: _failing_handler})
    with db.connect() as conn:
        user = _user(conn, "alice")
        job_id = enqueue(conn, user, "build", kind=KIND)

        ran = run_once(conn, registry, T0, LEASE_SECONDS)

        assert ran is not None
        job = get_job(conn, job_id, user)
        assert job is not None
        assert job.status == "failed"
        partial = conn.execute("SELECT count(*) FROM users WHERE name = 'partial-write'").fetchone()
        assert partial == (0,)


def test_run_once_ignores_kinds_without_handler(db: ScratchDatabase) -> None:
    calls: list[int] = []
    registry = Registry(handlers={KIND: _ok_handler(calls)})
    with db.connect() as conn:
        user = _user(conn, "alice")
        tag_id = enqueue(conn, user, "tag this")

        assert run_once(conn, registry, T0, LEASE_SECONDS) is None

        assert calls == []
        job = get_job(conn, tag_id, user)
        assert job is not None
        assert job.status == "queued"


def test_run_once_with_empty_registry_claims_nothing(db: ScratchDatabase) -> None:
    with db.connect() as conn:
        user = _user(conn, "alice")
        enqueue(conn, user, "build", kind=KIND)

        assert run_once(conn, Registry(), T0, LEASE_SECONDS) is None


def test_run_once_reclaims_expired_lease_with_fake_clock(db: ScratchDatabase) -> None:
    calls: list[int] = []
    registry = Registry(handlers={KIND: _ok_handler(calls)})
    with db.connect() as conn:
        user = _user(conn, "alice")
        job_id = enqueue(conn, user, "build", kind=KIND)
        conn.execute(
            "UPDATE jobs SET status = 'leased', lease_expires_at = %s, attempts = 1 WHERE id = %s",
            (T0 + timedelta(seconds=LEASE_SECONDS), job_id),
        )

        # Lease still live at T0: nothing claimed.
        assert run_once(conn, registry, T0, LEASE_SECONDS) is None
        # Lease expired one second later: the job runs.
        ran = run_once(conn, registry, T0 + timedelta(seconds=LEASE_SECONDS + 1), LEASE_SECONDS)

        assert ran is not None
        assert calls == [job_id]


def test_run_output_hook_dispatches_to_registered_hook(db: ScratchDatabase) -> None:
    seen: list[dict[str, Any]] = []

    def hook(conn: psycopg.Connection[Any], job: Any, output: dict[str, Any]) -> None:
        seen.append(output)

    registry = Registry(output_hooks={KIND: hook})
    with db.connect() as conn:
        user = _user(conn, "alice")
        job_id = enqueue(conn, user, "build", kind=KIND)
        job = get_job(conn, job_id, user)
        assert job is not None

        run_output_hook(conn, registry, job, {"ok": True})

        assert seen == [{"ok": True}]


def test_run_output_hook_without_hook_raises(db: ScratchDatabase) -> None:
    with db.connect() as conn:
        user = _user(conn, "alice")
        job_id = enqueue(conn, user, "build", kind=KIND)
        job = get_job(conn, job_id, user)
        assert job is not None

        with pytest.raises(ValueError, match="no output hook"):
            run_output_hook(conn, Registry(), job, {})


def test_load_registry_returns_dict_registry() -> None:
    registry = load_registry()

    assert isinstance(registry.handlers, dict)
    assert isinstance(registry.output_hooks, dict)


def _fake_package(
    root: Path, monkeypatch: pytest.MonkeyPatch, name: str, kind: str, with_hook: bool
) -> None:
    """Write `<root>/<name>/job_kinds.py` registering `kind`, importable as kata_core.<name>."""
    pkg = root / name
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    hooks = "OUTPUT_HOOKS = {KIND: lambda conn, job, output: None}\n" if with_hook else ""
    (pkg / "job_kinds.py").write_text(
        f"KIND = {kind!r}\nHANDLERS = {{KIND: lambda conn, job: None}}\n{hooks}"
    )
    # Drop the fake modules from the import cache when the test ends.
    for mod in (f"kata_core.{name}", f"kata_core.{name}.job_kinds"):
        monkeypatch.setitem(sys.modules, mod, None)
        monkeypatch.delitem(sys.modules, mod)


def _extend_package_path(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setattr(kata_core, "__path__", [*kata_core.__path__, str(root)])
    importlib.invalidate_caches()


def test_load_registry_discovers_job_kinds_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_package(tmp_path, monkeypatch, "fakefeature", "fake.discovered", with_hook=True)
    _extend_package_path(monkeypatch, tmp_path)

    registry = load_registry()

    assert "fake.discovered" in registry.handlers
    assert "fake.discovered" in registry.output_hooks


def test_load_registry_rejects_duplicate_kind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_package(tmp_path, monkeypatch, "fakeone", "fake.dup", with_hook=False)
    _fake_package(tmp_path, monkeypatch, "faketwo", "fake.dup", with_hook=False)
    _extend_package_path(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="registered twice"):
        load_registry()


def test_serve_polls_each_round_and_sleeps_the_configured_interval(
    db: ScratchDatabase,
) -> None:
    calls: list[int] = []
    sleeps: list[float] = []
    registry = Registry(handlers={KIND: _ok_handler(calls)})
    with db.connect() as conn:
        user = _user(conn, "alice")
        first = enqueue(conn, user, "build 1", kind=KIND)
        second = enqueue(conn, user, "build 2", kind=KIND)
        conn.commit()

    serve(
        db.cfg,
        registry,
        clock=lambda: T0,
        sleep=sleeps.append,
        rounds=[None, None],
        database=db.name,
    )

    assert calls == [first, second]
    assert sleeps == [db.cfg.get("jobs", "runner_poll_seconds")] * 2


def test_serve_survives_a_failing_round(db: ScratchDatabase) -> None:
    sleeps: list[float] = []

    serve(
        db.cfg,
        Registry(handlers={KIND: _ok_handler([])}),
        clock=lambda: T0,
        sleep=sleeps.append,
        rounds=[None, None],
        database=f"{db.name}_missing",
    )

    assert len(sleeps) == 2
