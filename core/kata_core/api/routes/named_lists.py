"""Named concept lists (M21): create, list, rename and delete a user's lists; add and remove concepts;
add a whole visible topic; find which of the user's lists hold a concept; and queue a course from a
list (the list is kept).

The user id always comes from `current_user`, never from the body or the path. A list the caller
does not own gives 404, and so does a concept or topic the caller cannot see.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from kata_core.api.deps import Conn, current_user, get_cfg, require_feature
from kata_core.api.routes.courses import CourseAcceptedOut, _course_out, queue_course
from kata_core.auth.service import AuthContext
from kata_core.config import Config
from kata_core.lists.store import (
    ConceptList,
    DuplicateConceptList,
    add_concepts,
    add_topic,
    create_list,
    delete_list,
    list_all,
    lists_of_concept,
    owns_list,
    remove_concept,
    rename_list,
)
from kata_core.storage.concepts import concept_visible
from kata_core.storage.taxonomy import topic_visible
from kata_core.trainer.rungs import START_RUNG_MAX, START_RUNG_MIN

router = APIRouter(prefix="/v1/lists")

Caller = Annotated[AuthContext, Depends(current_user)]
Cfg = Annotated[Config, Depends(get_cfg)]


class ListNameIn(BaseModel):
    name: str


class ListOut(BaseModel):
    id: int
    name: str
    item_count: int


class ConceptIdsIn(BaseModel):
    concept_ids: list[int] = Field(min_length=1)


class AddedOut(BaseModel):
    added: int


class CourseFromListIn(BaseModel):
    title: str
    learning_rung: int | None = Field(default=None, ge=START_RUNG_MIN, le=START_RUNG_MAX)


def _out(concept_list: ConceptList) -> ListOut:
    return ListOut(id=concept_list.id, name=concept_list.name, item_count=len(concept_list.concept_ids))


def _not_found_list() -> HTTPException:
    return HTTPException(status_code=404, detail="list not found")


@router.post("", response_model=ListOut)
def create_list_route(body: ListNameIn, ctx: Caller, conn: Conn) -> ListOut:
    """Create an empty list. 409 when the user already has a list with the same name; 422 when blank."""
    try:
        list_id = create_list(conn, ctx.user_id, body.name)
    except DuplicateConceptList as exc:
        raise HTTPException(status_code=409, detail="list name already taken") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ListOut(id=list_id, name=" ".join(body.name.split()), item_count=0)


@router.get("", response_model=list[ListOut])
def list_all_route(ctx: Caller, conn: Conn) -> list[ListOut]:
    """The caller's lists in name order, each with its item count."""
    return [_out(concept_list) for concept_list in list_all(conn, ctx.user_id)]


@router.get("/concept/{concept_id}", response_model=list[ListOut])
def lists_of_concept_route(concept_id: int, ctx: Caller, conn: Conn) -> list[ListOut]:
    """The caller's lists that hold `concept_id`. 404 when the concept is not visible to the caller."""
    if not concept_visible(conn, ctx.user_id, concept_id):
        raise HTTPException(status_code=404, detail="concept not found")
    return [_out(concept_list) for concept_list in lists_of_concept(conn, ctx.user_id, concept_id)]


@router.patch("/{list_id}", response_model=ListOut)
def rename_list_route(list_id: int, body: ListNameIn, ctx: Caller, conn: Conn) -> ListOut:
    """Rename the caller's list. 404 when not owned; 409 when the new name is taken; 422 when blank."""
    try:
        renamed = rename_list(conn, ctx.user_id, list_id, body.name)
    except DuplicateConceptList as exc:
        raise HTTPException(status_code=409, detail="list name already taken") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not renamed:
        raise _not_found_list()
    current = next(c for c in list_all(conn, ctx.user_id) if c.id == list_id)
    return _out(current)


@router.delete("/{list_id}", status_code=204)
def delete_list_route(list_id: int, ctx: Caller, conn: Conn) -> Response:
    """Delete the caller's list and its items. Courses made from it are kept. 404 when not owned."""
    if not delete_list(conn, ctx.user_id, list_id):
        raise _not_found_list()
    return Response(status_code=204)


@router.post("/{list_id}/concepts", response_model=AddedOut)
def add_concepts_route(list_id: int, body: ConceptIdsIn, ctx: Caller, conn: Conn) -> AddedOut:
    """Add concepts to the caller's list. 404 when the list is not owned; 422 when any concept is
    unknown or not visible to the caller (nothing is added then). Re-adding is not an error."""
    if not owns_list(conn, ctx.user_id, list_id):
        raise _not_found_list()
    for concept_id in body.concept_ids:
        if not concept_visible(conn, ctx.user_id, concept_id):
            raise HTTPException(status_code=422, detail=f"concept {concept_id} is unknown or not visible")
    return AddedOut(added=add_concepts(conn, ctx.user_id, list_id, body.concept_ids))


@router.post("/{list_id}/topics/{topic_id}", response_model=AddedOut)
def add_topic_route(list_id: int, topic_id: int, ctx: Caller, conn: Conn) -> AddedOut:
    """Add every concept of a visible topic to the caller's list. 404 when the list is not owned or
    the topic is not visible to the caller."""
    if not owns_list(conn, ctx.user_id, list_id):
        raise _not_found_list()
    if not topic_visible(conn, ctx.user_id, topic_id):
        raise HTTPException(status_code=404, detail="topic not found")
    return AddedOut(added=add_topic(conn, ctx.user_id, list_id, topic_id))


@router.post(
    "/{list_id}/course",
    status_code=202,
    response_model=CourseAcceptedOut,
    dependencies=[Depends(require_feature("trainer"))],
)
def course_from_list_route(
    list_id: int, body: CourseFromListIn, ctx: Caller, conn: Conn, cfg: Cfg
) -> CourseAcceptedOut:
    """Queue a course for the concepts of the caller's list. The list is kept. 404 when the list is not
    owned; 422 when it has no concepts, a concept is not visible, or the title is empty. Other course
    errors (409) are those of `POST /v1/courses`."""
    if not owns_list(conn, ctx.user_id, list_id):
        raise _not_found_list()
    concept_list = next(c for c in list_all(conn, ctx.user_id) if c.id == list_id)
    if not concept_list.concept_ids:
        raise HTTPException(status_code=422, detail="list has no concepts")
    for concept_id in concept_list.concept_ids:
        if not concept_visible(conn, ctx.user_id, concept_id):
            raise HTTPException(status_code=422, detail=f"concept {concept_id} is unknown or not visible")
    course, job_id = queue_course(
        conn, ctx.user_id, body.title, concept_list.concept_ids, body.learning_rung, cfg
    )
    return CourseAcceptedOut(**_course_out(course).model_dump(), job_id=job_id)


@router.delete("/{list_id}/concepts/{concept_id}", status_code=204)
def remove_concept_route(list_id: int, concept_id: int, ctx: Caller, conn: Conn) -> Response:
    """Remove a concept from the caller's list. 404 when the list is not owned or the concept is not
    in it."""
    if not remove_concept(conn, ctx.user_id, list_id, concept_id):
        raise HTTPException(status_code=404, detail="concept not in list")
    return Response(status_code=204)
