"""Syllabus import and triage view (D10): parse and store a syllabus, then compute each module's triage.

`import_syllabus` parses the text, stores the modules and links each module to the user's visible
concepts whose label occurs in it. `triage_view` reads the stored links and the user's mastery, and
computes triage, action and effort per module. It writes nothing. Limits and numbers come from `cfg`:
`[syllabus] max_bytes`, `[knowledge]` thresholds and base scores, `[planning]` shares, words and minutes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg

from kata_core.config import Config
from kata_core.importer.syllabus import parse_modules
from kata_core.knowledge.mastery import base_score
from kata_core.planning.syllabus_store import create_syllabus, get_syllabus, set_module_concepts
from kata_core.planning.triage import (
    ACTION_LEARN,
    ACTION_PRACTICE,
    ACTION_SKIM,
    ACTION_SKIP,
    action,
    effort,
    known_share,
    match_concepts,
    triage,
)

ACTIONS = (ACTION_SKIP, ACTION_SKIM, ACTION_PRACTICE, ACTION_LEARN)
MATCH_STATES = ("known", "learning", "new")


class SyllabusFlowError(ValueError):
    """A syllabus flow rule failed: the text is over the size limit, or the syllabus is not the caller's."""


class SyllabusTooLarge(SyllabusFlowError):
    """The syllabus text is over `[syllabus] max_bytes`."""


class SyllabusNotFound(SyllabusFlowError):
    """The syllabus is missing or belongs to another user."""


@dataclass(frozen=True)
class ModuleTriage:
    module_id: int
    position: int
    title: str
    triage: str
    action: str
    effort_minutes: int


def import_syllabus(conn: psycopg.Connection[Any], user_id: int, title: str, text: str, cfg: Config) -> int:
    """Parse `text` into modules, store them for `user_id` and return the syllabus id.

    Each module is linked to the visible concepts (shared, or owned by `user_id`) whose label occurs
    in its title or body. Raises SyllabusTooLarge over `[syllabus] max_bytes`, and ParseError when the
    text is blank. Parsing and the size check run first, so either one touches nothing.
    """
    max_bytes = int(cfg.get("syllabus", "max_bytes"))
    size = len(text.encode())
    if size > max_bytes:
        raise SyllabusTooLarge(f"syllabus is {size} bytes, over the limit of {max_bytes}")
    modules = parse_modules(text)
    labels = _visible_labels(conn, user_id)
    with conn.transaction():
        made = create_syllabus(conn, user_id, title, [(m.title, m.body) for m in modules])
        for stored, module in zip(made.modules, modules, strict=True):
            concept_ids = [int(cid) for cid in match_concepts(f"{module.title}\n{module.body}", labels)]
            if concept_ids and not set_module_concepts(conn, user_id, stored.id, concept_ids):
                raise SyllabusFlowError(f"concept links refused for module {stored.id}")
    return made.id


def triage_view(
    conn: psycopg.Connection[Any], user_id: int, syllabus_id: int, cfg: Config
) -> list[ModuleTriage]:
    """Triage, action and effort of each module of the syllabus, in position order. Stores nothing.

    A matched concept scores from its stored mastery, else from the base score of its mark state.
    Raises SyllabusNotFound when the syllabus is missing or belongs to another user.
    """
    syllabus = get_syllabus(conn, user_id, syllabus_id)
    if syllabus is None:
        raise SyllabusNotFound(f"syllabus {syllabus_id} not found")
    known_threshold = float(cfg.get("knowledge", "known_threshold"))
    learning_threshold = float(cfg.get("knowledge", "learning_threshold"))
    bases = {state: float(cfg.get("knowledge", f"base_{state}")) for state in MATCH_STATES}
    skim_share = float(cfg.get("planning", "skim_share"))
    words_per_unit = int(cfg.get("planning", "words_per_unit"))
    minutes = {name: int(cfg.get("planning", f"minutes_{name}")) for name in ACTIONS}
    concept_ids = sorted({cid for module in syllabus.modules for cid in module.concept_ids})
    scores = _concept_scores(conn, user_id, concept_ids, bases)
    views: list[ModuleTriage] = []
    for module in syllabus.modules:
        module_scores = [scores[cid] for cid in module.concept_ids]
        state = triage(module_scores, known_threshold, learning_threshold)
        act = action(state, known_share(module_scores, known_threshold), skim_share)
        views.append(
            ModuleTriage(
                module_id=module.id,
                position=module.position,
                title=module.title,
                triage=state,
                action=act,
                effort_minutes=effort(act, module.words, minutes, words_per_unit),
            )
        )
    return views


def _visible_labels(conn: psycopg.Connection[Any], user_id: int) -> dict[str, str]:
    """Labels of the concepts visible to `user_id`, keyed by concept id as text, in id order."""
    rows = conn.execute(
        "SELECT c.id, c.label FROM concepts c JOIN topics t ON t.id = c.topic_id "
        "WHERE (t.owner_user_id IS NULL OR t.owner_user_id = %s) "
        "AND (c.owner_user_id IS NULL OR c.owner_user_id = %s) ORDER BY c.id",
        (user_id, user_id),
    ).fetchall()
    return {str(row[0]): str(row[1]) for row in rows}


def _concept_scores(
    conn: psycopg.Connection[Any], user_id: int, concept_ids: list[int], bases: dict[str, float]
) -> dict[int, float]:
    """Score of each concept id for `user_id`: stored mastery, else the base score of its mark state."""
    if not concept_ids:
        return {}
    rows = conn.execute(
        "SELECT c.id, COALESCE(m.state, 'new'), ms.score FROM concepts c "
        "LEFT JOIN concept_marks m ON m.concept_id = c.id AND m.user_id = %s "
        "LEFT JOIN concept_mastery ms ON ms.concept_id = c.id AND ms.user_id = %s "
        "WHERE c.id = ANY(%s)",
        (user_id, user_id, concept_ids),
    ).fetchall()
    return {
        int(cid): float(score) if score is not None else base_score(str(state), bases)
        for cid, state, score in rows
    }
