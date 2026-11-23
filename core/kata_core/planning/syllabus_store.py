"""Syllabus store (migration 0012). Every query filters by user_id.

A syllabus that belongs to another user reads as None and writes as False, so callers
answer 404 for both. Module rows and their concept links are only written after the
ownership check passes.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg


@dataclass(frozen=True)
class SyllabusModule:
    id: int
    position: int
    title: str
    body: str
    words: int
    concept_ids: list[int]


@dataclass(frozen=True)
class Syllabus:
    id: int
    user_id: int
    title: str
    status: str
    created_at: datetime
    modules: list[SyllabusModule]


_COLUMNS = "id, user_id, title, status, created_at"


def _module_rows(
    conn: psycopg.Connection[Any], syllabus_ids: Sequence[int]
) -> dict[int, list[SyllabusModule]]:
    """Load the modules (with concept ids) of several syllabi in one query, by syllabus id."""
    by_syllabus: dict[int, list[SyllabusModule]] = {sid: [] for sid in syllabus_ids}
    if not syllabus_ids:
        return by_syllabus
    rows = conn.execute(
        "SELECT m.syllabus_id, m.id, m.position, m.title, m.body, m.words, "
        "COALESCE(array_agg(c.concept_id ORDER BY c.concept_id) "
        "FILTER (WHERE c.concept_id IS NOT NULL), '{}') "
        "FROM syllabus_module m "
        "LEFT JOIN syllabus_module_concept c ON c.module_id = m.id "
        "WHERE m.syllabus_id = ANY(%s) "
        "GROUP BY m.id ORDER BY m.syllabus_id, m.position",
        (list(syllabus_ids),),
    ).fetchall()
    for row in rows:
        module = SyllabusModule(
            id=int(row[1]),
            position=int(row[2]),
            title=str(row[3]),
            body=str(row[4]),
            words=int(row[5]),
            concept_ids=[int(c) for c in row[6]],
        )
        by_syllabus[int(row[0])].append(module)
    return by_syllabus


def _syllabi(conn: psycopg.Connection[Any], rows: Iterable[tuple[Any, ...]]) -> list[Syllabus]:
    headers = [
        (int(row[0]), int(row[1]), str(row[2]), str(row[3]), row[4]) for row in rows
    ]
    modules = _module_rows(conn, [h[0] for h in headers])
    return [
        Syllabus(
            id=sid,
            user_id=uid,
            title=title,
            status=status,
            created_at=created_at,
            modules=modules[sid],
        )
        for sid, uid, title, status, created_at in headers
    ]


def create_syllabus(
    conn: psycopg.Connection[Any],
    user_id: int,
    title: str,
    modules: Sequence[tuple[str, str]],
) -> Syllabus:
    """Insert a syllabus for `user_id` with `modules` as (title, body) pairs, in order.

    `words` of each module counts the whitespace-separated words of its body. Returns the
    stored syllabus with its modules.
    """
    with conn.transaction():
        row = conn.execute(
            f"INSERT INTO syllabus (user_id, title) VALUES (%s, %s) RETURNING {_COLUMNS}",
            (user_id, title),
        ).fetchone()
        if row is None:
            raise RuntimeError("create_syllabus: INSERT ... RETURNING returned no row")
        syllabus_id = int(row[0])
        for position, (module_title, body) in enumerate(modules):
            conn.execute(
                "INSERT INTO syllabus_module (syllabus_id, position, title, body, words) "
                "VALUES (%s, %s, %s, %s, %s)",
                (syllabus_id, position, module_title, body, len(body.split())),
            )
    stored = get_syllabus(conn, user_id, syllabus_id)
    if stored is None:
        raise RuntimeError("create_syllabus: inserted syllabus not readable by its owner")
    return stored


def get_syllabus(conn: psycopg.Connection[Any], user_id: int, syllabus_id: int) -> Syllabus | None:
    """Return the syllabus of `user_id` with `syllabus_id`, or None when it is missing or foreign."""
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM syllabus WHERE id = %s AND user_id = %s",
        (syllabus_id, user_id),
    ).fetchall()
    found = _syllabi(conn, rows)
    return found[0] if found else None


def list_syllabi(
    conn: psycopg.Connection[Any],
    user_id: int,
    limit: int,
    before_id: int | None = None,
) -> list[Syllabus]:
    """Return up to `limit` syllabi of `user_id`, newest id first.

    `before_id` pages: only syllabi with a smaller id are returned. Raises ValueError
    when `limit` is below 1.
    """
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM syllabus "
        "WHERE user_id = %s AND (%s::bigint IS NULL OR id < %s) "
        "ORDER BY id DESC LIMIT %s",
        (user_id, before_id, before_id, limit),
    ).fetchall()
    return _syllabi(conn, rows)


def delete_syllabus(conn: psycopg.Connection[Any], user_id: int, syllabus_id: int) -> bool:
    """Delete the syllabus of `user_id`; modules and concept links cascade.

    False when it is missing or foreign.
    """
    cur = conn.execute(
        "DELETE FROM syllabus WHERE id = %s AND user_id = %s",
        (syllabus_id, user_id),
    )
    return cur.rowcount == 1


def replace_modules(
    conn: psycopg.Connection[Any],
    user_id: int,
    syllabus_id: int,
    modules: Sequence[tuple[str, str]],
) -> bool:
    """Replace the modules of the syllabus of `user_id` with `modules` as (title, body) pairs.

    Old modules and their concept links cascade away. False, with nothing written, when the
    syllabus is missing or foreign.
    """
    with conn.transaction():
        owned = conn.execute(
            "SELECT id FROM syllabus WHERE id = %s AND user_id = %s",
            (syllabus_id, user_id),
        ).fetchone()
        if owned is None:
            return False
        conn.execute("DELETE FROM syllabus_module WHERE syllabus_id = %s", (syllabus_id,))
        for position, (module_title, body) in enumerate(modules):
            conn.execute(
                "INSERT INTO syllabus_module (syllabus_id, position, title, body, words) "
                "VALUES (%s, %s, %s, %s, %s)",
                (syllabus_id, position, module_title, body, len(body.split())),
            )
    return True


def set_module_concepts(
    conn: psycopg.Connection[Any],
    user_id: int,
    module_id: int,
    concept_ids: Iterable[int],
) -> bool:
    """Replace the concepts of a module of `user_id`.

    False, with links unchanged, when the module is missing or foreign, or when any concept
    is unknown or private to another user. Duplicate ids are stored once.
    """
    ids = sorted(set(concept_ids))
    owned = conn.execute(
        "SELECT 1 FROM syllabus_module m JOIN syllabus s ON s.id = m.syllabus_id "
        "WHERE m.id = %s AND s.user_id = %s",
        (module_id, user_id),
    ).fetchone()
    if owned is None:
        return False
    visible = conn.execute(
        "SELECT count(*) FROM concepts "
        "WHERE id = ANY(%s) AND (owner_user_id IS NULL OR owner_user_id = %s)",
        (ids, user_id),
    ).fetchone()
    if visible is None or int(visible[0]) != len(ids):
        return False
    with conn.transaction():
        conn.execute("DELETE FROM syllabus_module_concept WHERE module_id = %s", (module_id,))
        for concept_id in ids:
            conn.execute(
                "INSERT INTO syllabus_module_concept (module_id, concept_id) VALUES (%s, %s)",
                (module_id, concept_id),
            )
    return True
