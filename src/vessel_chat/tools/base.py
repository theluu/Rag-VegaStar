"""Hạ tầng tool: định nghĩa, đăng ký, sinh JSON schema cho OpenAI và thực thi an toàn."""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, ClassVar

import asyncpg
from pydantic import BaseModel, ValidationError

from ..config import Settings

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


class ToolInputError(Exception):
    """Tham số hợp lệ về kiểu nhưng không dùng được (vd. thời gian sai định dạng)."""


class Tool:
    name: ClassVar[str]
    description: ClassVar[str]
    Args: ClassVar[type[BaseModel]]

    async def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:  # pragma: no cover
        raise NotImplementedError


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


async def execute_tool(ctx: ToolContext, name: str, raw_args: str | None) -> ToolResult:
    """Chạy tool theo tên; mọi lỗi được chuyển thành kết quả {"error": ...} cho LLM tự xử lý."""
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
