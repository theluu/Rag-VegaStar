"""Giao diện LLM/embedding và bản cài đặt OpenAI (hoặc endpoint tương thích OpenAI).

ChatService chỉ phụ thuộc vào Protocol ở đây → test dùng bản giả, đổi nhà cung cấp chỉ cần
viết lớp mới cùng giao diện.
"""

import hashlib
import logging
import os
import struct
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal, Protocol

from openai import AsyncOpenAI

from ..config import Settings
from ..observability import LLM_PROVIDER_EVENTS

log = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    """Không có nhà cung cấp LLM nào dùng được (chưa cấu hình hoặc tất cả đều lỗi)."""


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
    def stream_chat(
        self, messages: list[dict], tools: list[dict] | None = None, tool_choice: str = "auto"
    ) -> AsyncIterator[LLMEvent]: ...

    async def complete(self, messages: list[dict], max_tokens: int | None = None) -> str: ...


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


def _client(settings: Settings, api_key: str | None = None, base_url: str | None = None,
            timeout: float | None = None) -> AsyncOpenAI:
    key = api_key or settings.openai_api_key
    if not key:
        raise LLMUnavailable("Chưa cấu hình OPENAI_API_KEY")
    # SDK tự đọc OPENAI_BASE_URL từ môi trường; biến rỗng (vd. từ env_file) sẽ làm hỏng URL → bỏ đi
    if not os.environ.get("OPENAI_BASE_URL", "x").strip():
        os.environ.pop("OPENAI_BASE_URL")
    return AsyncOpenAI(
        api_key=key,
        base_url=(base_url if base_url is not None else settings.openai_base_url) or None,
        timeout=timeout or settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,  # SDK tự lùi theo cấp số nhân, tôn trọng Retry-After
    )


class OpenAILLM:
    def __init__(self, settings: Settings, api_key: str | None = None, base_url: str | None = None,
                 model: str | None = None, name: str = "primary"):
        self.settings = settings
        self.model = model or settings.llm_model
        self.name = name
        if not self.model:
            raise LLMUnavailable("Chưa cấu hình LLM_MODEL")
        self.client = _client(settings, api_key, base_url)

    async def stream_chat(
        self, messages: list[dict], tools: list[dict] | None = None, tool_choice: str = "auto"
    ) -> AsyncIterator[LLMEvent]:
        kwargs = {}
        if tools:
            kwargs.update(tools=tools, tool_choice=tool_choice, parallel_tool_calls=True)
        stream = await self.client.chat.completions.create(
            model=self.model,
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
            model=self.model,
            messages=messages,
            temperature=0,
            max_tokens=max_tokens or self.settings.summary_max_tokens,
        )
        return resp.choices[0].message.content or ""


class FallbackLLM:
    """Thử nhà cung cấp chính, lỗi thì chuyển sang nhà cung cấp dự phòng.

    Chỉ chuyển khi chưa phát ra chữ nào của lượt đó, để câu trả lời không bị ghép từ hai model.
    """

    def __init__(self, providers: list[LLMClient]):
        if not providers:
            raise LLMUnavailable("Danh sách nhà cung cấp LLM rỗng")
        self.providers = providers

    @property
    def model(self) -> str:
        return getattr(self.providers[0], "model", "")

    async def stream_chat(
        self, messages: list[dict], tools: list[dict] | None = None, tool_choice: str = "auto"
    ) -> AsyncIterator[LLMEvent]:
        last: Exception | None = None
        for index, provider in enumerate(self.providers):
            produced = False
            try:
                async for event in provider.stream_chat(messages, tools, tool_choice):
                    produced = produced or event.type != "done"
                    yield event
                if index:
                    LLM_PROVIDER_EVENTS.labels("fallback_used").inc()
                return
            except Exception as exc:  # noqa: BLE001 — mọi lỗi nhà cung cấp đều thử bản dự phòng
                last = exc
                if produced or index == len(self.providers) - 1:
                    raise
                LLM_PROVIDER_EVENTS.labels("failover").inc()
                log.warning("Nhà cung cấp LLM #%d lỗi (%s), chuyển sang bản dự phòng", index, type(exc).__name__)
        raise last or LLMUnavailable("Không nhà cung cấp nào trả lời")

    async def complete(self, messages: list[dict], max_tokens: int | None = None) -> str:
        last: Exception | None = None
        for index, provider in enumerate(self.providers):
            try:
                return await provider.complete(messages, max_tokens)
            except Exception as exc:  # noqa: BLE001
                last = exc
                if index == len(self.providers) - 1:
                    raise
                LLM_PROVIDER_EVENTS.labels("failover").inc()
        raise last or LLMUnavailable("Không nhà cung cấp nào trả lời")


class NullLLM:
    """Chế độ không có AI: mọi yêu cầu sinh văn bản đều báo không khả dụng."""

    model = ""

    async def stream_chat(
        self, messages: list[dict], tools: list[dict] | None = None, tool_choice: str = "auto"
    ) -> AsyncIterator[LLMEvent]:
        raise LLMUnavailable("Chưa cấu hình nhà cung cấp LLM")
        yield  # pragma: no cover — giữ hàm là async generator

    async def complete(self, messages: list[dict], max_tokens: int | None = None) -> str:
        raise LLMUnavailable("Chưa cấu hình nhà cung cấp LLM")


class LocalHashEmbedder:
    """Embedding cục bộ, tất định, không gọi mạng — chỉ dùng khi không có API key.

    Không có chất lượng ngữ nghĩa: kho tri thức vẫn tìm được bằng full-text, còn truy xuất ký ức
    theo vector gần như vô hiệu. Mục đích là hệ thống vẫn chạy khi không có AI.
    """

    def __init__(self, dim: int):
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dim
            for token in set(fold_tokens(text)):
                digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
                slot = struct.unpack("<Q", digest)[0] % self.dim
                vec[slot] += 1.0
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            out.append([v / norm for v in vec])
        return out


def fold_tokens(text: str) -> list[str]:
    return [t for t in "".join(c if c.isalnum() else " " for c in text.lower()).split() if t]


class OpenAIEmbedder:
    def __init__(self, settings: Settings):
        settings.require("embedding_model", "openai_api_key")
        self.settings = settings
        self.client = _client(settings)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self.client.embeddings.create(
            model=self.settings.embedding_model,
            input=texts,
            dimensions=self.settings.embedding_dim,
        )
        return [d.embedding for d in resp.data]


class OpenAIModerator:
    """Kiểm duyệt nội dung đầu vào bằng OpenAI Moderation API (miễn phí)."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = _client(settings)

    async def moderate(self, text: str) -> tuple[bool, list[str]]:
        resp = await self.client.moderations.create(model=self.settings.guardrail_moderation_model, input=text)
        result = resp.results[0]
        categories = [name for name, hit in result.categories.model_dump().items() if hit]
        return bool(result.flagged), categories
