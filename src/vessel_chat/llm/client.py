"""Giao diện LLM/embedding và bản cài đặt OpenAI (hoặc endpoint tương thích OpenAI).

ChatService chỉ phụ thuộc vào Protocol ở đây → test dùng bản giả, đổi nhà cung cấp chỉ cần
viết lớp mới cùng giao diện.
"""

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal, Protocol

from openai import AsyncOpenAI

from ..config import Settings


@dataclass
class ToolCallReq:
    id: str
    name: str
    arguments: str  # JSON


@dataclass
class LLMEvent:
    type: Literal["text", "tool_calls", "done"]
    text: str = ""
    tool_calls: list[ToolCallReq] = field(default_factory=list)
    usage: dict | None = None


class LLMClient(Protocol):
    def stream_chat(self, messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[LLMEvent]: ...

    async def complete(self, messages: list[dict], max_tokens: int | None = None) -> str: ...


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


def _client(settings: Settings) -> AsyncOpenAI:
    settings.require("openai_api_key")
    # SDK tự đọc OPENAI_BASE_URL từ môi trường; biến rỗng (vd. từ env_file) sẽ làm hỏng URL → bỏ đi
    if not os.environ.get("OPENAI_BASE_URL", "x").strip():
        os.environ.pop("OPENAI_BASE_URL")
    return AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
        timeout=settings.llm_timeout_seconds,
        max_retries=2,
    )


class OpenAILLM:
    def __init__(self, settings: Settings):
        settings.require("llm_model")
        self.settings = settings
        self.client = _client(settings)

    async def stream_chat(self, messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[LLMEvent]:
        kwargs = {}
        if tools:
            kwargs.update(tools=tools, tool_choice="auto", parallel_tool_calls=True)
        stream = await self.client.chat.completions.create(
            model=self.settings.llm_model,
            messages=messages,
            temperature=self.settings.llm_temperature,
            stream=True,
            stream_options={"include_usage": True},
            **kwargs,
        )
        # Tool call đến theo từng mảnh (theo index) → gom lại, phát một lần khi stream kết thúc
        pending: dict[int, dict] = {}
        usage = None
        async for chunk in stream:
            if chunk.usage:
                usage = chunk.usage.model_dump()
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                yield LLMEvent(type="text", text=delta.content)
            for tc in delta.tool_calls or []:
                slot = pending.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                if tc.id:
                    slot["id"] = tc.id
                if tc.function and tc.function.name:
                    slot["name"] += tc.function.name
                if tc.function and tc.function.arguments:
                    slot["arguments"] += tc.function.arguments
        if pending:
            yield LLMEvent(
                type="tool_calls",
                tool_calls=[ToolCallReq(**pending[i]) for i in sorted(pending)],
            )
        yield LLMEvent(type="done", usage=usage)

    async def complete(self, messages: list[dict], max_tokens: int | None = None) -> str:
        resp = await self.client.chat.completions.create(
            model=self.settings.llm_model,
            messages=messages,
            temperature=0,
            max_tokens=max_tokens or self.settings.summary_max_tokens,
        )
        return resp.choices[0].message.content or ""


class OpenAIEmbedder:
    def __init__(self, settings: Settings):
        settings.require("embedding_model")
        self.settings = settings
        self.client = _client(settings)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self.client.embeddings.create(
            model=self.settings.embedding_model,
            input=texts,
            dimensions=self.settings.embedding_dim,
        )
        return [d.embedding for d in resp.data]
