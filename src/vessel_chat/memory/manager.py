"""Bộ nhớ hội thoại kết hợp: trạng thái đang bàn + tóm tắt cuốn chiếu + truy xuất vector + cửa sổ nguyên văn.

Prompt mỗi lượt:
    [system prompt]
    [system: trạng thái hội thoại + tóm tắt các lượt cũ + ký ức truy xuất theo ngữ nghĩa]
    [N lượt gần nhất nguyên văn (kể cả tool call/kết quả, kết quả cũ bị rút gọn)]
    [câu hỏi hiện tại]

Sau mỗi lượt (chạy nền):
    - nhúng lượt vừa xong vào memory_chunks (luôn luôn, chi phí rất nhỏ)
    - các lượt vừa rời khỏi cửa sổ được gộp vào bản tóm tắt bằng LLM
Truy xuất vector chỉ xét các lượt cũ hơn cửa sổ nguyên văn → không lặp lại nội dung đã có.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field

import asyncpg

from ..config import Settings
from ..llm.client import Embedder, LLMClient
from ..llm.prompts import CONTEXT_HEADER, SUMMARY_SYSTEM, SUMMARY_USER
from ..repositories import conversations as conv_repo
from ..repositories import memory as mem_repo

log = logging.getLogger(__name__)

CHARS_PER_TOKEN = 3  # ước lượng thận trọng cho tiếng Việt có dấu
CHUNK_ANSWER_MAX_CHARS = 1500


@dataclass
class BuiltContext:
    messages: list[dict]
    window_turns: list[int] = field(default_factory=list)
    summary_used: bool = False
    retrieved: list[dict] = field(default_factory=list)


def _group_by_turn(rows: list[dict]) -> dict[int, list[dict]]:
    turns: dict[int, list[dict]] = {}
    for r in rows:
        turns.setdefault(r["turn_no"], []).append(r)
    return turns


def _truncate(text: str, limit: int | None) -> str:
    if limit is None or len(text) <= limit:
        return text
    return text[:limit] + " …[đã rút gọn]"


def _to_openai(rows: list[dict], tool_limit: int | None) -> list[dict]:
    """Đổi tin nhắn đã lưu sang định dạng OpenAI; bỏ tool call không có kết quả (lượt bị ngắt)."""
    answered = {r["tool_call_id"] for r in rows if r["role"] == "tool"}
    out: list[dict] = []
    valid_ids: set[str] = set()
    for r in rows:
        if r["role"] == "user":
            out.append({"role": "user", "content": r["content"]})
        elif r["role"] == "assistant":
            calls = [c for c in (r["tool_calls"] or []) if c["id"] in answered]
            if calls:
                valid_ids.update(c["id"] for c in calls)
                out.append({"role": "assistant", "content": r["content"] or None, "tool_calls": calls})
            elif r["content"]:
                out.append({"role": "assistant", "content": r["content"]})
        elif r["role"] == "tool" and r["tool_call_id"] in valid_ids:
            out.append({"role": "tool", "tool_call_id": r["tool_call_id"],
                        "content": _truncate(r["content"], tool_limit)})
    return out


def _estimate_tokens(messages: list[dict]) -> int:
    chars = 0
    for m in messages:
        chars += len(m.get("content") or "")
        for c in m.get("tool_calls") or []:
            chars += len(c["function"]["arguments"]) + len(c["function"]["name"])
    return chars // CHARS_PER_TOKEN + 4 * len(messages)


def turn_text(turn_no: int, rows: list[dict]) -> str:
    """Dạng văn bản của một lượt để nhúng/tóm tắt (bỏ dữ liệu thô của tool)."""
    lines = [f"Lượt {turn_no}"]
    for r in rows:
        if r["role"] == "user":
            lines.append(f"Người dùng: {r['content']}")
        elif r["role"] == "assistant":
            for c in r["tool_calls"] or []:
                lines.append(f"Tool: {c['function']['name']}({c['function']['arguments']})")
            if r["content"]:
                lines.append(f"Trợ lý: {_truncate(r['content'], CHUNK_ANSWER_MAX_CHARS)}")
    return "\n".join(lines)


class MemoryManager:
    def __init__(self, pool: asyncpg.Pool, llm: LLMClient, embedder: Embedder, settings: Settings, system_prompt: str):
        self.pool = pool
        self.llm = llm
        self.embedder = embedder
        self.settings = settings
        self.system_prompt = system_prompt
        self._tasks: dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------ dựng ngữ cảnh
    async def build_context(self, conv_id: str, user_text: str, current_turn: int) -> BuiltContext:
        s = self.settings
        first = max(1, current_turn - s.memory_window_turns)
        async with self.pool.acquire() as conn:
            conv = await conv_repo.get_conversation(conn, conv_id)
            rows = await conv_repo.messages_between_turns(conn, conv_id, first, current_turn - 1)

        # Cửa sổ nguyên văn: kết quả tool của lượt mới nhất giữ đủ, lượt cũ hơn bị rút gọn
        turns = _group_by_turn(rows)
        converted = {
            t: _to_openai(r, None if t == current_turn - 1 else s.memory_tool_result_max_chars)
            for t, r in turns.items()
        }
        kept = sorted(converted)
        while len(kept) > 1 and sum(_estimate_tokens(converted[t]) for t in kept) > s.memory_window_max_tokens:
            kept.pop(0)
        if kept and _estimate_tokens(converted[kept[0]]) > s.memory_window_max_tokens:
            kept = []  # một lượt duy nhất cũng quá ngân sách → dựa vào tóm tắt/ký ức
        oldest_verbatim = kept[0] if kept else current_turn

        retrieved: list[dict] = []
        if oldest_verbatim > 1 and s.memory_top_k > 0:
            [query_vec] = await self.embedder.embed([user_text])
            async with self.pool.acquire() as conn:
                retrieved = await mem_repo.search_chunks(
                    conn, conv_id, query_vec, max_turn=oldest_verbatim - 1,
                    k=s.memory_top_k, min_score=s.memory_min_score,
                )

        summary = conv["summary"] if conv else ""
        focus = conv["focus_state"] if conv else {}
        blocks = []
        if focus:
            blocks.append("## Đối tượng đang bàn gần nhất\n" + json.dumps(focus, ensure_ascii=False))
        if summary:
            upto = conv["summary_upto_turn"]
            blocks.append(f"## Tóm tắt các lượt 1–{upto}\n{summary}")
        if retrieved:
            parts = [f"[{r['turn_no']}] (độ liên quan {r['score']:.2f})\n{r['text']}"
                     for r in sorted(retrieved, key=lambda x: x["turn_no"])]
            blocks.append("## Ký ức liên quan từ các lượt cũ (truy xuất theo ngữ nghĩa)\n" + "\n\n".join(parts))

        messages = [{"role": "system", "content": self.system_prompt}]
        if blocks:
            messages.append({"role": "system", "content": CONTEXT_HEADER + "\n\n" + "\n\n".join(blocks)})
        for t in kept:
            messages.extend(converted[t])
        messages.append({"role": "user", "content": user_text})
        return BuiltContext(messages=messages, window_turns=kept, summary_used=bool(summary), retrieved=retrieved)

    # ------------------------------------------------------------------ sau mỗi lượt
    async def after_turn(self, conv_id: str, turn_no: int) -> None:
        s = self.settings
        async with self.pool.acquire() as conn:
            rows = await conv_repo.messages_between_turns(conn, conv_id, turn_no, turn_no)
            conv = await conv_repo.get_conversation(conn, conv_id)
        if not rows or conv is None:
            return

        text = turn_text(turn_no, rows)
        [vec] = await self.embedder.embed([text])
        async with self.pool.acquire() as conn:
            await mem_repo.add_chunk(conn, conv_id, turn_no, text, vec)

        compact_upto = turn_no - s.memory_window_turns
        start = conv["summary_upto_turn"] + 1
        if compact_upto < start:
            return
        async with self.pool.acquire() as conn:
            old_rows = await conv_repo.messages_between_turns(conn, conv_id, start, compact_upto)
        turns_text = "\n\n".join(turn_text(t, r) for t, r in sorted(_group_by_turn(old_rows).items()))
        summary = await self.llm.complete(
            [
                {"role": "system", "content": SUMMARY_SYSTEM},
                {"role": "user", "content": SUMMARY_USER.format(summary=conv["summary"] or "(trống)", turns=turns_text)},
            ],
            max_tokens=s.summary_max_tokens,
        )
        async with self.pool.acquire() as conn:
            await conv_repo.update_summary(conn, conv_id, summary.strip(), compact_upto)

    def schedule_after_turn(self, conv_id: str, turn_no: int) -> None:
        previous = self._tasks.get(conv_id)

        async def run() -> None:
            if previous is not None:
                await asyncio.gather(previous, return_exceptions=True)
            try:
                await self.after_turn(conv_id, turn_no)
            except Exception:  # noqa: BLE001
                log.exception("Cập nhật bộ nhớ thất bại (hội thoại %s, lượt %s)", conv_id, turn_no)

        task = asyncio.create_task(run())
        self._tasks[conv_id] = task
        task.add_done_callback(lambda t: self._tasks.get(conv_id) is t and self._tasks.pop(conv_id, None))

    async def wait_idle(self, conv_id: str) -> None:
        task = self._tasks.get(conv_id)
        if task is None:
            return
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=self.settings.memory_compaction_wait_seconds)
        except asyncio.TimeoutError:
            log.warning("Hết thời gian chờ cập nhật bộ nhớ của hội thoại %s", conv_id)

    async def close(self) -> None:
        tasks = list(self._tasks.values())
        if tasks:
            await asyncio.wait(tasks, timeout=self.settings.memory_compaction_wait_seconds)
