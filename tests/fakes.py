"""LLM và embedding giả, xác định, để test không gọi API thật."""

import asyncio
import hashlib
import json
import math
import re
from typing import Any

from vessel_chat.llm.client import LLMEvent, ToolCallReq


class HashEmbedder:
    """Túi từ băm vào `dim` chiều rồi chuẩn hoá: câu có chung từ khoá → cosine cao."""

    def __init__(self, dim: int):
        self.dim = dim
        self.calls = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        out = []
        for t in texts:
            v = [0.0] * self.dim
            for tok in re.findall(r"\w[\w-]*", t.lower()):
                v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dim] += 1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out


class Step:
    """Một lần gọi stream_chat: text (chia nhỏ thành nhiều token) hoặc tool call, hoặc ném lỗi."""

    def __init__(self, text: str | None = None, tool_calls: list[tuple[str, dict]] | None = None,
                 error: Exception | None = None, delay: float = 0.0):
        self.text, self.tool_calls, self.error, self.delay = text, tool_calls, error, delay


class ScriptedLLM:
    """Trả lời theo kịch bản. Có thể chọn kịch bản theo nội dung câu hỏi (router)."""

    def __init__(self, steps: list[Step] | None = None, router=None):
        self.steps = list(steps or [])
        self.router = router  # fn(messages) -> list[Step] khi hết steps
        self.requests: list[list[dict]] = []
        self.summaries: list[str] = []
        self.tool_choices: list[str | None] = []
        self._counter = 0

    def _next(self, messages) -> Step:
        if not self.steps and self.router:
            self.steps = list(self.router(messages))
        if not self.steps:
            return Step(text="(hết kịch bản)")
        return self.steps.pop(0)

    async def stream_chat(self, messages: list[dict], tools: list[dict] | None = None, tool_choice: str = "auto"):
        self.requests.append(json.loads(json.dumps(messages, default=str)))
        self.tool_choices.append(tool_choice if tools else None)
        step = self._next(messages)
        if step.delay:
            await asyncio.sleep(step.delay)
        if step.error:
            raise step.error
        if step.tool_calls:
            calls = []
            for name, args in step.tool_calls:
                self._counter += 1
                calls.append(ToolCallReq(id=f"call_{self._counter}", name=name, arguments=json.dumps(args)))
            yield LLMEvent(type="tool_calls", tool_calls=calls)
        if step.text:
            for piece in re.findall(r"\S+\s*", step.text):
                yield LLMEvent(type="text", text=piece)
                await asyncio.sleep(0)
        yield LLMEvent(type="done", usage={"prompt_tokens": 1, "completion_tokens": 1})

    async def complete(self, messages: list[dict], max_tokens: int | None = None) -> str:
        # Tóm tắt giả: giữ nguyên toàn bộ nội dung được đưa vào (đủ để kiểm tra luồng dữ liệu)
        text = "\n".join(str(m.get("content", "")) for m in messages if m["role"] == "user")
        self.summaries.append(text)
        return "TÓM TẮT:\n" + text[-3000:]


def last_user_text(messages: list[dict[str, Any]]) -> str:
    return next(m["content"] for m in reversed(messages) if m["role"] == "user")
