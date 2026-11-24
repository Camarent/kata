"""Scan extraction output hook: teachable filter, concept resolve, ignored concepts, output rewrite (M20)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from kata_core.config import Config
from kata_core.jobs.queue import Job, claim_next, enqueue, get_job
from kata_core.jobs.runner import Registry, run_output_hook
from kata_core.scan import extract
from kata_core.scan.extract import extract_output_hook
from kata_core.scan.job_kinds import OUTPUT_HOOKS, SCAN_EXTRACT_KIND
from kata_core.storage.concepts import ignore_concept
from kata_core.storage.taxonomy import ensure_category, ensure_topic
from support.scratch_db import ScratchDatabase

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
TEACHABLE = "Mitosis divides one cell into two identical daughter cells during growth."
PHONE = "Call us on +44 20 7946 0958 for enrolment questions this week."


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


@pytest.fixture(autouse=True)
def _scan_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        extract,
        "load_config",
        lambda: Config({"scan": {"min_block_chars": 40, "max_blocks_per_job": 3}}),
    )


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def _shared_topic(conn: psycopg.Connection[Any]) -> tuple[int, int]:
    """Return (area_id, topic_id) of a shared topic in a shared area."""
    category = ensure_category(conn, "Biology")
    return category, ensure_topic(conn, category, "Cells", owner_user_id=None)


def _shared_concept(conn: psycopg.Connection[Any], topic_id: int, label: str) -> int:
    row = conn.execute(
        "INSERT INTO concepts (topic_id, label) VALUES (%s, %s) RETURNING id",
        (topic_id, label),
    ).fetchone()
    assert row is not None
    return int(row[0])


def _leased_job(
    conn: psycopg.Connection[Any],
    user_id: int,
    area_id: int,
    topic_id: int,
    blocks: list[tuple[int, str]],
) -> Job:
    payload = json.dumps(
        {
            "area_id": area_id,
            "topic_id": topic_id,
            "blocks": [{"id": block_id, "text": text} for block_id, text in blocks],
        }
    )
    job_id = enqueue(conn, user_id, payload, kind=SCAN_EXTRACT_KIND)
    job = claim_next(conn, user_id, T0, 60, kinds=(SCAN_EXTRACT_KIND,))
    assert job is not None and job.id == job_id
    return job


def _run(
    conn: psycopg.Connection[Any],
    user_id: int,
    area_id: int,
    topic_id: int,
    blocks: list[tuple[int, str]],
    worker_output: dict[str, Any],
) -> dict[str, Any]:
    job = _leased_job(conn, user_id, area_id, topic_id, blocks)
    run_output_hook(conn, Registry(output_hooks=OUTPUT_HOOKS), job, worker_output)
    stored = get_job(conn, job.id, user_id)
    assert stored is not None and stored.output is not None
    return stored.output


def _concept(word: str, name: str, candidates: list[str] | None = None) -> dict[str, Any]:
    return {
        "word": word,
        "name": name,
        "definition": "",
        "candidates": candidates or [],
    }


def test_registry_maps_scan_extract_to_hook() -> None:
    assert OUTPUT_HOOKS[SCAN_EXTRACT_KIND] is extract_output_hook


def test_non_teachable_block_is_skipped_with_reason(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "extract-skip")
    area, topic = _shared_topic(conn)
    worker = {
        "blocks": [
            {"id": 1, "concepts": [_concept("Mitosis", "Mitosis")]},
            {"id": 2, "concepts": [_concept("Call", "Call")]},
        ]
    }
    output = _run(conn, alice, area, topic, [(1, TEACHABLE), (2, PHONE)], worker)
    assert output["blocks"][1] == {"blockId": 2, "skipped": "phone number", "concepts": []}
    assert output["blocks"][0]["blockId"] == 1
    assert "skipped" not in output["blocks"][0]


def test_alias_merges_into_existing_concept_in_output(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "extract-alias")
    area, topic = _shared_topic(conn)
    handshake = _shared_concept(conn, topic, "Three-way handshake")
    worker = {"blocks": [{"id": 1, "concepts": [_concept("Handshake", "Three-way handshake")]}]}
    output = _run(conn, alice, area, topic, [(1, TEACHABLE)], worker)
    concepts = output["blocks"][0]["concepts"]
    assert len(concepts) == 1
    assert concepts[0]["word"] == "Handshake"
    assert concepts[0]["conceptId"] == handshake
    assert concepts[0]["label"] == "Three-way handshake"


def test_which_one_item_lists_candidates_without_concept_id(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "extract-which")
    area, topic = _shared_topic(conn)
    worker = {
        "blocks": [
            {
                "id": 1,
                "concepts": [
                    _concept("Cell", "Cell", ["Cell (biology)", "Cell (battery)"]),
                ],
            }
        ]
    }
    output = _run(conn, alice, area, topic, [(1, TEACHABLE)], worker)
    item = output["blocks"][0]["concepts"][0]
    assert item["word"] == "Cell"
    assert item["conceptId"] is None
    assert [c["label"] for c in item["candidates"]] == ["Cell (biology)", "Cell (battery)"]
    assert all(isinstance(c["conceptId"], int) for c in item["candidates"])


def test_ignored_concept_is_absent_from_output(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "extract-ignore")
    area, topic = _shared_topic(conn)
    mitosis = _shared_concept(conn, topic, "Mitosis")
    ignore_concept(conn, alice, mitosis)
    worker = {
        "blocks": [
            {
                "id": 1,
                "concepts": [_concept("Mitosis", "Mitosis"), _concept("Growth", "Growth")],
            }
        ]
    }
    output = _run(conn, alice, area, topic, [(1, TEACHABLE)], worker)
    labels = [c["label"] for c in output["blocks"][0]["concepts"]]
    assert labels == ["Growth"]


def test_unknown_topic_raises_lookup_error(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "extract-topic")
    area, _ = _shared_topic(conn)
    job = _leased_job(conn, alice, area, 999_999, [(1, TEACHABLE)])
    with pytest.raises(LookupError):
        run_output_hook(conn, Registry(output_hooks=OUTPUT_HOOKS), job, {"blocks": []})


def test_too_many_blocks_raises_value_error(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "extract-many")
    area, topic = _shared_topic(conn)
    blocks = [(i, TEACHABLE) for i in range(1, 5)]
    job = _leased_job(conn, alice, area, topic, blocks)
    with pytest.raises(ValueError):
        run_output_hook(conn, Registry(output_hooks=OUTPUT_HOOKS), job, {"blocks": []})


def test_stored_output_is_the_rewritten_result(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "extract-rewrite")
    area, topic = _shared_topic(conn)
    worker = {"blocks": [{"id": 1, "concepts": [_concept("Mitosis", "Mitosis")]}]}
    output = _run(conn, alice, area, topic, [(1, TEACHABLE)], worker)
    assert set(output) == {"areaId", "topicId", "blocks"}
    assert output["areaId"] == area
    assert output["topicId"] == topic
    assert set(output["blocks"][0]["concepts"][0]) == {
        "word",
        "conceptId",
        "label",
        "definition",
        "state",
        "candidates",
    }
