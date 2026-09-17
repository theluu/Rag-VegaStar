from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ..chat.service import ChatService
from ..repositories import conversations as conv_repo
from .deps import get_pool, get_service

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


@router.post(
    "/conversations/{conv_id}/chat",
    response_class=EventSourceResponse,
    responses={200: {"content": {"text/event-stream": {}},
                     "description": "Server-Sent Events: token, tool_call, tool_result, data, memory, error, done"}},
)
async def chat(
    conv_id: UUID,
    body: ChatRequest,
    pool: asyncpg.Pool = Depends(get_pool),
    service: ChatService = Depends(get_service),
):
    async with pool.acquire() as conn:
        if await conv_repo.get_conversation(conn, str(conv_id)) is None:
            raise HTTPException(status_code=404, detail="Hội thoại không tồn tại")
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Tin nhắn rỗng")

    async def stream():
        async for event in service.run_turn(str(conv_id), message):
            yield event.to_sse()

    return EventSourceResponse(stream(), ping=15, headers={"X-Accel-Buffering": "no"})
