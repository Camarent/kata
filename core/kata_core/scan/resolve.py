"""Resolve a word written on a page to one concept inside a topic (M20).

Order: a remembered choice (D38) wins; several candidate names ask the user which one; otherwise the
word or the name is looked up in the topic; with no hit a private concept is created. A concept the
user ignores is still returned: the caller checks is_ignored and drops it. The topic must be visible
to the user, and a word is only ever resolved inside its own topic (D54).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import psycopg

from kata_core.storage.concept_aliases import add_concept_alias, resolve_concept
from kata_core.storage.concepts import concept_mark_states, create_concept, set_concept_definition
from kata_core.storage.page_scan import get_choice
from kata_core.storage.taxonomy import topic_visible

MIN_CANDIDATES = 2


@dataclass(frozen=True)
class ResolvedItem:
    """The concept a written word stands for. concept_id is None while the user must pick one of
    `candidates`, a list of (concept_id, label)."""

    word: str
    concept_id: int | None
    label: str
    definition: str
    state: str | None
    candidates: list[tuple[int, str]] = field(default_factory=list)


def is_ignored(conn: psycopg.Connection[Any], user_id: int, concept_id: int) -> bool:
    """True when `user_id` ignores concept `concept_id` (concept_ignored)."""
    row = conn.execute(
        "SELECT 1 FROM concept_ignored WHERE user_id = %s AND concept_id = %s",
        (user_id, concept_id),
    ).fetchone()
    return row is not None


def resolve_item(
    conn: psycopg.Connection[Any],
    user_id: int,
    topic_id: int,
    word: str,
    name: str | None = None,
    definition: str = "",
    candidates: list[str] | None = None,
) -> ResolvedItem:
    """Resolve `word` in `topic_id` for `user_id`. `name` is the concept name the page gives the word
    (defaults to `word`); `candidates` with two or more names asks the user to pick one.
    Raises LookupError when the topic is not visible to the user."""
    if not topic_visible(conn, user_id, topic_id):
        raise LookupError(f"topic {topic_id} is not visible to user {user_id}")
    label_name = name or word

    chosen = get_choice(conn, user_id, topic_id, word)
    if chosen is not None:
        return _item(conn, user_id, word, chosen, definition)

    if candidates is not None and len(candidates) >= MIN_CANDIDATES:
        options: list[tuple[int, str]] = []
        for option in candidates:
            option_id = resolve_concept(conn, user_id, topic_id, option)
            if option_id is None:
                option_id = create_concept(conn, topic_id, option, owner_user_id=user_id)
            options.append((option_id, option))
        return ResolvedItem(word=word, concept_id=None, label=word, definition="", state=None, candidates=options)

    hit = resolve_concept(conn, user_id, topic_id, word)
    if hit is not None:
        return _item(conn, user_id, word, hit, definition)

    hit = resolve_concept(conn, user_id, topic_id, label_name)
    if hit is not None:
        if word.lower() != _label(conn, hit).lower():
            try:
                add_concept_alias(conn, hit, word, owner_user_id=user_id)
            except ValueError:
                pass  # the alias is already there
        return _item(conn, user_id, word, hit, definition)

    new_id = create_concept(conn, topic_id, label_name, owner_user_id=user_id)
    return _item(conn, user_id, word, new_id, definition)


def _label(conn: psycopg.Connection[Any], concept_id: int) -> str:
    row = conn.execute("SELECT label FROM concepts WHERE id = %s", (concept_id,)).fetchone()
    if row is None:
        raise LookupError(f"concept {concept_id} does not exist")
    return str(row[0])


def _item(
    conn: psycopg.Connection[Any], user_id: int, word: str, concept_id: int, definition: str
) -> ResolvedItem:
    """Build the result for one concept. A definition is set only on a private concept that has none."""
    row = conn.execute(
        "SELECT label, definition, owner_user_id FROM concepts WHERE id = %s", (concept_id,)
    ).fetchone()
    if row is None:
        raise LookupError(f"concept {concept_id} does not exist")
    label, stored, owner = str(row[0]), str(row[1]), row[2]
    if definition and stored == "" and owner is not None and int(owner) == user_id:
        set_concept_definition(conn, user_id, concept_id, definition)
        stored = definition
    state = concept_mark_states(conn, user_id, [concept_id]).get(concept_id)
    return ResolvedItem(
        word=word,
        concept_id=concept_id,
        label=label,
        definition=stored,
        state=state,
    )
