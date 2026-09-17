"""Xử lý một lượt chat: dựng ngữ cảnh → vòng lặp LLM/tool → phát sự kiện → lưu tin nhắn → cập nhật bộ nhớ."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator

import asyncpg

from ..config import Settings
from ..llm.client import Embedder, LLMClient
from ..llm.prompts import SYSTEM_PROMPT
from ..memory.manager import MemoryManager
from ..repositories import conversations as conv_repo
from ..repositories import map_data as map_repo
from ..timeutil import iso
from ..tools import ToolContext, ToolResult, execute_tool, openai_tool_specs
from .events import Event

log = logging.getLogger(__name__)

DEFAULT_TITLE = "Hội thoại mới"
TITLE_MAX_CHARS = 60
_SUMMARY_KEYS = (
    "status", "count", "vessel_count", "total_matching", "returned", "point_count", "distance_nm",
    "matched_vessels", "vessels_with_data", "total_points", "method", "nearest_offset_minutes",
)


async def build_system_prompt(pool: asyncpg.Pool) -> str:
    """Điền phạm vi dữ liệu thực tế (từ DB) vào system prompt."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT min(event_ts) AS a, max(event_ts) AS b, min(lon) AS lon_min, max(lon) AS lon_max,
                   min(lat) AS lat_min, max(lat) AS lat_max,
                   (SELECT count(*) FROM vessels) AS vessel_count
            FROM ais_positions
            """
        )
    fmt = lambda x: "?" if x is None else f"{x:.0f}"  # noqa: E731
    return SYSTEM_PROMPT.format(
        coverage_start=iso(row["a"]) or "?",
        coverage_end=iso(row["b"]) or "?",
        lon_min=fmt(row["lon_min"]), lon_max=fmt(row["lon_max"]),
        lat_min=fmt(row["lat_min"]), lat_max=fmt(row["lat_max"]),
        vessel_count=row["vessel_count"],
    )


def _short_summary(result: ToolResult) -> dict:
    c = result.content
    if "error" in c:
        return {"error": c["error"]}
    out = {k: c[k] for k in _SUMMARY_KEYS if k in c}
    vessel = c.get("vessel")
    if isinstance(vessel, dict):
        out["vessel"] = vessel.get("name")
    return out


def _parse_args(raw: str):
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return raw


class ChatService:
    def __init__(self, pool: asyncpg.Pool, llm: LLMClient, embedder: Embedder, settings: Settings, system_prompt: str):
        self.pool = pool
        self.llm = llm
        self.settings = settings
        self.memory = MemoryManager(pool, llm, embedder, settings, system_prompt)
        self.tool_ctx = ToolContext(pool=pool, settings=settings)
        self.tool_specs = openai_tool_specs()
        self._locks: dict[str, asyncio.Lock] = {}

    async def close(self) -> None:
        await self.memory.close()

    async def _save(self, conv_id: str, turn: int, role: str, content: str, **kwargs) -> int:
        # shield: vẫn ghi xong khi request bị huỷ giữa chừng (client ngắt kết nối)
        async def write() -> int:
            async with self.pool.acquire() as conn:
                return await conv_repo.add_message(conn, conv_id, turn, role, content, **kwargs)

        return await asyncio.shield(write())

    async def run_turn(self, conv_id: str, text: str) -> AsyncIterator[Event]:
        lock = self._locks.setdefault(conv_id, asyncio.Lock())
        async with lock:  # các lượt trong cùng hội thoại chạy tuần tự; hội thoại khác chạy song song
            async for event in self._run_turn(conv_id, text):
                yield event

    async def _run_turn(self, conv_id: str, text: str) -> AsyncIterator[Event]:
        s = self.settings
        await self.memory.wait_idle(conv_id)

        async with self.pool.acquire() as conn:
            conv = await conv_repo.get_conversation(conn, conv_id)
            if conv is None:
                yield Event("error", {"code": "not_found", "message": "Hội thoại không tồn tại"})
                return
            turn = await conv_repo.next_turn_no(conn, conv_id)
            await conv_repo.add_message(conn, conv_id, turn, "user", text)
            if turn == 1 and conv["title"] == DEFAULT_TITLE:
                await conv_repo.rename_conversation(conn, conv_id, text.strip()[:TITLE_MAX_CHARS])

        focus = dict(conv["focus_state"] or {})
        answer = ""
        message_id = None
        data_ids: list[str] = []
        usage_total = {"prompt_tokens": 0, "completion_tokens": 0}
        try:
            ctx = await self.memory.build_context(conv_id, text, turn)
            if s.debug_memory_events:
                yield Event("memory", {
                    "window_turns": ctx.window_turns,
                    "summary_used": ctx.summary_used,
                    "retrieved": [{"turn_no": r["turn_no"], "score": round(r["score"], 3), "text": r["text"][:300]}
                                  for r in ctx.retrieved],
                })
            messages = ctx.messages

            for iteration in range(s.max_tool_iterations + 1):
                # Vòng cuối không đưa tool → buộc model trả lời bằng dữ liệu đã có
                tools = self.tool_specs if iteration < s.max_tool_iterations else None
                answer, calls = "", []
                async for ev in self.llm.stream_chat(messages, tools):
                    if ev.type == "text":
                        answer += ev.text
                        yield Event("token", {"text": ev.text})
                    elif ev.type == "tool_calls":
                        calls = ev.tool_calls
                    elif ev.type == "done" and ev.usage:
                        for k in usage_total:
                            usage_total[k] += ev.usage.get(k) or 0
                if not calls:
                    break

                call_dicts = [{"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                              for c in calls]
                messages.append({"role": "assistant", "content": answer or None, "tool_calls": call_dicts})
                await self._save(conv_id, turn, "assistant", answer, tool_calls=call_dicts)
                answer = ""
                for c in calls:
                    yield Event("tool_call", {"id": c.id, "name": c.name, "args": _parse_args(c.arguments)})

                results = await asyncio.gather(*(execute_tool(self.tool_ctx, c.name, c.arguments) for c in calls))
                for c, result in zip(calls, results):
                    content = dict(result.content)
                    for payload in result.map_data:
                        async with self.pool.acquire() as conn:
                            data_id = await map_repo.save_map_data(conn, conv_id, payload)
                        data_ids.append(data_id)
                        content["map"] = "Đã hiển thị trên bản đồ cho người dùng."
                        yield Event("data", {"data_id": data_id, "kind": payload.kind, "bbox": payload.bbox,
                                             "summary": {k: v for k, v in payload.summary.items() if k != "vessels"},
                                             "tool_call_id": c.id})
                    yield Event("tool_result", {"id": c.id, "name": c.name, "ok": result.ok,
                                                "summary": _short_summary(result)})
                    body = json.dumps(content, ensure_ascii=False, default=str)
                    messages.append({"role": "tool", "tool_call_id": c.id, "content": body})
                    await self._save(conv_id, turn, "tool", body, tool_call_id=c.id, tool_name=c.name)
                    focus.update(result.focus)
                if focus:
                    async with self.pool.acquire() as conn:
                        await conv_repo.update_focus(conn, conv_id, focus)

            message_id = await self._save(conv_id, turn, "assistant", answer,
                                          meta={"data_ids": data_ids, "usage": usage_total})
        except asyncio.CancelledError:
            log.info("Lượt %s của hội thoại %s bị huỷ (client ngắt kết nối)", turn, conv_id)
            await self._save(conv_id, turn, "assistant", answer + " …[bị ngắt]",
                             meta={"data_ids": data_ids, "interrupted": True})
            self.memory.schedule_after_turn(conv_id, turn)
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("Lỗi khi xử lý lượt %s của hội thoại %s", turn, conv_id)
            yield Event("error", {"code": "llm_error" if "openai" in type(exc).__module__ else "internal_error",
                                  "message": f"Không thể hoàn tất câu trả lời: {type(exc).__name__}"})
            message_id = await self._save(conv_id, turn, "assistant", answer,
                                          meta={"data_ids": data_ids, "error": type(exc).__name__})

        self.memory.schedule_after_turn(conv_id, turn)
        yield Event("done", {"message_id": message_id, "turn": turn, "usage": usage_total, "data_ids": data_ids})
