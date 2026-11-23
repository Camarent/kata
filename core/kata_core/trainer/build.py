"""Job kind `course.build` logic: check the course drafts with the trainer, then build or fail the course.

The drafts are added to a probe workdir first; the items the trainer marks invalid are dropped, and
the kept drafts go into a fresh workdir that is locked and built. Fewer than `[trainer] min_items`
kept items fails the course with a diagnostics summary. Every call runs on the caller's connection.
"""

from __future__ import annotations

import json
import mimetypes
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

from kata_core.config import Config, load_config
from kata_core.jobs.queue import Job
from kata_core.journal.store import write_entry
from kata_core.trainer.cli import TrainerCli, TrainerError
from kata_core.trainer.dojo_cli import DojoTrainerCli
from kata_core.trainer.store import (
    add_artifacts,
    add_item_map,
    get_course,
    read_files,
    set_status,
)

KIND = "course.build"
COURSE_READY_KIND = "course.ready"
COURSE_FAILED_KIND = "course.failed"
DEFAULT_MEDIA_TYPE = "application/octet-stream"
MAX_ERROR_CHARS = 2000
# Every course item goes into this one dojo unit; dojo ids come back as `<unit>-<n>`.
DOJO_UNIT = "unit-1"
DOJO_ITEM_TYPE = "gap"
# A course is a dojo course named `<prefix>-<course id>`; dojo titles are capped at this many chars.
DOJO_COURSE_PREFIX = "kata"
DOJO_TITLE_CHARS = 80


class BuildRejected(Exception):
    """The build cannot give a course: artifacts over the cap, or too few items left."""


@dataclass(frozen=True)
class BuiltCourse:
    """A built course: artifacts (path -> (media type, bytes)), dojo item id -> concept id,
    the kept drafts and the dropped item id -> message of the probe."""

    artifacts: dict[str, tuple[str, bytes]]
    item_ids: dict[str, int]
    kept: list[dict[str, Any]]
    dropped: dict[str, str]


def course_id_of(job: Job) -> int:
    """Return the course id in a `course.build` payload `{"course_id": n}`."""
    payload = json.loads(job.payload)
    course_id = payload.get("course_id") if isinstance(payload, dict) else None
    if type(course_id) is not int:
        raise ValueError(f"job {job.id}: payload has no integer course_id")
    return course_id


def handle(conn: psycopg.Connection[Any], job: Job) -> None:
    """Handler for `course.build`: load config, run the trainer CLI, record the course outcome."""
    cfg = load_config()
    cli = DojoTrainerCli(
        argv_prefix=list(cfg.get("trainer", "command")),
        timeout=float(cfg.get("trainer", "timeout_seconds")),
        wasm=str(cfg.get("trainer", "wasm")),
        web=str(cfg.get("trainer", "web")),
    )
    run_build(conn, job, cfg, cli)


def run_build(
    conn: psycopg.Connection[Any],
    job: Job,
    cfg: Config,
    cli: TrainerCli,
) -> None:
    """Build the course of `job` with `cli`; mark it `ready`, or `failed` with the reason."""
    course_id = course_id_of(job)
    course = get_course(conn, job.user_id, course_id)
    if course is None:
        raise LookupError(f"course {course_id} of user {job.user_id} not found")
    drafts = _drafts(read_files(conn, job.user_id, course_id) or {})
    try:
        built = build_course_dir(
            cli,
            cfg,
            f"{DOJO_COURSE_PREFIX}-{course.id}",
            _dojo_title(course.title),
            drafts,
        )
    except BuildRejected as exc:
        fail_course(conn, job, course_id, str(exc))
        return
    except TrainerError as exc:
        fail_course(conn, job, course_id, f"trainer: {exc}")
        return
    add_artifacts(conn, job.user_id, course_id, built.artifacts)
    add_item_map(conn, job.user_id, course_id, built.item_ids)
    set_status(conn, job.user_id, course_id, "ready")
    write_entry(
        conn,
        job.user_id,
        COURSE_READY_KIND,
        {"course_id": course_id, "items": len(built.kept)},
        datetime.now(UTC),
    )


def build_course_dir(
    cli: TrainerCli,
    cfg: Config,
    course_id: str,
    title: str,
    drafts: list[dict[str, Any]],
) -> BuiltCourse:
    """Check `drafts` with a probe course, then init, add the kept ones, validate, lock and build.

    No database access. Raises BuildRejected when fewer than `min_items` kept or artifacts over the cap.
    """
    kept, dropped = _check_items(cli, course_id, title, drafts)
    min_items = int(cfg.get("trainer", "min_items"))
    if len(kept) < min_items:
        raise BuildRejected(_summary(len(drafts), len(kept), min_items, dropped))
    with tempfile.TemporaryDirectory() as tmp:
        workspace, outdir = Path(tmp) / "work", Path(tmp) / "out"
        workspace.mkdir()
        workdir = cli.init(workspace, course_id, title)
        item_ids: dict[str, int] = {}
        for draft in kept:
            item_ids[_add(cli, workdir, draft)] = draft["concept_id"]
        if cli.validate(workdir):
            raise TrainerError("trainer validate: kept items still invalid")
        cli.lock(workdir)
        artifacts = _artifacts(
            cli.build(workdir, outdir),
            outdir,
            course_id,
            int(cfg.get("trainer", "max_artifact_bytes")),
        )
    return BuiltCourse(artifacts, item_ids, kept, dropped)


def _drafts(files: dict[str, str]) -> list[dict[str, Any]]:
    """Parse the stored draft files (sorted by path) back into draft objects."""
    return [json.loads(files[path]) for path in sorted(files)]


def _dojo_title(title: str) -> str:
    """The course title as dojo takes it: no control characters, at most DOJO_TITLE_CHARS chars."""
    printable = "".join(ch for ch in title if unicodedata.category(ch) != "Cc")
    return printable[:DOJO_TITLE_CHARS]


def _check_items(
    cli: TrainerCli,
    course_id: str,
    title: str,
    drafts: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Add all drafts to a probe course and validate. Return (kept drafts, dropped item id -> message)."""
    with tempfile.TemporaryDirectory() as tmp:
        probe = cli.init(Path(tmp), course_id, title)
        ids = [_add(cli, probe, draft) for draft in drafts]
        bad = {d.item: d.message for d in cli.validate(probe)}
    kept = [draft for item_id, draft in zip(ids, drafts, strict=True) if item_id not in bad]
    dropped = {item_id: msg for item_id, msg in bad.items() if item_id in ids}
    return kept, dropped


def _dojo_item(draft: dict[str, Any]) -> dict[str, Any]:
    """Map a stored draft `{concept_id, prompt, answer}` to a dojo gap item. `concept_id` stays out of it."""
    return {
        "type": DOJO_ITEM_TYPE,
        "unit": DOJO_UNIT,
        "prompt": draft["prompt"],
        "answers": [draft["answer"]],
    }


def _add(cli: TrainerCli, workdir: Path, draft: dict[str, Any]) -> str:
    """Add one draft as a dojo item. The id must match the one `next-id` announced."""
    expected = cli.next_id(workdir, DOJO_UNIT)
    added = cli.add(workdir, json.dumps(_dojo_item(draft), sort_keys=True))
    if added != expected:
        raise TrainerError(f"trainer add gave id {added}, next-id said {expected}")
    return added


def _artifacts(
    files: list[str],
    outdir: Path,
    course_id: str,
    max_bytes: int,
) -> dict[str, tuple[str, bytes]]:
    """Read the built `files` under `outdir` into artifacts (path -> (media type, bytes)), capped in total.

    Names are relative to the course folder `<outdir>/<course_id>`, so `index.html` is served at the root.
    """
    root = (outdir / course_id).resolve()
    out: dict[str, tuple[str, bytes]] = {}
    total = 0
    for name in files:
        path = Path(name)
        if not path.is_absolute():
            path = outdir / path
        try:
            rel = path.resolve().relative_to(root)
        except ValueError as exc:
            raise TrainerError(f"trainer build: file outside course dir: {name}") from exc
        data = path.read_bytes()
        total += len(data)
        if total > max_bytes:
            raise BuildRejected(f"artifacts exceed {max_bytes} bytes")
        media_type = mimetypes.guess_type(rel.name)[0] or DEFAULT_MEDIA_TYPE
        out[rel.as_posix()] = (media_type, data)
    return out


def _summary(total: int, kept: int, min_items: int, dropped: dict[str, str]) -> str:
    """Diagnostics summary for a failed course, bounded to MAX_ERROR_CHARS."""
    detail = "; ".join(f"{item}: {msg}" for item, msg in dropped.items())
    text = f"{total - kept} of {total} items dropped, {kept} left, {min_items} needed"
    if detail:
        text = f"{text}. {detail}"
    return text[:MAX_ERROR_CHARS]


def fail_course(conn: psycopg.Connection[Any], job: Job, course_id: int, error: str) -> None:
    """Mark the course `failed` with `error` and journal `course.failed`."""
    set_status(conn, job.user_id, course_id, "failed", error)
    write_entry(
        conn,
        job.user_id,
        COURSE_FAILED_KIND,
        {"course_id": course_id, "error": error},
        datetime.now(UTC),
    )
