"""Scan classification output hook: taxonomy match, new private topic, cache row, output rewrite (M20)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from kata_core.config import Config
from kata_core.jobs.queue import Job, claim_next, enqueue, get_job
from kata_core.scan import classify
from kata_core.scan.classify import classify_output_hook, visible_taxonomy
from kata_core.scan.job_kinds import OUTPUT_HOOKS, SCAN_CLASSIFY_KIND
from kata_core.storage.page_scan import get_classification
from kata_core.storage.taxonomy import ensure_category, ensure_topic
from support.scratch_db import ScratchDatabase

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
PAGE_KEY = "https://example.test/page-1"


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


@pytest.fixture(autouse=True)
def _scan_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(classify, "load_config", lambda: Config({"scan": {"max_candidates": 5}}))


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def _leased_job(conn: psycopg.Connection[Any], user_id: int) -> Job:
    payload = json.dumps({"page_key": PAGE_KEY, "text": "Cells divide by mitosis."})
    job_id = enqueue(conn, user_id, payload, kind=SCAN_CLASSIFY_KIND)
    job = claim_next(conn, user_id, T0, 60, kinds=(SCAN_CLASSIFY_KIND,))
    assert job is not None and job.id == job_id
    return job


def _shared_topic(conn: psycopg.Connection[Any], area: str, topic: str) -> int:
    category = ensure_category(conn, area)
    return ensure_topic(conn, category, topic, owner_user_id=None)


def _run(conn: psycopg.Connection[Any], user_id: int, output: dict[str, Any]) -> dict[str, Any]:
    job = _leased_job(conn, user_id)
    classify_output_hook(conn, job, output)
    stored = get_job(conn, job.id, user_id)
    assert stored is not None and stored.output is not None
    return stored.output


def test_registry_maps_scan_classify_to_hook() -> None:
    assert OUTPUT_HOOKS[SCAN_CLASSIFY_KIND] is classify_output_hook


def test_visible_taxonomy_lists_shared_and_own_topics_only(conn: psycopg.Connection[Any]) -> None:
    alice, bob = _user(conn, "alice-vis"), _user(conn, "bob-vis")
    _shared_topic(conn, "Biology", "Cells")
    category = ensure_category(conn, "Biology")
    ensure_topic(conn, category, "Alice notes", owner_user_id=alice)
    ensure_topic(conn, category, "Bob notes", owner_user_id=bob)

    assert visible_taxonomy(conn, alice) == [("Biology", "Cells"), ("Biology", "Alice notes")]


def test_existing_area_and_topic_match(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "match-exact")
    topic_id = _shared_topic(conn, "Biology", "Cells")

    result = _run(conn, user, {"area": "Biology", "topic": "Cells", "candidates": []})

    assert result["topicId"] == topic_id
    assert result["area"] == "Biology"
    assert result["topic"] == "Cells"
    assert result["isNew"] is False


def test_match_ignores_case(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "match-case")
    topic_id = _shared_topic(conn, "Biology", "Cells")

    result = _run(conn, user, {"area": "biology", "topic": "CELLS", "candidates": []})

    assert result["topicId"] == topic_id
    assert result["area"] == "Biology"
    assert result["topic"] == "Cells"
    assert result["isNew"] is False


def test_miss_creates_private_topic_for_owner(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "new-topic")

    result = _run(conn, user, {"area": "Chemistry", "topic": "Bonds", "candidates": []})

    assert result["isNew"] is True
    assert result["area"] == "Chemistry"
    assert result["topic"] == "Bonds"
    row = conn.execute("SELECT owner_user_id FROM topics WHERE id = %s", (result["topicId"],)).fetchone()
    assert row is not None and row[0] == user


def test_other_users_private_topic_is_not_matched(conn: psycopg.Connection[Any]) -> None:
    owner, other = _user(conn, "private-owner"), _user(conn, "private-other")
    category = ensure_category(conn, "Biology")
    private_id = ensure_topic(conn, category, "Secret", owner_user_id=owner)

    result = _run(conn, other, {"area": "Biology", "topic": "Secret", "candidates": []})

    assert result["isNew"] is True
    assert result["topicId"] != private_id
    row = conn.execute("SELECT owner_user_id FROM topics WHERE id = %s", (result["topicId"],)).fetchone()
    assert row is not None and row[0] == other


@pytest.mark.parametrize(
    "output",
    [
        {"area": 5, "topic": "Cells", "candidates": []},
        {"area": "Biology", "topic": None, "candidates": []},
        {"area": "  ", "topic": "Cells", "candidates": []},
        {"area": "Biology", "topic": "", "candidates": []},
    ],
)
def test_bad_output_raises_and_stores_nothing(conn: psycopg.Connection[Any], output: dict[str, Any]) -> None:
    user = _user(conn, f"bad-{uuid.uuid4().hex[:8]}")
    job = _leased_job(conn, user)

    with pytest.raises(ValueError):
        classify_output_hook(conn, job, output)

    stored = get_job(conn, job.id, user)
    assert stored is not None and stored.output is None
    assert get_classification(conn, user, PAGE_KEY) is None


def test_candidates_drop_malformed_and_trim_to_max(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "candidates")
    good = [{"area": f"Area {i}", "topic": f"Topic {i}"} for i in range(7)]
    raw = [good[0], "not a pair", {"area": "No topic"}, {"area": 3, "topic": "x"}, *good[1:]]

    result = _run(conn, user, {"area": "Chemistry", "topic": "Bonds", "candidates": raw})

    assert result["candidates"] == good[:5]


def test_cache_row_written_for_page(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "cache-row")
    candidates = [{"area": "Biology", "topic": "Cells"}]

    result = _run(conn, user, {"area": "Biology", "topic": "Cells", "candidates": candidates})

    assert get_classification(conn, user, PAGE_KEY) == (result["topicId"], candidates)
