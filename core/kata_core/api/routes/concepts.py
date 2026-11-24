"""Concept routes: concepts under a visible topic, and the caller's own marks on them.

The user id always comes from `current_user`, never from the body or the path.
A concept made through this API belongs to its creator, so other users never see it.
Aliases, definition, the ignored list and hard delete act on concepts the caller can see.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from kata_core.api.deps import Conn, current_user
from kata_core.auth.service import AuthContext
from kata_core.storage.concept_aliases import add_concept_alias, list_concept_aliases
from kata_core.storage.concepts import (
    clear_concept_mark,
    concept_visible,
    create_concept,
    delete_concept,
    get_concept_mark_detail,
    ignore_concept,
    list_concept_marks_detail,
    list_ignored,
    set_concept_definition,
    set_concept_mark,
    unignore_concept,
)
from kata_core.storage.taxonomy import topic_visible

router = APIRouter(prefix="/concepts")

Caller = Annotated[AuthContext, Depends(current_user)]


class ConceptIn(BaseModel):
    topic_id: int
    label: str


class ConceptOut(BaseModel):
    id: int
    topic_id: int
    label: str
    definition: str


class ConceptAliasIn(BaseModel):
    alias: str = Field(min_length=1, max_length=200)


class ConceptAliasOut(BaseModel):
    id: int
    concept_id: int
    alias: str
    private: bool


class ConceptDefinitionIn(BaseModel):
    definition: str = Field(max_length=2000)


class IgnoredConceptOut(BaseModel):
    concept_id: int
    label: str


class ConceptMarkIn(BaseModel):
    state: Literal["known", "learning", "new"]
    evidence: str = ""


class ConceptMarkOut(BaseModel):
    concept_id: int
    label: str
    state: str
    evidence: str
    created_at: datetime
    updated_at: datetime


@router.post("", response_model=ConceptOut)
def create_concept_route(body: ConceptIn, ctx: Caller, conn: Conn) -> ConceptOut:
    """Add a concept under a topic the caller can see. 404 otherwise."""
    if not topic_visible(conn, ctx.user_id, body.topic_id):
        raise HTTPException(status_code=404, detail="topic not found")
    concept_id = create_concept(conn, body.topic_id, body.label, ctx.user_id)
    return ConceptOut(id=concept_id, topic_id=body.topic_id, label=body.label, definition="")


@router.get("/marks", response_model=list[ConceptMarkOut])
def list_concept_marks_route(ctx: Caller, conn: Conn) -> list[ConceptMarkOut]:
    """Every concept mark of the caller, ordered by concept id. Other users' marks are never listed."""
    return [
        ConceptMarkOut(
            concept_id=concept_id,
            label=label,
            state=state,
            evidence=evidence,
            created_at=created_at,
            updated_at=updated_at,
        )
        for concept_id, label, state, evidence, created_at, updated_at in list_concept_marks_detail(
            conn, ctx.user_id
        )
    ]


@router.put("/{concept_id}/mark", response_model=ConceptMarkOut)
def put_concept_mark(
    concept_id: int, body: ConceptMarkIn, ctx: Caller, conn: Conn
) -> ConceptMarkOut:
    """Set the caller's mark on a visible concept. 404 when the concept is not visible to the caller."""
    try:
        set_concept_mark(conn, ctx.user_id, concept_id, body.state, body.evidence)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="concept not found") from exc
    row = get_concept_mark_detail(conn, ctx.user_id, concept_id)
    if row is None:  # unreachable after a successful set; kept for the type
        raise HTTPException(status_code=404, detail="concept not found")
    mark_id, label, state, evidence, created_at, updated_at = row
    return ConceptMarkOut(
        concept_id=mark_id,
        label=label,
        state=state,
        evidence=evidence,
        created_at=created_at,
        updated_at=updated_at,
    )


@router.delete("/{concept_id}/mark", status_code=204)
def delete_concept_mark(concept_id: int, ctx: Caller, conn: Conn) -> Response:
    """Remove the caller's mark on a concept. 404 when the caller has no such mark."""
    if not clear_concept_mark(conn, ctx.user_id, concept_id):
        raise HTTPException(status_code=404, detail="mark not found")
    return Response(status_code=204)


def _require_concept(conn: Conn, user_id: int, concept_id: int) -> None:
    """404 when concept `concept_id` is not visible to `user_id`."""
    if not concept_visible(conn, user_id, concept_id):
        raise HTTPException(status_code=404, detail="concept not found")


@router.post("/{concept_id}/aliases", response_model=ConceptAliasOut)
def create_concept_alias_route(
    concept_id: int, body: ConceptAliasIn, ctx: Caller, conn: Conn
) -> ConceptAliasOut:
    """Add a private alias the caller owns to a visible concept. 404 otherwise, 409 when the alias exists."""
    _require_concept(conn, ctx.user_id, concept_id)
    try:
        alias_id = add_concept_alias(conn, concept_id, body.alias, ctx.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="alias already exists") from exc
    return ConceptAliasOut(id=alias_id, concept_id=concept_id, alias=body.alias, private=True)


@router.get("/{concept_id}/aliases", response_model=list[ConceptAliasOut])
def list_concept_aliases_route(concept_id: int, ctx: Caller, conn: Conn) -> list[ConceptAliasOut]:
    """Shared aliases and the caller's own aliases of a visible concept. 404 otherwise."""
    _require_concept(conn, ctx.user_id, concept_id)
    return [
        ConceptAliasOut(id=alias_id, concept_id=concept_id, alias=alias, private=owner is not None)
        for alias_id, alias, owner in list_concept_aliases(conn, ctx.user_id, concept_id)
    ]


@router.put("/{concept_id}/definition", status_code=204)
def put_concept_definition(
    concept_id: int, body: ConceptDefinitionIn, ctx: Caller, conn: Conn
) -> Response:
    """Set the definition of a concept the caller owns. 404 when not visible, 403 when the concept is shared."""
    _require_concept(conn, ctx.user_id, concept_id)
    try:
        set_concept_definition(conn, ctx.user_id, concept_id, body.definition)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="shared concept cannot be edited") from exc
    return Response(status_code=204)


@router.get("/ignored", response_model=list[IgnoredConceptOut])
def list_ignored_route(ctx: Caller, conn: Conn) -> list[IgnoredConceptOut]:
    """Concepts the caller ignores, ordered by concept id."""
    return [
        IgnoredConceptOut(concept_id=concept_id, label=label)
        for concept_id, label in list_ignored(conn, ctx.user_id)
    ]


@router.put("/{concept_id}/ignore", status_code=204)
def put_concept_ignore(concept_id: int, ctx: Caller, conn: Conn) -> Response:
    """Hide a visible concept from the caller's lists. Its marks stay. 404 when not visible."""
    _require_concept(conn, ctx.user_id, concept_id)
    ignore_concept(conn, ctx.user_id, concept_id)
    return Response(status_code=204)


@router.delete("/{concept_id}/ignore", status_code=204)
def delete_concept_ignore(concept_id: int, ctx: Caller, conn: Conn) -> Response:
    """Show a concept in the caller's lists again. 404 when the caller does not ignore it."""
    if not unignore_concept(conn, ctx.user_id, concept_id):
        raise HTTPException(status_code=404, detail="ignored concept not found")
    return Response(status_code=204)


@router.delete("/{concept_id}", status_code=204)
def delete_concept_route(concept_id: int, ctx: Caller, conn: Conn) -> Response:
    """Hard-delete a concept the caller owns, with its marks, aliases and ignore rows.
    404 when not visible, 403 when the concept is shared."""
    _require_concept(conn, ctx.user_id, concept_id)
    try:
        delete_concept(conn, ctx.user_id, concept_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="shared concept cannot be deleted") from exc
    return Response(status_code=204)
