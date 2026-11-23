"""Taxonomy routes: list visible topics, create a topic, add an alias to a visible topic.

The caller comes from `current_user`; a private topic or alias is owned by the caller.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from kata_core.api.deps import Conn, current_user
from kata_core.auth.service import AuthContext
from kata_core.storage.taxonomy import (
    add_alias,
    ensure_category,
    ensure_topic,
    list_visible_topics,
    topic_visible,
)

router = APIRouter(prefix="/topics")

Caller = Annotated[AuthContext, Depends(current_user)]


class TopicIn(BaseModel):
    category: str = Field(min_length=1)
    label: str = Field(min_length=1)
    private: bool = False


class TopicOut(BaseModel):
    id: int
    category: str
    label: str
    private: bool


class AliasIn(BaseModel):
    alias: str = Field(min_length=1)


class AliasOut(BaseModel):
    id: int
    topic_id: int
    alias: str
    private: bool


@router.get("", response_model=list[TopicOut])
def list_topics_route(ctx: Caller, conn: Conn) -> list[TopicOut]:
    """Shared topics and the caller's own private topics."""
    return [
        TopicOut(id=topic_id, category=cat, label=label, private=private)
        for topic_id, cat, label, private in list_visible_topics(conn, ctx.user_id)
    ]


@router.post("", response_model=TopicOut)
def create_topic(body: TopicIn, ctx: Caller, conn: Conn) -> TopicOut:
    """Create (or find) a topic. private true makes it the caller's own; default is shared."""
    owner = ctx.user_id if body.private else None
    category_id = ensure_category(conn, body.category)
    topic_id = ensure_topic(conn, category_id, body.label, owner)
    return TopicOut(id=topic_id, category=body.category, label=body.label, private=body.private)


@router.post("/{topic_id}/aliases", response_model=AliasOut)
def create_alias(topic_id: int, body: AliasIn, ctx: Caller, conn: Conn) -> AliasOut:
    """Add an alias the caller owns to a topic the caller can see. 404 otherwise."""
    if not topic_visible(conn, ctx.user_id, topic_id):
        raise HTTPException(status_code=404, detail="topic not found")
    alias_id = add_alias(conn, topic_id, body.alias, ctx.user_id)
    return AliasOut(id=alias_id, topic_id=topic_id, alias=body.alias, private=True)
