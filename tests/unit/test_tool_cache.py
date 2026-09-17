import json

import pytest
from pydantic import BaseModel

from vessel_chat.tools import ToolContext, execute_tool
from vessel_chat.tools.base import REGISTRY, Tool, ToolResult
from vessel_chat.tools.cache import ToolCache


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_ttl_cache_expiry_and_lru_eviction():
    clock = Clock()
    cache = ToolCache(ttl_seconds=10, max_entries=2, clock=clock)
    cache.put("a", ToolResult(content={"v": 1}))
    cache.put("b", ToolResult(content={"v": 2}))
    assert cache.get("a").content == {"v": 1}  # "a" vừa được dùng → "b" cũ nhất
    cache.put("c", ToolResult(content={"v": 3}))
    assert cache.get("b") is None and cache.get("a") is not None
    clock.t = 11
    assert cache.get("a") is None


def test_cached_result_is_a_copy():
    cache = ToolCache(ttl_seconds=10, max_entries=4)
    cache.put("k", ToolResult(content={"v": 1}))
    got = cache.get("k")
    got.content["map"] = "x"
    assert "map" not in cache.get("k").content


class CountingTool(Tool):
    name = "_test_counting"
    description = "test"
    calls = 0

    class Args(BaseModel):
        x: int

    async def run(self, ctx, args):
        CountingTool.calls += 1
        if args.x < 0:
            return ToolResult(content={"error": "âm"})
        return ToolResult(content={"x": args.x})


@pytest.fixture
def counting_tool():
    REGISTRY[CountingTool.name] = CountingTool()
    CountingTool.calls = 0
    yield
    REGISTRY.pop(CountingTool.name)


async def test_execute_tool_uses_cache_with_normalized_args(pool, settings, counting_tool):
    ctx = ToolContext(pool=pool, settings=settings, cache=ToolCache(60, 16))
    await execute_tool(ctx, "_test_counting", '{"x": 1}')
    r = await execute_tool(ctx, "_test_counting", json.dumps({"x": 1}, indent=2))
    assert r.content == {"x": 1} and CountingTool.calls == 1
    await execute_tool(ctx, "_test_counting", '{"x": 2}')
    assert CountingTool.calls == 2


async def test_errors_are_not_cached(pool, settings, counting_tool):
    ctx = ToolContext(pool=pool, settings=settings, cache=ToolCache(60, 16))
    await execute_tool(ctx, "_test_counting", '{"x": -1}')
    await execute_tool(ctx, "_test_counting", '{"x": -1}')
    assert CountingTool.calls == 2


async def test_company_tool_cache_key_depends_on_focus(pool, settings):
    cache = ToolCache(60, 16)
    alpha = "00000000-0000-7000-8000-000000000001"
    a = ToolContext(pool=pool, settings=settings, cache=cache, focus={"vessel": {"vessel_id": alpha, "name": "ALPHA STAR"}})
    b = ToolContext(pool=pool, settings=settings, cache=cache)
    args = '{"company_name": "OCEAN LINE", "role": "registered_owner"}'
    with_focus = await execute_tool(a, "find_company_vessels", args)
    without = await execute_tool(b, "find_company_vessels", args)
    assert "note" in with_focus.content and "note" not in without.content
