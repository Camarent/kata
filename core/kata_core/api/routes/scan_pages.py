"""Scan routes: the caller's cached page classification and remembered Which-one choices.

The user id always comes from `current_user`, never from the body or the query.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from kata_core.api.deps import Conn, current_user
from kata_core.auth.service import AuthContext
from kata_core.storage.concepts import concept_topic_id, concept_visible
from kata_core.storage.page_scan import get_classification, remember_choice
from kata_core.storage.taxonomy import list_visible_topics, topic_visible

router = APIRouter(prefix="/scan")

Caller = Annotated[AuthContext, Depends(current_user)]


class CandidateOut(BaseModel):
    topic_id: int
    area: str
    topic: str


class ClassificationOut(BaseModel):
    topic_id: int
    area: str
    topic: str
    candidates: list[CandidateOut]


class ChoiceIn(BaseModel):
    topic_id: int
    word: str = Field(min_length=1, max_length=200)
    concept_id: int


@router.get("/classification", response_model=ClassificationOut)
def get_page_classification(page_key: str, ctx: Caller, conn: Conn) -> ClassificationOut:
    """The caller's cached classification of a page. 404 when the caller has none for it.

    Cached candidates are matched against the caller's visible topics; a candidate with no visible topic is dropped.
    """
    cached = get_classification(conn, ctx.user_id, page_key)
    if cached is None:
        raise HTTPException(status_code=404, detail="classification not found")
    topic_id, raw_candidates = cached
    visible = list_visible_topics(conn, ctx.user_id)
    by_name: dict[tuple[str, str], tuple[int, str, str]] = {}
    for vid, area, label, private in visible:
        key = (area.lower(), label.lower())
        if key not in by_name or private:  # the caller's own topic wins over a shared one with the same name
            by_name[key] = (vid, area, label)
    by_id = {vid: (area, label) for vid, area, label, _ in visible}
    if topic_id not in by_id:
        raise HTTPException(status_code=404, detail="classification not found")
    area, label = by_id[topic_id]
    candidates: list[CandidateOut] = []
    for raw in raw_candidates:
        match = by_name.get((str(raw["area"]).lower(), str(raw["topic"]).lower()))
        if match is not None:
            candidates.append(CandidateOut(topic_id=match[0], area=match[1], topic=match[2]))
    return ClassificationOut(topic_id=topic_id, area=area, topic=label, candidates=candidates)


@router.post("/choice", status_code=204)
def post_choice(body: ChoiceIn, ctx: Caller, conn: Conn) -> Response:
    """Remember the concept the caller picked for a word in a visible topic.

    404 when the topic or concept is not visible to the caller; 422 when the concept belongs to another topic.
    """
    if not topic_visible(conn, ctx.user_id, body.topic_id):
        raise HTTPException(status_code=404, detail="topic not found")
    if not concept_visible(conn, ctx.user_id, body.concept_id):
        raise HTTPException(status_code=404, detail="concept not found")
    if concept_topic_id(conn, body.concept_id) != body.topic_id:
        raise HTTPException(status_code=422, detail="concept is not in this topic")
    remember_choice(conn, ctx.user_id, body.topic_id, body.word, body.concept_id)
    return Response(status_code=204)
