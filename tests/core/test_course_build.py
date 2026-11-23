"""Course generate output hook and course build handler against a real Postgres and the fake trainer."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fakes import fake_dojo
from kata_core.config import Config
from kata_core.jobs.queue import Job, enqueue, get_job
from kata_core.jobs.runner import load_registry
from kata_core.storage.concepts import create_concept
from kata_core.storage.taxonomy import ensure_category
from kata_core.trainer import build
from kata_core.trainer.dojo_cli import DojoTrainerCli
from kata_core.trainer.job_kinds import generate_output_hook
from kata_core.trainer.store import Course, create_course, get_course, read_files
from support.scratch_db import ScratchDatabase

FAKE_TRAINER = [sys.executable, str(Path(fake_dojo.__file__))]
MISSING_TRAINER = ["/nonexistent/dojo"]
FAKE_MARK = fake_dojo.INVALID_MARK


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


def _cfg(argv: list[str] = FAKE_TRAINER, min_items: int = 2, max_bytes: int = 1048576) -> Config:
    return Config(
        sections={
            "trainer": {
                "command": argv,
                "timeout_seconds": 30,
                "min_items": min_items,
                "max_artifact_bytes": max_bytes,
            }
        }
    )


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def _concepts(conn: psycopg.Connection[Any]) -> tuple[int, int]:
    category_id = ensure_category(conn, "music")
    row = conn.execute(
        "INSERT INTO topics (category_id, label) VALUES (%s, 'topic') RETURNING id",
        (category_id,),
    ).fetchone()
    assert row is not None
    topic_id = int(row[0])
    return create_concept(conn, topic_id, "scales"), create_concept(conn, topic_id, "chords")


def _course(conn: psycopg.Connection[Any], user: int, concepts: tuple[int, int]) -> Course:
    return create_course(conn, user, "course", list(concepts))


def _generate_job(
    conn: psycopg.Connection[Any], user: int, course: Course, concepts: tuple[int, int]
) -> Job:
    payload = {
        "course_id": course.id,
        "concepts": [{"id": c, "label": f"c{c}"} for c in concepts],
    }
    job_id = enqueue(conn, user, json.dumps(payload), kind="course.generate")
    job = get_job(conn, job_id, user)
    assert job is not None
    return job


def _draft(concept: int, prompt: str = "name a scale", answer: str = "major") -> dict[str, Any]:
    return {"concept_id": concept, "prompt": prompt, "answer": answer}


def _generate(
    conn: psycopg.Connection[Any],
    user: int,
    concepts: tuple[int, int],
    items: list[dict[str, Any]],
) -> Course:
    course = _course(conn, user, concepts)
    job = _generate_job(conn, user, course, concepts)
    generate_output_hook(conn, job, {"items": items})
    refreshed = get_course(conn, user, course.id)
    assert refreshed is not None
    return refreshed


def _build_job(conn: psycopg.Connection[Any], user: int) -> Job:
    row = conn.execute(
        "SELECT id FROM jobs WHERE user_id = %s AND kind = 'course.build'", (user,)
    ).fetchone()
    assert row is not None
    job = get_job(conn, int(row[0]), user)
    assert job is not None
    return job


def _count(conn: psycopg.Connection[Any], table: str, course_id: int) -> int:
    row = conn.execute(
        f"SELECT count(*) FROM {table} WHERE course_id = %s", (course_id,)
    ).fetchone()
    assert row is not None
    return int(row[0])


def _journal(conn: psycopg.Connection[Any], user: int, kind: str) -> int:
    row = conn.execute(
        "SELECT count(*) FROM journal_entry WHERE user_id = %s AND kind = %s", (user, kind)
    ).fetchone()
    assert row is not None
    return int(row[0])


def test_hook_stores_drafts_and_queues_build(
    conn: psycopg.Connection[Any], db: ScratchDatabase
) -> None:
    user = _user(conn, "alice")
    concepts = _concepts(conn)
    extra = {**_draft(concepts[0]), "score": 9}
    course = _generate(conn, user, concepts, [extra, _draft(concepts[1])])

    assert course.status == "building"
    stored = read_files(conn, user, course.id)
    assert stored is not None
    assert len(stored) == 2
    assert all("score" not in json.loads(text) for text in stored.values())
    build_job = _build_job(conn, user)
    assert build_job.kind == build.KIND
    assert json.loads(build_job.payload) == {"course_id": course.id}


BAD_DRAFTS = [
    pytest.param(
        lambda c: {"concept_id": 999999, "prompt": "p", "answer": "a"}, id="foreign-concept"
    ),
    pytest.param(lambda c: {"concept_id": True, "prompt": "p", "answer": "a"}, id="bool-concept"),
    pytest.param(lambda c: {"concept_id": c, "prompt": "", "answer": "a"}, id="empty-prompt"),
    pytest.param(
        lambda c: {"concept_id": c, "prompt": "p" * 2001, "answer": "a"}, id="long-prompt"
    ),
    pytest.param(
        lambda c: {"concept_id": c, "prompt": "p", "answer": "bad\x07bell"}, id="control-char"
    ),
    pytest.param(lambda c: {"concept_id": c, "prompt": "p"}, id="no-answer"),
]


@pytest.mark.parametrize("make", BAD_DRAFTS)
def test_hook_bad_draft_fails_course(conn: psycopg.Connection[Any], make: Any) -> None:
    user = _user(conn, "alice")
    concepts = _concepts(conn)
    course = _generate(conn, user, concepts, [_draft(concepts[1]), make(concepts[0])])

    assert course.status == "failed"
    assert course.error is not None
    assert read_files(conn, user, course.id) == {}
    assert _count(conn, "course_file", course.id) == 0
    assert _journal(conn, user, build.COURSE_FAILED_KIND) == 1
    rows = conn.execute("SELECT count(*) FROM jobs WHERE kind = 'course.build'").fetchone()
    assert rows is not None and rows[0] == 0


def test_build_ready_drops_invalid_item(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "alice")
    concepts = _concepts(conn)
    _generate(
        conn,
        user,
        concepts,
        [_draft(concepts[0]), _draft(concepts[1]), _draft(concepts[0], prompt=f"{FAKE_MARK} x")],
    )
    job = _build_job(conn, user)
    build.run_build(conn, job, _cfg(), DojoTrainerCli(FAKE_TRAINER, 30))

    course = get_course(conn, user, json.loads(job.payload)["course_id"])
    assert course is not None
    assert course.status == "ready"
    assert course.error is None
    assert _count(conn, "course_item_map", course.id) == 2
    # The fake dojo writes data/content.json, manifest.json and index.html.
    assert _count(conn, "course_artifact", course.id) == 3
    assert _journal(conn, user, build.COURSE_READY_KIND) == 1


def test_build_fails_below_min_items_with_summary(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "alice")
    concepts = _concepts(conn)
    _generate(
        conn,
        user,
        concepts,
        [
            _draft(concepts[0], prompt=f"{FAKE_MARK} one"),
            _draft(concepts[1], prompt=f"{FAKE_MARK} two"),
            _draft(concepts[1]),
        ],
    )
    job = _build_job(conn, user)
    build.run_build(conn, job, _cfg(min_items=2), DojoTrainerCli(FAKE_TRAINER, 30))

    course = get_course(conn, user, json.loads(job.payload)["course_id"])
    assert course is not None
    assert course.status == "failed"
    assert course.error is not None
    assert course.error.startswith("2 of 3 items dropped, 1 left, 2 needed")
    assert "fake marked invalid" in course.error
    assert _count(conn, "course_artifact", course.id) == 0
    assert _count(conn, "course_item_map", course.id) == 0
    assert _journal(conn, user, build.COURSE_FAILED_KIND) == 1


def test_build_fails_when_artifacts_over_cap(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "alice")
    concepts = _concepts(conn)
    _generate(conn, user, concepts, [_draft(concepts[0]), _draft(concepts[1])])
    job = _build_job(conn, user)
    build.run_build(conn, job, _cfg(max_bytes=10), DojoTrainerCli(FAKE_TRAINER, 30))

    course = get_course(conn, user, json.loads(job.payload)["course_id"])
    assert course is not None
    assert course.status == "failed"
    assert course.error == "artifacts exceed 10 bytes"
    assert _count(conn, "course_artifact", course.id) == 0


def test_build_fails_when_trainer_missing(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "alice")
    concepts = _concepts(conn)
    _generate(conn, user, concepts, [_draft(concepts[0]), _draft(concepts[1])])
    job = _build_job(conn, user)
    build.run_build(
        conn, job, _cfg(argv=MISSING_TRAINER), DojoTrainerCli(MISSING_TRAINER, 30)
    )

    course = get_course(conn, user, json.loads(job.payload)["course_id"])
    assert course is not None
    assert course.status == "failed"
    assert course.error is not None
    assert course.error.startswith("trainer: dojo next-id could not start")


def test_dojo_item_is_gap_in_unit_without_concept_id() -> None:
    draft = {"concept_id": 7, "prompt": "name a scale", "answer": "major"}
    assert build._dojo_item(draft) == {
        "type": "gap",
        "unit": build.DOJO_UNIT,
        "prompt": "name a scale",
        "answers": ["major"],
    }


def test_registry_has_course_kinds() -> None:
    registry = load_registry()
    assert build.KIND in registry.handlers
    assert "course.generate" in registry.output_hooks
