"""Quiz job kinds: allowlist before fetch, source stored with tier and licence, model input, bad reply (M22)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from kata_core.config import Config
from kata_core.jobs.queue import Job, claim_next, enqueue, get_job
from kata_core.jobs.runner import load_registry
from kata_core.quiz import job_kinds, service
from kata_core.quiz.allowlist import Tier, exams_allowed
from kata_core.quiz.fetch import QuizFetchError
from kata_core.quiz.job_kinds import QUIZ_FETCH_KIND, QUIZ_GENERATE_KIND
from kata_core.quiz.questions import SOURCE_BEGIN, build_prompt
from support.scratch_db import ScratchDatabase

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
TIER_ONE_URL = "https://docs.python.org/3/library/json.html"
TIER_TWO_URL = "https://en.wikipedia.org/wiki/JSON"
USER_URL = "https://notes.example.test/json"
SOURCE_TEXT = "JSON is a text format. It stores data as objects and arrays."
QUESTION = "What is JSON?"
GOOD_REPLY = json.dumps(
    {
        "questions": [
            {
                "question": QUESTION,
                "choices": ["A text format", "A compiler", "A database", "A browser"],
                "answer_index": 0,
                "quote": "JSON is a text format",
            }
        ]
    }
)


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


@pytest.fixture(autouse=True)
def _quiz_config(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = Config({"quiz": {"max_fetch_bytes": 4096, "max_questions_per_source": 50}})
    monkeypatch.setattr(job_kinds, "load_config", lambda: cfg)


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def _fake_fetch(monkeypatch: pytest.MonkeyPatch, text: str = SOURCE_TEXT) -> list[str]:
    calls: list[str] = []

    def fake(url: str, **_: Any) -> str:
        calls.append(url)
        return text

    monkeypatch.setattr(service, "fetch_text", fake)
    return calls


def _claimed(conn: psycopg.Connection[Any], user_id: int, kind: str, payload: str) -> Job:
    job_id = enqueue(conn, user_id, payload, kind=kind)
    job = claim_next(conn, user_id, T0, 60, kinds=(kind,))
    assert job is not None and job.id == job_id
    return job


def _queued_generate(conn: psycopg.Connection[Any], user_id: int) -> Job:
    row = conn.execute(
        "SELECT id FROM jobs WHERE user_id = %s AND kind = %s ORDER BY id DESC LIMIT 1",
        (user_id, QUIZ_GENERATE_KIND),
    ).fetchone()
    assert row is not None
    job = claim_next(conn, user_id, T0, 60, kinds=(QUIZ_GENERATE_KIND,))
    assert job is not None and job.id == row[0]
    return job


def _source_row(conn: psycopg.Connection[Any], url: str) -> tuple[int, str]:
    row = conn.execute("SELECT tier, licence FROM quiz_source WHERE url = %s", (url,)).fetchone()
    assert row is not None
    return int(row[0]), str(row[1])


def test_registry_maps_quiz_kinds_to_handler_and_hook() -> None:
    registry = load_registry()
    assert registry.handlers[QUIZ_FETCH_KIND] is job_kinds.fetch_handler
    assert registry.output_hooks[QUIZ_GENERATE_KIND] is job_kinds.generate_output_hook


def test_url_off_allowlist_fails_before_any_fetch(
    conn: psycopg.Connection[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _fake_fetch(monkeypatch)
    user_id = _user(conn, "quiz-off-list")
    job = _claimed(conn, user_id, QUIZ_FETCH_KIND, json.dumps({"url": "https://evil.example.test/"}))
    with pytest.raises(ValueError, match="allowlist"):
        job_kinds.fetch_handler(conn, job)
    assert calls == []


def test_fetch_stores_tier_one_source_with_licence_and_queues_generate(
    conn: psycopg.Connection[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _fake_fetch(monkeypatch)
    user_id = _user(conn, "quiz-tier-one")
    job = _claimed(conn, user_id, QUIZ_FETCH_KIND, json.dumps({"url": TIER_ONE_URL}))
    job_kinds.fetch_handler(conn, job)
    assert calls == [TIER_ONE_URL]
    tier, licence = _source_row(conn, TIER_ONE_URL)
    assert tier == 1
    assert "Python Software Foundation License" in licence
    assert exams_allowed(Tier(tier))
    queued = _queued_generate(conn, user_id)
    payload = json.loads(queued.payload)
    assert payload["text"] == SOURCE_TEXT


def test_tier_two_source_stored_as_tier_two_and_no_exam(
    conn: psycopg.Connection[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_fetch(monkeypatch)
    user_id = _user(conn, "quiz-tier-two")
    job = _claimed(conn, user_id, QUIZ_FETCH_KIND, json.dumps({"url": TIER_TWO_URL}))
    job_kinds.fetch_handler(conn, job)
    tier, licence = _source_row(conn, TIER_TWO_URL)
    assert tier == 2
    assert "CC BY-SA 4.0" in licence
    assert not exams_allowed(Tier(tier))


def test_fetch_error_stores_nothing(
    conn: psycopg.Connection[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(_url: str, **_: Any) -> str:
        raise QuizFetchError("redirects are not followed")

    monkeypatch.setattr(service, "fetch_text", refuse)
    user_id = _user(conn, "quiz-refused")
    job = _claimed(conn, user_id, QUIZ_FETCH_KIND, json.dumps({"url": TIER_ONE_URL}))
    with pytest.raises(QuizFetchError):
        job_kinds.fetch_handler(conn, job)
    row = conn.execute("SELECT count(*) FROM quiz_source WHERE url = %s", (TIER_ONE_URL,)).fetchone()
    assert row is not None and row[0] == 0


def test_model_input_is_only_marked_source_text() -> None:
    payload = service.generate_payload(7, SOURCE_TEXT)
    job = Job(
        id=1,
        user_id=3,
        payload=payload,
        status="leased",
        lease_expires_at=T0,
        attempts=1,
        result_topic_id=None,
        kind=QUIZ_GENERATE_KIND,
        output=None,
    )
    prompt = service.model_input(job)
    assert prompt == build_prompt(SOURCE_TEXT)
    assert SOURCE_TEXT in prompt
    assert SOURCE_BEGIN in prompt
    for leaked in ("source_id", "user_id", "concept", "keys"):
        assert leaked not in prompt


def test_good_reply_caches_questions(conn: psycopg.Connection[Any], monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_fetch(monkeypatch)
    user_id = _user(conn, "quiz-good-reply")
    fetch = _claimed(conn, user_id, QUIZ_FETCH_KIND, json.dumps({"url": TIER_ONE_URL}))
    job_kinds.fetch_handler(conn, fetch)
    job = _queued_generate(conn, user_id)
    job_kinds.generate_output_hook(conn, job, {"raw": GOOD_REPLY})
    row = conn.execute("SELECT count(*) FROM quiz_question").fetchone()
    assert row is not None and row[0] == 1


@pytest.mark.parametrize(
    "output",
    [
        {"raw": "not json"},
        {"raw": json.dumps({"questions": "nope"})},
        {"raw": json.dumps({"questions": [{"question": QUESTION}]})},
        {"raw": json.dumps({"questions": [{"question": QUESTION, "choices": ["a", "b", "c"],
                                           "answer_index": 0, "quote": "not in the source"}]})},
        {"answer": GOOD_REPLY},
    ],
)
def test_bad_reply_fails_and_stores_nothing(
    conn: psycopg.Connection[Any], monkeypatch: pytest.MonkeyPatch, output: dict[str, Any]
) -> None:
    _fake_fetch(monkeypatch)
    user_id = _user(conn, "quiz-bad-reply")
    fetch = _claimed(conn, user_id, QUIZ_FETCH_KIND, json.dumps({"url": TIER_ONE_URL}))
    job_kinds.fetch_handler(conn, fetch)
    job = _queued_generate(conn, user_id)
    with pytest.raises(ValueError):
        job_kinds.generate_output_hook(conn, job, output)
    row = conn.execute("SELECT count(*) FROM quiz_question").fetchone()
    assert row is not None and row[0] == 0
    assert get_job(conn, job.id, user_id) is not None
