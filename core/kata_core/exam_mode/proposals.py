"""Exam-mode proposals: group the weak analysed signals of a closed session, then confirm or dismiss.

A proposal is a concept the practice exam showed as likely wrong or unsure. Its key is
`concept:<id>` for an existing concept, or `name:<topic_id or 0>:<lower name>` for a name that
matched nothing. Proposals are computed at read time from the stored signals; a key with a stored
decision shows that decision. Confirm marks the concept learning (creating it first when it is still
missing). Confirm and dismiss write one decision row per key: the first answer wins and a repeat call
returns it without creating anything.

Nothing here reads the clock. The session must be closed before its proposals are listed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg

from kata_core.storage.concept_aliases import resolve_concept
from kata_core.storage.concepts import concept_visible, create_concept, set_concept_mark
from kata_core.storage.exam_mode import (
    StoredDecision,
    get_decision,
    get_session,
    list_signals,
    lock_session,
    put_decision,
)
from kata_core.storage.taxonomy import topic_visible

WEAK_OUTCOMES = ("likely_wrong", "unsure")
ANALYSED = "analysed"
CONFIRMED = "confirmed"
DISMISSED = "dismissed"
LEARNING = "learning"
MARK_SOURCE = "user"


class ProposalError(ValueError):
    """The proposal cannot be confirmed as asked: unknown key, or no visible topic for a new concept."""


class SessionNotFoundError(LookupError):
    """The session does not exist or belongs to another user."""


class SessionOpenError(RuntimeError):
    """The session is still open; its proposals are not shown until it ends."""


@dataclass(frozen=True)
class Proposal:
    key: str
    concept_id: int | None
    topic_id: int | None
    name: str | None
    decision: StoredDecision | None


def _name_key(topic_id: int | None, name: str) -> str:
    return f"name:{topic_id or 0}:{name.lower()}"


def _closed_session(conn: psycopg.Connection[Any], user_id: int, session_id: int) -> None:
    session = get_session(conn, user_id, session_id)
    if session is None:
        raise SessionNotFoundError(f"exam session {session_id} not found")
    if session.ended_at is None:
        raise SessionOpenError(f"exam session {session_id} is still open")


def _candidates(conn: psycopg.Connection[Any], session_id: int) -> dict[str, Proposal]:
    """Weak analysed signals grouped by key, in position order. Decisions are not read here."""
    found: dict[str, Proposal] = {}
    for signal in list_signals(conn, session_id):
        if signal.status != ANALYSED or signal.outcome not in WEAK_OUTCOMES:
            continue
        for concept_id in signal.concept_ids:
            key = f"concept:{concept_id}"
            found.setdefault(key, Proposal(key, concept_id, signal.topic_id, None, None))
        for name in signal.proposed_names:
            key = _name_key(signal.topic_id, name)
            found.setdefault(key, Proposal(key, None, signal.topic_id, name, None))
    return found


def list_proposals(conn: psycopg.Connection[Any], user_id: int, session_id: int) -> list[Proposal]:
    """The session's proposals with their stored decision. Raises while the session is open."""
    _closed_session(conn, user_id, session_id)
    proposals: list[Proposal] = []
    for proposal in _candidates(conn, session_id).values():
        stored = get_decision(conn, session_id, proposal.key)
        proposals.append(
            Proposal(proposal.key, proposal.concept_id, proposal.topic_id, proposal.name, stored)
        )
    return proposals


def _find(conn: psycopg.Connection[Any], session_id: int, key: str) -> Proposal:
    proposal = _candidates(conn, session_id).get(key)
    if proposal is None:
        raise ProposalError(f"no proposal {key!r} in exam session {session_id}")
    return proposal


def _learn(
    conn: psycopg.Connection[Any],
    user_id: int,
    session_id: int,
    proposal: Proposal,
    topic_id: int | None,
) -> int:
    """Mark the proposal's concept learning, creating it first when it is a name still missing."""
    if proposal.concept_id is not None:
        concept_id = proposal.concept_id
        if not concept_visible(conn, user_id, concept_id):
            raise ProposalError(f"concept {concept_id} is not visible to user {user_id}")
    else:
        topic = proposal.topic_id if proposal.topic_id is not None else topic_id
        if topic is None:
            raise ProposalError(f"proposal {proposal.key!r} needs a topic_id")
        if not topic_visible(conn, user_id, topic):
            raise ProposalError(f"topic {topic} is not visible to user {user_id}")
        name = proposal.name or ""
        # Look again: the concept may have been added since the list was shown.
        found = resolve_concept(conn, user_id, topic, name)
        concept_id = (
            found if found is not None else create_concept(conn, topic, name, owner_user_id=user_id)
        )
    set_concept_mark(
        conn,
        user_id,
        concept_id,
        state=LEARNING,
        evidence=f"exam mode session {session_id}",
        source=MARK_SOURCE,
    )
    return concept_id


def _answer(
    conn: psycopg.Connection[Any],
    user_id: int,
    session_id: int,
    key: str,
    topic_id: int | None,
    decision: str,
) -> StoredDecision:
    # One transaction under the session lock: a concurrent answer waits, then sees the stored decision.
    with conn.transaction():
        lock_session(conn, user_id, session_id)
        _closed_session(conn, user_id, session_id)
        stored = get_decision(conn, session_id, key)
        if stored is not None:
            return stored
        proposal = _find(conn, session_id, key)
        concept_id: int | None = None
        if decision == CONFIRMED:
            concept_id = _learn(conn, user_id, session_id, proposal, topic_id)
        return put_decision(conn, session_id, key, decision, concept_id)


def confirm(
    conn: psycopg.Connection[Any],
    user_id: int,
    session_id: int,
    key: str,
    topic_id: int | None = None,
) -> StoredDecision:
    """Mark the proposal's concept learning. Returns the stored decision; a repeat call changes nothing."""
    return _answer(conn, user_id, session_id, key, topic_id, CONFIRMED)


def dismiss(
    conn: psycopg.Connection[Any],
    user_id: int,
    session_id: int,
    key: str,
    topic_id: int | None = None,
) -> StoredDecision:
    """Record that the owner dropped the proposal. Returns the stored decision; a repeat call changes nothing."""
    return _answer(conn, user_id, session_id, key, topic_id, DISMISSED)
