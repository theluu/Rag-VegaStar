import json

import pytest

from fakes import HashEmbedder, ScriptedLLM
from vessel_chat.memory.manager import MemoryManager
from vessel_chat.repositories import conversations as conv_repo
from vessel_chat.repositories import memory as mem_repo

TURNS = [
    ("Ghi nhớ giúp tôi: tôi phụ trách hồ sơ HS-2099-001 và đang theo dõi tàu ALPHA STAR.", "Đã ghi nhớ."),
    ("Thời tiết biển hôm nay thế nào?", "Tôi không có dữ liệu thời tiết."),
    ("Tàu cá thường hoạt động ở đâu?", "Dữ liệu có 2 tàu cá."),
    ("Cho tôi thông tin tàu BETA SEA", "BETA SEA là tàu chở dầu."),
    ("Nó treo cờ nước nào?", "Singapore."),
]


@pytest.fixture
def manager(pool, settings):
    llm = ScriptedLLM()
    return MemoryManager(pool, llm, HashEmbedder(settings.embedding_dim), settings, system_prompt="SYS")


async def _seed(pool, manager, turns=TURNS, with_tool_turn=None):
    async with pool.acquire() as conn:
        cid = (await conv_repo.create_conversation(conn, "mem"))["id"]
        for i, (q, a) in enumerate(turns, start=1):
            await conv_repo.add_message(conn, cid, i, "user", q)
            if i == with_tool_turn:
                call = {"id": "c1", "type": "function", "function": {"name": "get_track", "arguments": "{}"}}
                await conv_repo.add_message(conn, cid, i, "assistant", "", tool_calls=[call])
                await conv_repo.add_message(conn, cid, i, "tool", json.dumps({"x": "y" * 9000}),
                                            tool_call_id="c1", tool_name="get_track")
            await conv_repo.add_message(conn, cid, i, "assistant", a)
    for i in range(1, len(turns) + 1):
        await manager.after_turn(cid, i)
    return cid


async def test_window_keeps_only_recent_turns_verbatim(pool, manager):
    cid = await _seed(pool, manager)
    ctx = await manager.build_context(cid, "Hồ sơ tôi nhắc từ đầu có mã gì?", current_turn=6)
    msgs = ctx.messages
    assert msgs[0] == {"role": "system", "content": "SYS"}
    users = [m["content"] for m in msgs if m["role"] == "user"]
    # window = 2 lượt gần nhất + câu hỏi hiện tại
    assert users == [TURNS[3][0], TURNS[4][0], "Hồ sơ tôi nhắc từ đầu có mã gì?"]
    assert ctx.window_turns == [4, 5]


async def test_old_turns_are_summarized_and_retrievable(pool, manager):
    cid = await _seed(pool, manager)
    ctx = await manager.build_context(cid, "Mã hồ sơ HS-2099-001 tôi nhắc từ đầu là gì?", current_turn=6)
    memory_block = ctx.messages[1]["content"]
    assert ctx.summary_used is True
    assert "HS-2099-001" in memory_block  # qua tóm tắt và/hoặc ký ức vector
    assert ctx.retrieved and ctx.retrieved[0]["turn_no"] == 1
    assert all(r["turn_no"] <= 3 for r in ctx.retrieved)  # không lặp lại lượt đã có trong cửa sổ

    async with pool.acquire() as conn:
        conv = await conv_repo.get_conversation(conn, cid)
        assert conv["summary_upto_turn"] == 3
        assert await mem_repo.max_chunk_turn(conn, cid) == 5


async def test_summary_only_calls_llm_when_turns_leave_window(pool, manager):
    await _seed(pool, manager, turns=TURNS[:2])
    assert manager.llm.summaries == []


async def test_focus_state_is_rendered(pool, manager):
    cid = await _seed(pool, manager, turns=TURNS[:1])
    async with pool.acquire() as conn:
        await conv_repo.update_focus(conn, cid, {"vessel": {"name": "BETA SEA", "vessel_id": "v-3"}})
    ctx = await manager.build_context(cid, "nó ở đâu?", current_turn=2)
    assert "BETA SEA" in ctx.messages[1]["content"] and "v-3" in ctx.messages[1]["content"]


async def test_tool_messages_kept_paired_and_truncated(pool, manager, settings):
    cid = await _seed(pool, manager, turns=TURNS[:2], with_tool_turn=1)
    ctx = await manager.build_context(cid, "tiếp", current_turn=3)
    msgs = ctx.messages
    i = next(k for k, m in enumerate(msgs) if m.get("tool_calls"))
    assert msgs[i + 1]["role"] == "tool" and msgs[i + 1]["tool_call_id"] == "c1"
    assert len(msgs[i + 1]["content"]) <= settings.memory_tool_result_max_chars + 50


async def test_orphan_tool_calls_are_dropped(pool, manager):
    async with pool.acquire() as conn:
        cid = (await conv_repo.create_conversation(conn, "orphan"))["id"]
        await conv_repo.add_message(conn, cid, 1, "user", "q")
        call = {"id": "zz", "type": "function", "function": {"name": "get_track", "arguments": "{}"}}
        await conv_repo.add_message(conn, cid, 1, "assistant", "", tool_calls=[call])  # bị ngắt, không có kết quả
        await conv_repo.add_message(conn, cid, 1, "assistant", "(đã dừng)")
    ctx = await manager.build_context(cid, "tiếp", current_turn=2)
    assert not any(m.get("tool_calls") for m in ctx.messages)
    assert [m["role"] for m in ctx.messages] == ["system", "user", "assistant", "user"]


async def test_token_budget_trims_oldest_window_turn(pool, manager, settings):
    tight = settings.model_copy(update={"memory_window_max_tokens": 30, "memory_window_turns": 3})
    m = MemoryManager(pool, manager.llm, manager.embedder, tight, system_prompt="SYS")
    long_turns = [("câu hỏi " + "x " * 60, "trả lời một"), ("câu hỏi hai", "trả lời hai")]
    cid = await _seed(pool, m, turns=long_turns)
    ctx = await m.build_context(cid, "câu hỏi x trước đó", current_turn=3)
    assert ctx.window_turns == [2]
    # lượt 1 bị cắt khỏi cửa sổ (chưa được tóm tắt) vẫn truy xuất được từ vector
    assert [r["turn_no"] for r in ctx.retrieved] == [1]


async def test_scheduled_work_can_be_awaited(pool, manager):
    async with pool.acquire() as conn:
        cid = (await conv_repo.create_conversation(conn, "bg"))["id"]
        await conv_repo.add_message(conn, cid, 1, "user", "q1")
        await conv_repo.add_message(conn, cid, 1, "assistant", "a1")
    manager.schedule_after_turn(cid, 1)
    await manager.wait_idle(cid)
    async with pool.acquire() as conn:
        assert await mem_repo.max_chunk_turn(conn, cid) == 1


async def test_wait_idle_does_not_block_on_slow_summary(pool, settings):
    import asyncio

    class SlowSummaryLLM(ScriptedLLM):
        async def complete(self, messages, max_tokens=None):
            await asyncio.sleep(3)
            return "tóm tắt chậm"

    m = MemoryManager(pool, SlowSummaryLLM(), HashEmbedder(settings.embedding_dim), settings, system_prompt="SYS")
    async with pool.acquire() as conn:
        cid = (await conv_repo.create_conversation(conn, "slow"))["id"]
        for t in (1, 2, 3):
            await conv_repo.add_message(conn, cid, t, "user", f"q{t}")
            await conv_repo.add_message(conn, cid, t, "assistant", f"a{t}")
    for t in (1, 2, 3):
        m.schedule_after_turn(cid, t)
    started = asyncio.get_running_loop().time()
    await m.wait_idle(cid)
    assert asyncio.get_running_loop().time() - started < 2  # chỉ chờ phần nhúng
    async with pool.acquire() as conn:
        assert await mem_repo.max_chunk_turn(conn, cid) == 3
    await m.close()
    async with pool.acquire() as conn:
        conv = await conv_repo.get_conversation(conn, cid)
    assert conv["summary"] == "tóm tắt chậm" and conv["summary_upto_turn"] == 1
