"""Thống kê vận hành cho trang "Thống kê" của giao diện.

Số liệu lượt hỏi đáp đọc từ bảng messages nên vẫn còn sau khi khởi động lại. Khi đưa lên production,
endpoint này chỉ nên dành cho quản trị viên (xem SECURITY.md).
"""

import json
import logging
import statistics
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path

import asyncpg
from fastapi import APIRouter, Depends, Query, Request

from ..config import Settings
from ..repositories import stats as stats_repo
from .deps import get_app_settings, get_pool

log = logging.getLogger(__name__)

router = APIRouter(tags=["stats"])

RECENT_TURNS = 12


class StatsRange(str, Enum):
    day = "24h"
    week = "7d"
    month = "30d"
    all = "all"


_RANGE_DELTA = {
    StatsRange.day: timedelta(hours=24),
    StatsRange.week: timedelta(days=7),
    StatsRange.month: timedelta(days=30),
}


def _num(v):
    """asyncpg trả Decimal cho sum(); JSON cần số thường."""
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    return v


def _ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def _round(v: float | None, digits: int = 3) -> float | None:
    return None if v is None else round(v, digits)


async def _inventory(request: Request, pool: asyncpg.Pool, settings: Settings) -> dict:
    """Quy mô dữ liệu nguồn gần như không đổi → cache trong tiến trình."""
    cached = getattr(request.app.state, "stats_inventory", None)
    now = time.monotonic()
    if cached and now - cached[0] < settings.stats_inventory_ttl_seconds:
        return cached[1]
    async with pool.acquire() as conn:
        data = await stats_repo.data_inventory(conn)
    request.app.state.stats_inventory = (now, data)
    return data


def load_eval_report(path: str) -> dict | None:
    """Tóm tắt báo cáo harness đánh giá (results/eval_report.json) nếu có."""
    if not path:
        return None
    file = Path(path)
    if not file.is_file():
        return None
    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("Không đọc được báo cáo đánh giá %s", path)
        return None
    results = raw.get("results") or []
    categories: dict[str, dict] = {}
    failed_checks: Counter[str] = Counter()
    for r in results:
        cat = categories.setdefault(r.get("category", "khác"), {"name": r.get("category", "khác"), "cases": 0, "passed": 0})
        cat["cases"] += 1
        cat["passed"] += bool(r.get("passed"))
        for check, ok in (r.get("checks") or {}).items():
            if not ok:
                failed_checks[check] += 1
    first = [r["first_token_s"] for r in results if r.get("first_token_s") is not None]
    total = [r["total_s"] for r in results if r.get("total_s") is not None]
    passed = sum(bool(r.get("passed")) for r in results)
    return {
        "generated_at": datetime.fromtimestamp(file.stat().st_mtime, UTC),
        "cases": len(results),
        "passed": passed,
        "pass_rate": raw.get("pass_rate", _ratio(passed, len(results))),
        "cost_usd": _round(raw.get("cost_usd"), 5),
        "first_token_p50": _round(statistics.median(first)) if first else None,
        "total_p50": _round(statistics.median(total)) if total else None,
        "categories": sorted(categories.values(), key=lambda c: (-c["cases"], c["name"])),
        "failed_checks": dict(failed_checks),
    }


@router.get("/stats")
async def get_stats(
    request: Request,
    range_: StatsRange = Query(StatsRange.week, alias="range", description="Khoảng thời gian: 24h, 7d, 30d, all"),
    pool: asyncpg.Pool = Depends(get_pool),
    settings: Settings = Depends(get_app_settings),
):
    now = datetime.now(UTC)
    since = now - _RANGE_DELTA[range_] if range_ in _RANGE_DELTA else None
    async with pool.acquire() as conn:
        summary = await stats_repo.turn_summary(conn, since)
        daily = await stats_repo.daily_series(conn, since, settings.stats_timezone)
        tools = await stats_repo.tool_usage(conn, since)
        guardrails = await stats_repo.guardrail_counts(conn, since)
        verification = await stats_repo.verification_summary(conn, since)
        recent = await stats_repo.recent_turns(conn, since, RECENT_TURNS)
        memory = await stats_repo.memory_summary(conn)
    inventory = await _inventory(request, pool, settings)

    summary = {k: _num(v) for k, v in summary.items()}
    turns = summary["turns"]
    cost = settings.cost_usd(summary["prompt_tokens"], summary["completion_tokens"])
    service = getattr(request.app.state, "service", None)

    tool_rows = []
    for t in tools:
        t = {k: _num(v) for k, v in t.items()}
        tool_rows.append({
            "name": t["name"],
            "calls": t["calls"],
            "ok": t["ok"],
            "success_rate": _ratio(t["ok"], t["calls"]),
            "measured": t["measured"],
            "cache_hit_rate": _ratio(t["cache_hits"], t["cacheable"]),
            "ms_p50": _round(t["ms_p50"], 1),
            "ms_p95": _round(t["ms_p95"], 1),
        })
    total_calls = sum(t["calls"] for t in tool_rows)
    cache_hits = sum(_num(t["cache_hits"]) for t in tools)
    cacheable = sum(_num(t["cacheable"]) for t in tools)

    verification = {k: _num(v) for k, v in verification.items()}

    return {
        "generated_at": now,
        "range": range_.value,
        "since": since,
        "timezone": settings.stats_timezone,
        "overview": {
            "turns": turns,
            "conversations": summary["conversations"],
            "outcomes": {k: summary[k] for k in ("ok", "blocked", "error", "cancelled")},
            "success_rate": _ratio(summary["ok"], turns),
            "prompt_tokens": summary["prompt_tokens"],
            "completion_tokens": summary["completion_tokens"],
            "cost_usd": round(cost, 6),
            "cost_per_turn_usd": round(cost / turns, 6) if turns else None,
            "tool_calls": total_calls,
            "tool_calls_per_turn": round(total_calls / turns, 2) if turns else None,
            "first_turn_at": summary["first_at"],
            "last_turn_at": summary["last_at"],
        },
        "latency": {
            "measured_turns": summary["measured"],
            "ttft_p50": _round(summary["ttft_p50"]),
            "ttft_p95": _round(summary["ttft_p95"]),
            "duration_p50": _round(summary["duration_p50"]),
            "duration_p95": _round(summary["duration_p95"]),
        },
        "daily": [
            {
                "day": d["day"],
                "turns": d["turns"],
                "blocked": d["blocked"],
                "errors": d["errors"],
                "cost_usd": round(settings.cost_usd(_num(d["prompt_tokens"]), _num(d["completion_tokens"])), 6),
            }
            for d in daily
        ],
        "tools": tool_rows,
        "cache": {
            "hit_rate": _ratio(cache_hits, cacheable),
            "hits": cache_hits,
            "lookups": cacheable,
            "entries": len(service.tool_cache) if service else None,
            "max_entries": settings.tool_cache_max_entries,
        },
        "quality": {
            "verified_answers": verification["verified"],
            "grounded_answers": verification["grounded"],
            "grounded_rate": _ratio(verification["grounded"], verification["verified"]),
            "numbers_checked": verification["numbers_checked"],
            "answers_with_evidence": verification["with_evidence"],
            "cited_answers": verification["cited"],
            "citation_rate": _ratio(verification["cited"], verification["with_evidence"]),
            "auto_cited": verification["auto_cited"],
        },
        "guardrails": [{k: _num(v) for k, v in g.items()} for g in guardrails],
        "rag": {
            "knowledge_searches": next((t["calls"] for t in tool_rows if t["name"] == "search_knowledge"), 0),
            "knowledge_docs": inventory["knowledge_docs"],
            "knowledge_chunks": inventory["knowledge_chunks"],
            "memory_chunks": memory["memory_chunks"],
            "summarized_conversations": memory["summarized"],
        },
        "recent_turns": [
            {
                **{k: v for k, v in r.items() if k != "tools"},
                "tools": json.loads(r["tools"]) if isinstance(r["tools"], str) else r["tools"],
                "cost_usd": round(settings.cost_usd(r["prompt_tokens"] or 0, r["completion_tokens"] or 0), 6),
            }
            for r in recent
        ],
        "data": {
            **{k: _num(v) for k, v in inventory.items() if k != "ship_type_groups"},
            "ship_type_groups": inventory["ship_type_groups"],
            "conversations_total": memory["conversations"],
            "map_layers": memory["map_layers"],
        },
        "evaluation": load_eval_report(settings.eval_report_path),
        "runtime": {
            "model": settings.llm_model,
            "embedding_model": settings.embedding_model,
            "memory_window_turns": settings.memory_window_turns,
            "max_tool_iterations": settings.max_tool_iterations,
            "moderation_enabled": settings.guardrail_moderation_enabled,
            "grounding_enabled": settings.guardrail_grounding_enabled,
            "auth_required": bool(settings.api_key_list),
            "rate_limit_chat_per_minute": settings.rate_limit_chat_per_minute,
            "price_input_per_m": settings.price_input_per_m,
            "price_output_per_m": settings.price_output_per_m,
            "started_at": getattr(request.app.state, "started_at", None),
        },
    }
