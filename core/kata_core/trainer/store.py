"""Course store (migration 0009). Every query filters by user_id.

A course that belongs to another user reads as None and writes as False, so callers
answer 404 for both. Child rows are only written after the ownership check passes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg
from psycopg.errors import UniqueViolation


class EmptyCourseTitle(ValueError):
    """The title is empty or whitespace only."""


class DuplicateCourseTitle(ValueError):
    """The user already has a course whose normalised title is the same."""


# Normal form of a course title, as migration 0014 indexes it. The migration file
# carries this text copied verbatim; tests/core/test_course_title_unique.py checks that.
NORMAL_TITLE_SQL = r"lower(btrim(regexp_replace(title, '\s+', ' ', 'g')))"
COURSE_TITLE_INDEX = "course_user_id_title_norm_uidx"


@dataclass(frozen=True)
class Course:
    id: int
    user_id: int
    title: str
    status: str
    concept_ids: list[int]
    error: str | None
    created_at: datetime
    updated_at: datetime


_COLUMNS = "id, user_id, title, status, concept_ids, error, created_at, updated_at"


def _course(row: tuple[Any, ...]) -> Course:
    return Course(
        id=int(row[0]),
        user_id=int(row[1]),
        title=str(row[2]),
        status=str(row[3]),
        concept_ids=[int(c) for c in row[4]],
        error=row[5],
        created_at=row[6],
        updated_at=row[7],
    )


def _owned(conn: psycopg.Connection[Any], user_id: int, course_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM course WHERE id = %s AND user_id = %s",
        (course_id, user_id),
    ).fetchone()
    return row is not None


def title_taken(conn: psycopg.Connection[Any], user_id: int, title: str) -> bool:
    """True when `user_id` already has a course whose normal form equals that of `title`."""
    row = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM course WHERE user_id = %s "
        f"AND {NORMAL_TITLE_SQL} = (SELECT {NORMAL_TITLE_SQL} FROM (SELECT %s::text AS title) t))",
        (user_id, title),
    ).fetchone()
    return row is not None and bool(row[0])


def create_course(
    conn: psycopg.Connection[Any],
    user_id: int,
    title: str,
    concept_ids: list[int],
) -> Course:
    """Insert a `queued` course for `user_id` and return it.

    Raises EmptyCourseTitle for an empty or whitespace-only title, and
    DuplicateCourseTitle when the user already has the same normalised title.
    """
    if not title.strip():
        raise EmptyCourseTitle("course title is empty")
    try:
        # A savepoint (or transaction) keeps the connection usable after a violation.
        with conn.transaction():
            row = conn.execute(
                "INSERT INTO course (user_id, title, status, concept_ids) "
                f"VALUES (%s, %s, 'queued', %s::bigint[]) RETURNING {_COLUMNS}",
                (user_id, title, concept_ids),
            ).fetchone()
    except UniqueViolation as exc:
        if exc.diag.constraint_name != COURSE_TITLE_INDEX:
            raise
        raise DuplicateCourseTitle(f"user {user_id} already has course title {title!r}") from exc
    if row is None:
        raise RuntimeError("create_course: INSERT ... RETURNING returned no row")
    return _course(row)


def get_course(conn: psycopg.Connection[Any], user_id: int, course_id: int) -> Course | None:
    """Return the course of `user_id` with `course_id`, or None when it is missing or foreign."""
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM course WHERE id = %s AND user_id = %s",
        (course_id, user_id),
    ).fetchone()
    return None if row is None else _course(row)


def list_courses(
    conn: psycopg.Connection[Any],
    user_id: int,
    limit: int,
    before_id: int | None = None,
) -> list[Course]:
    """Return up to `limit` courses of `user_id`, newest id first.

    `before_id` pages: only courses with a smaller id are returned. Raises ValueError
    when `limit` is below 1.
    """
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM course "
        "WHERE user_id = %s AND (%s::bigint IS NULL OR id < %s) "
        "ORDER BY id DESC LIMIT %s",
        (user_id, before_id, before_id, limit),
    ).fetchall()
    return [_course(row) for row in rows]


def delete_course(conn: psycopg.Connection[Any], user_id: int, course_id: int) -> bool:
    """Delete the course of `user_id` (children cascade). False when it is missing or foreign."""
    cur = conn.execute(
        "DELETE FROM course WHERE id = %s AND user_id = %s",
        (course_id, user_id),
    )
    return cur.rowcount == 1


def set_status(
    conn: psycopg.Connection[Any],
    user_id: int,
    course_id: int,
    status: str,
    error: str | None = None,
) -> bool:
    """Set the status (and error text) of a course of `user_id`. False when it is missing or foreign.

    The database CHECK rejects unknown statuses.
    """
    cur = conn.execute(
        "UPDATE course SET status = %s, error = %s, updated_at = now() "
        "WHERE id = %s AND user_id = %s",
        (status, error, course_id, user_id),
    )
    return cur.rowcount == 1


def add_files(
    conn: psycopg.Connection[Any],
    user_id: int,
    course_id: int,
    files: Mapping[str, str],
) -> bool:
    """Store generated source `files` (path -> text) of a course of `user_id`.

    False, with nothing written, when the course is missing or foreign.
    """
    if not _owned(conn, user_id, course_id):
        return False
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO course_file (course_id, path, content) VALUES (%s, %s, %s)",
            [(course_id, path, content) for path, content in files.items()],
        )
    return True


def read_files(
    conn: psycopg.Connection[Any],
    user_id: int,
    course_id: int,
) -> dict[str, str] | None:
    """Return the generated source files (path -> text) of a course of `user_id`, sorted by path.

    None when the course is missing or foreign.
    """
    if not _owned(conn, user_id, course_id):
        return None
    rows = conn.execute(
        "SELECT path, content FROM course_file WHERE course_id = %s ORDER BY path",
        (course_id,),
    ).fetchall()
    return {str(path): str(content) for path, content in rows}


def read_artifact(
    conn: psycopg.Connection[Any],
    user_id: int,
    course_id: int,
    path: str,
) -> tuple[str, bytes] | None:
    """Return `(media_type, bytes)` of the built artifact `path` of a course of `user_id`.

    None when the course is missing or foreign, or when it has no artifact named `path`.
    """
    if not _owned(conn, user_id, course_id):
        return None
    row = conn.execute(
        "SELECT media_type, content FROM course_artifact WHERE course_id = %s AND path = %s",
        (course_id, path),
    ).fetchone()
    if row is None:
        return None
    return str(row[0]), bytes(row[1])


def add_artifacts(
    conn: psycopg.Connection[Any],
    user_id: int,
    course_id: int,
    artifacts: Mapping[str, tuple[str, bytes]],
) -> bool:
    """Store built `artifacts` (path -> (media_type, bytes)) of a course of `user_id`.

    False, with nothing written, when the course is missing or foreign.
    """
    if not _owned(conn, user_id, course_id):
        return False
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO course_artifact (course_id, path, media_type, content) "
            "VALUES (%s, %s, %s, %s)",
            [
                (course_id, path, media_type, content)
                for path, (media_type, content) in artifacts.items()
            ],
        )
    return True


def add_item_map(
    conn: psycopg.Connection[Any],
    user_id: int,
    course_id: int,
    items: Mapping[str, int],
) -> bool:
    """Map item ids to concept ids (item -> concept) for a course of `user_id`.

    False, with nothing written, when the course is missing or foreign.
    """
    if not _owned(conn, user_id, course_id):
        return False
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO course_item_map (course_id, item_id, concept_id) VALUES (%s, %s, %s)",
            [(course_id, item_id, concept_id) for item_id, concept_id in items.items()],
        )
    return True
