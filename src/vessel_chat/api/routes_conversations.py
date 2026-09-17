from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from ..chat.service import DEFAULT_TITLE
from ..repositories import conversations as conv_repo
from ..repositories import map_data as map_repo
from .deps import get_pool

router = APIRouter(prefix="/conversations", tags=["conversations"])


class CreateConversation(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationDetail(ConversationOut):
    summary: str
    summary_upto_turn: int
    focus_state: dict[str, Any]


class MessageOut(BaseModel):
    id: int
    turn_no: int
    role: str
    content: str
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    meta: dict | None = None
    created_at: datetime


class MapDataRef(BaseModel):
    id: str
    kind: str
    summary: dict
    bbox: list[float] | None
    created_at: datetime


async def _require(conn: asyncpg.Connection, conv_id: UUID) -> dict:
    conv = await conv_repo.get_conversation(conn, str(conv_id))
    if conv is None:
        raise HTTPException(status_code=404, detail="Hội thoại không tồn tại")
    return conv


@router.post("", status_code=201, response_model=ConversationOut)
async def create_conversation(body: CreateConversation | None = None, pool: asyncpg.Pool = Depends(get_pool)):
    title = (body.title if body and body.title else None) or DEFAULT_TITLE
    async with pool.acquire() as conn:
        return await conv_repo.create_conversation(conn, title)


@router.get("", response_model=list[ConversationOut])
async def list_conversations(pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        return await conv_repo.list_conversations(conn)


@router.get("/{conv_id}", response_model=ConversationDetail)
async def get_conversation(conv_id: UUID, pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        return await _require(conn, conv_id)


@router.get("/{conv_id}/messages", response_model=list[MessageOut])
async def list_messages(conv_id: UUID, pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        await _require(conn, conv_id)
        return await conv_repo.list_messages(conn, str(conv_id))


@router.get("/{conv_id}/map-data", response_model=list[MapDataRef])
async def list_map_data(conv_id: UUID, pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        await _require(conn, conv_id)
        items = await map_repo.list_map_data(conn, str(conv_id))
    for item in items:
        item["summary"] = {k: v for k, v in item["summary"].items() if k != "vessels"}
    return items


@router.delete("/{conv_id}", status_code=204)
async def delete_conversation(conv_id: UUID, pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        if not await conv_repo.delete_conversation(conn, str(conv_id)):
            raise HTTPException(status_code=404, detail="Hội thoại không tồn tại")
    return Response(status_code=204)
