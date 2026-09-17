"""Xử lý một lượt chat: dựng ngữ cảnh → vòng lặp LLM/tool → phát sự kiện → lưu tin nhắn → cập nhật bộ nhớ."""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator

import asyncpg

from ..config import Settings
from ..guardrails.input import INJECTION_NOTICE, Moderator, check_input
from ..guardrails.output import OutputGuard, extract_answer_numbers, find_ungrounded_numbers, source_numbers
from ..llm.client import Embedder, LLMClient
from ..llm.prompts import SYSTEM_PROMPT
from ..memory.manager import MemoryManager
from ..observability import CHAT_DURATION, CHAT_TTFT, CHAT_TURNS, GUARDRAIL_EVENTS, LLM_COST, LLM_TOKENS, log_event
from ..repositories import conversations as conv_repo
from ..repositories import map_data as map_repo
from ..timeutil import iso
from ..tools import ToolContext, ToolResult, execute_tool, openai_tool_specs
from ..tools.cache import ToolCache
from .events import Event
from .evidence import build_evidence, cited_ids

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


def _guardrail_event(stage: str, action: str, kind: str, message: str, **extra) -> Event:
    GUARDRAIL_EVENTS.labels(stage, kind, action).inc()
    return Event("guardrail", {"stage": stage, "action": action, "kind": kind, "message": message, **extra})


_OUTPUT_EVENT_TEXT = {
    "secret": "Đã ẩn chuỗi trông giống thông tin bí mật trong câu trả lời.",
    "system_prompt_leak": "Đã chặn việc lặp lại chỉ dẫn nội bộ của hệ thống.",
}


def _parse_args(raw: str):
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return raw


class ChatService:
    def __init__(
        self,
        pool: asyncpg.Pool,
        llm: LLMClient,
        embedder: Embedder,
        settings: Settings,
        system_prompt: str,
        tool_pool: asyncpg.Pool | None = None,
        moderator: Moderator | None = None,
    ):
        self.pool = pool
        self.tool_pool = tool_pool or pool
        self.moderator = moderator
        self.system_prompt = system_prompt
        self.tool_cache = ToolCache(settings.tool_cache_ttl_seconds, settings.tool_cache_max_entries)
        self.llm = llm
        self.settings = settings
        self.memory = MemoryManager(pool, llm, embedder, settings, system_prompt)
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

    def _record_turn(self, conv_id, turn, outcome, started, first_token_at, tools_used, usage) -> None:
        duration = time.perf_counter() - started
        ttft = None if first_token_at is None else first_token_at - started
        cost = self.settings.cost_usd(usage["prompt_tokens"], usage["completion_tokens"])
        CHAT_TURNS.labels(outcome).inc()
        CHAT_DURATION.observe(duration)
        if ttft is not None:
            CHAT_TTFT.observe(ttft)
        LLM_TOKENS.labels("prompt").inc(usage["prompt_tokens"])
        LLM_TOKENS.labels("completion").inc(usage["completion_tokens"])
        LLM_COST.inc(cost)
        log_event(
            log, "chat_turn",
            conversation_id=conv_id, turn=turn, outcome=outcome, tools=tools_used,
            ttft_s=None if ttft is None else round(ttft, 3), duration_s=round(duration, 3),
            prompt_tokens=usage["prompt_tokens"], completion_tokens=usage["completion_tokens"],
            cost_usd=round(cost, 6),
        )

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
            evidence_base = await conv_repo.count_tool_messages(conn, conv_id)
            await conv_repo.add_message(conn, conv_id, turn, "user", text)
            if turn == 1 and conv["title"] == DEFAULT_TITLE:
                await conv_repo.rename_conversation(conn, conv_id, text.strip()[:TITLE_MAX_CHARS])

        focus = dict(conv["focus_state"] or {})
        started = time.perf_counter()
        first_token_at: float | None = None
        tools_used: list[str] = []
        outcome = "ok"
        answer = ""
        message_id = None
        data_ids: list[str] = []
        guard_log: list[dict] = []
        evidence: list[dict] = []
        usage_total = {"prompt_tokens": 0, "completion_tokens": 0}

        # ---- Guardrail đầu vào: chặn trước khi tốn một lần gọi LLM
        verdict = await check_input(text, s, self.moderator)
        if verdict.action == "block":
            guard_log.append({"stage": "input", "action": "block", "kind": verdict.kind, "reasons": verdict.reasons})
            yield _guardrail_event("input", "block", verdict.kind, "Yêu cầu bị chặn bởi guardrail đầu vào.",
                                   reasons=verdict.reasons)
            yield Event("token", {"text": verdict.message})
            message_id = await self._save(conv_id, turn, "assistant", verdict.message, meta={"guardrail": guard_log})
            self.memory.schedule_after_turn(conv_id, turn)
            self._record_turn(conv_id, turn, "blocked", started, time.perf_counter(), [], usage_total)
            yield Event("done", {"message_id": message_id, "turn": turn, "usage": usage_total, "data_ids": []})
            return

        guard = OutputGuard(self.system_prompt)
        seen_guard_events = 0

        def drain_guard_events():
            nonlocal seen_guard_events
            for e in guard.events[seen_guard_events:]:
                guard_log.append({"stage": "output", "action": "redact", **e})
                yield _guardrail_event("output", "redact", e["kind"], _OUTPUT_EVENT_TEXT.get(e["kind"], ""))
            seen_guard_events = len(guard.events)

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
            if verdict.action == "warn":
                messages.insert(len(messages) - 1, {"role": "system", "content": INJECTION_NOTICE})
                guard_log.append({"stage": "input", "action": "warn", "kind": verdict.kind, "reasons": verdict.reasons})
                yield _guardrail_event("input", "warn", verdict.kind,
                                       "Tin nhắn có dấu hiệu thay đổi chỉ dẫn; trợ lý vẫn tuân thủ quy tắc hệ thống.",
                                       reasons=verdict.reasons)

            for iteration in range(s.max_tool_iterations + 1):
                # Vòng cuối không đưa tool → buộc model trả lời bằng dữ liệu đã có
                tools = self.tool_specs if iteration < s.max_tool_iterations else None
                answer, calls = "", []
                async for ev in self.llm.stream_chat(messages, tools):
                    if ev.type == "text":
                        safe = guard.push(ev.text)
                        for e in drain_guard_events():
                            yield e
                        if safe:
                            if first_token_at is None:
                                first_token_at = time.perf_counter()
                            answer += safe
                            yield Event("token", {"text": safe})
                    elif ev.type == "tool_calls":
                        calls = ev.tool_calls
                    elif ev.type == "done" and ev.usage:
                        for k in usage_total:
                            usage_total[k] += ev.usage.get(k) or 0
                tail = guard.flush()
                for e in drain_guard_events():
                    yield e
                if tail:
                    if first_token_at is None:
                        first_token_at = time.perf_counter()
                    answer += tail
                    yield Event("token", {"text": tail})
                if not calls:
                    break

                call_dicts = [{"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                              for c in calls]
                messages.append({"role": "assistant", "content": answer or None, "tool_calls": call_dicts})
                await self._save(conv_id, turn, "assistant", answer, tool_calls=call_dicts)
                answer = ""
                tools_used.extend(c.name for c in calls)
                for c in calls:
                    yield Event("tool_call", {"id": c.id, "name": c.name, "args": _parse_args(c.arguments)})

                tool_ctx = ToolContext(pool=self.tool_pool, settings=s, focus=dict(focus), cache=self.tool_cache,
                                       embedder=self.memory.embedder)
                results = await asyncio.gather(*(execute_tool(tool_ctx, c.name, c.arguments) for c in calls))
                for c, result in zip(calls, results):
                    eid = f"E{evidence_base + len(evidence) + 1}"
                    content = {"evidence_id": eid, **result.content}
                    ev = build_evidence(eid, c.name, _parse_args(c.arguments), result)
                    evidence.append(ev)
                    for payload in result.map_data:
                        async with self.pool.acquire() as conn:
                            data_id = await map_repo.save_map_data(conn, conv_id, payload)
                        data_ids.append(data_id)
                        ev["data_ids"].append(data_id)
                        content["map"] = "Đã hiển thị trên bản đồ cho người dùng."
                        yield Event("data", {"data_id": data_id, "kind": payload.kind, "bbox": payload.bbox,
                                             "summary": {k: v for k, v in payload.summary.items() if k != "vessels"},
                                             "tool_call_id": c.id})
                    yield Event("tool_result", {"id": c.id, "name": c.name, "ok": result.ok,
                                                "summary": _short_summary(result), "evidence_id": eid})
                    yield Event("evidence", ev)
                    body = json.dumps(content, ensure_ascii=False, default=str)
                    messages.append({"role": "tool", "tool_call_id": c.id, "content": body})
                    await self._save(conv_id, turn, "tool", body, tool_call_id=c.id, tool_name=c.name)
                    focus.update(result.focus)
                if focus:
                    async with self.pool.acquire() as conn:
                        await conv_repo.update_focus(conn, conv_id, focus)

            # ---- Kiểm chứng đầu ra: con số phải truy được về dữ liệu; mã chứng cứ phải tồn tại
            verification = None
            if answer and not guard.leaked:
                checked = len(extract_answer_numbers(answer))
                ungrounded: list[str] = []
                if s.guardrail_grounding_enabled and checked:
                    sources = source_numbers([m["content"] for m in messages if isinstance(m.get("content"), str)])
                    ungrounded = find_ungrounded_numbers(answer, sources)
                cited = list(dict.fromkeys(cited_ids(answer)))
                last_id = evidence_base + len(evidence)
                unknown = [c for c in cited if not 1 <= int(c[1:]) <= last_id]
                verification = {
                    "numbers_checked": checked,
                    "ungrounded_numbers": ungrounded,
                    "citations": cited,
                    "unknown_citations": unknown,
                    "evidence_count": len(evidence),
                    "grounded": not ungrounded and not unknown,
                }
                yield Event("verification", verification)
                if ungrounded:
                    guard_log.append({"stage": "output", "action": "warn", "kind": "ungrounded_numbers",
                                      "numbers": ungrounded})
                    yield _guardrail_event(
                        "output", "warn", "ungrounded_numbers",
                        "Kiểm tra tự động: một số con số không tìm thấy trong dữ liệu đã truy vấn.",
                        numbers=ungrounded,
                    )
                if unknown:
                    guard_log.append({"stage": "output", "action": "warn", "kind": "unknown_citations",
                                      "citations": unknown})
                    yield _guardrail_event("output", "warn", "unknown_citations",
                                           "Câu trả lời trích mã chứng cứ không tồn tại.", citations=unknown)

            meta = {"data_ids": data_ids, "usage": usage_total, "evidence": evidence}
            if verification:
                meta["verification"] = verification
            if guard_log:
                meta["guardrail"] = guard_log
            message_id = await self._save(conv_id, turn, "assistant", answer, meta=meta)
        except asyncio.CancelledError:
            log.info("Lượt %s của hội thoại %s bị huỷ (client ngắt kết nối)", turn, conv_id)
            CHAT_TURNS.labels("cancelled").inc()
            await self._save(conv_id, turn, "assistant", answer + " …[bị ngắt]",
                             meta={"data_ids": data_ids, "evidence": evidence, "interrupted": True})
            self.memory.schedule_after_turn(conv_id, turn)
            raise
        except Exception as exc:  # noqa: BLE001
            outcome = "error"
            log.exception("Lỗi khi xử lý lượt %s của hội thoại %s", turn, conv_id)
            yield Event("error", {"code": "llm_error" if "openai" in type(exc).__module__ else "internal_error",
                                  "message": f"Không thể hoàn tất câu trả lời: {type(exc).__name__}"})
            message_id = await self._save(conv_id, turn, "assistant", answer,
                                          meta={"data_ids": data_ids, "evidence": evidence, "error": type(exc).__name__})

        self.memory.schedule_after_turn(conv_id, turn)
        self._record_turn(conv_id, turn, outcome, started, first_token_at, tools_used, usage_total)
        yield Event("done", {"message_id": message_id, "turn": turn, "usage": usage_total, "data_ids": data_ids})
