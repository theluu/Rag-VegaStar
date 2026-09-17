"""Hạ tầng tool: định nghĩa, đăng ký, sinh JSON schema cho OpenAI và thực thi an toàn."""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

import asyncpg
from pydantic import BaseModel, ValidationError

from ..config import Settings
from ..observability import TOOL_CALLS, TOOL_LATENCY

if TYPE_CHECKING:
    from .cache import ToolCache

log = logging.getLogger(__name__)


@dataclass
class MapPayload:
    """Dữ liệu bản đồ: đi thẳng tới client qua sự kiện `data`, không qua LLM."""

    kind: str  # position | track | gaps | tracks
    geojson: dict
    summary: dict
    bbox: list[float] | None


@dataclass
class ToolResult:
    content: dict  # phần gửi cho LLM (đã rút gọn)
    map_data: list[MapPayload] = field(default_factory=list)
    focus: dict = field(default_factory=dict)  # cập nhật "đối tượng đang bàn" của hội thoại

    @property
    def ok(self) -> bool:
        return "error" not in self.content


@dataclass
class ToolContext:
    pool: asyncpg.Pool
    settings: Settings
    focus: dict = field(default_factory=dict)  # "đối tượng đang bàn" của hội thoại (chỉ đọc)
    cache: "ToolCache | None" = None
    embedder: Any = None  # dùng cho tool kho tri thức


class ToolInputError(Exception):
    """Tham số hợp lệ về kiểu nhưng không dùng được (vd. thời gian sai định dạng)."""


class Tool:
    name: ClassVar[str]
    description: ClassVar[str]
    Args: ClassVar[type[BaseModel]]

    async def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:  # pragma: no cover
        raise NotImplementedError

    def cache_key(self, ctx: ToolContext, args: BaseModel) -> str | None:
        """Khoá cache từ tham số đã chuẩn hoá; None = không cache."""
        return self.name + ":" + json.dumps(args.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)


REGISTRY: dict[str, Tool] = {}


def register(cls: type[Tool]) -> type[Tool]:
    REGISTRY[cls.name] = cls()
    return cls


def _strip_titles(schema: Any) -> Any:
    if isinstance(schema, dict):
        return {k: _strip_titles(v) for k, v in schema.items() if k != "title"}
    if isinstance(schema, list):
        return [_strip_titles(v) for v in schema]
    return schema


def openai_tool_specs() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": _strip_titles(tool.Args.model_json_schema()),
            },
        }
        for tool in REGISTRY.values()
    ]


def error_result(message: str, **extra) -> ToolResult:
    return ToolResult(content={"error": message, **extra})


@dataclass
class ToolRun:
    """Một lần chạy tool kèm số đo vận hành (lưu vào meta của lượt để thống kê)."""

    result: ToolResult
    cache: str  # none | hit | miss
    seconds: float


async def run_tool(ctx: ToolContext, name: str, raw_args: str | None) -> ToolRun:
    """Chạy tool theo tên; mọi lỗi được chuyển thành kết quả {"error": ...} cho LLM tự xử lý."""
    started = time.perf_counter()
    result, cache_state = await _execute(ctx, name, raw_args)
    seconds = time.perf_counter() - started
    label = name if name in REGISTRY else "unknown"
    TOOL_LATENCY.labels(label).observe(seconds)
    TOOL_CALLS.labels(label, str(result.ok).lower(), cache_state).inc()
    return ToolRun(result, cache_state, seconds)


async def execute_tool(ctx: ToolContext, name: str, raw_args: str | None) -> ToolResult:
    return (await run_tool(ctx, name, raw_args)).result


async def _execute(ctx: ToolContext, name: str, raw_args: str | None) -> tuple[ToolResult, str]:
    """Trả (kết quả, trạng thái cache: none | hit | miss)."""
    cached, key = _lookup(ctx, name, raw_args)
    if cached is not None:
        return cached, "hit"
    result = await _call(ctx, name, raw_args)
    if key is None:
        return result, "none"
    if result.ok:
        ctx.cache.put(key, result)
    return result, "miss"


def _lookup(ctx: ToolContext, name: str, raw_args: str | None) -> tuple[ToolResult | None, str | None]:
    """Tra cache; trả (kết quả từ cache hoặc None, khoá cache hoặc None nếu không cache được)."""
    tool = REGISTRY.get(name)
    if tool is None or ctx.cache is None or not ctx.cache.enabled:
        return None, None
    try:
        args = tool.Args.model_validate(json.loads(raw_args or "{}"))
    except (json.JSONDecodeError, ValidationError):
        return None, None
    key = tool.cache_key(ctx, args)
    if key is None:
        return None, None
    return ctx.cache.get(key), key


async def _call(ctx: ToolContext, name: str, raw_args: str | None) -> ToolResult:
    tool = REGISTRY.get(name)
    if tool is None:
        return error_result(f"Tool không tồn tại: {name}")
    try:
        data = json.loads(raw_args or "{}")
    except json.JSONDecodeError:
        return error_result("Tham số không phải JSON hợp lệ")
    try:
        args = tool.Args.model_validate(data)
    except ValidationError as exc:
        issues = [f"{'.'.join(map(str, e['loc'])) or 'args'}: {e['msg']}" for e in exc.errors()]
        return error_result("Tham số không hợp lệ", details=issues)
    try:
        return await tool.run(ctx, args)
    except ToolInputError as exc:
        return error_result(str(exc))
    except asyncio.CancelledError:
        raise
    except asyncpg.QueryCanceledError:
        log.warning("Tool %s quá thời gian truy vấn", name)
        return error_result("Truy vấn quá thời gian cho phép; hãy thu hẹp phạm vi (ít tàu hơn hoặc khoảng thời gian ngắn hơn)")
    except Exception as exc:  # noqa: BLE001
        log.exception("Tool %s lỗi", name)
        return error_result(f"Lỗi nội bộ khi chạy tool ({type(exc).__name__})")
