from fakes import HashEmbedder
from vessel_chat.repositories import conversations as conv_repo
from vessel_chat.repositories import map_data as map_repo
from vessel_chat.repositories import memory as mem_repo
from vessel_chat.tools import MapPayload


async def test_conversation_crud_and_messages(pool):
    async with pool.acquire() as conn:
        c = await conv_repo.create_conversation(conn, "Thử nghiệm")
        cid = c["id"]
        assert await conv_repo.next_turn_no(conn, cid) == 1
        await conv_repo.add_message(conn, cid, 1, "user", "xin chào")
        await conv_repo.add_message(conn, cid, 1, "assistant", "", tool_calls=[{"id": "t1", "type": "function",
                                    "function": {"name": "x", "arguments": "{}"}}])
        await conv_repo.add_message(conn, cid, 1, "tool", '{"a": 1}', tool_call_id="t1", tool_name="x")
        await conv_repo.add_message(conn, cid, 1, "assistant", "chào bạn", meta={"data_ids": ["d1"]})
        assert await conv_repo.next_turn_no(conn, cid) == 2

        msgs = await conv_repo.list_messages(conn, cid)
        assert [m["role"] for m in msgs] == ["user", "assistant", "tool", "assistant"]
        assert msgs[1]["tool_calls"][0]["id"] == "t1"
        assert msgs[3]["meta"] == {"data_ids": ["d1"]}

        listed = await conv_repo.list_conversations(conn)
        entry = next(x for x in listed if x["id"] == cid)
        assert entry["message_count"] == 4

        await conv_repo.update_focus(conn, cid, {"vessel": {"name": "A"}})
        await conv_repo.update_summary(conn, cid, "tóm tắt", 3)
        got = await conv_repo.get_conversation(conn, cid)
        assert got["focus_state"] == {"vessel": {"name": "A"}}
        assert got["summary"] == "tóm tắt" and got["summary_upto_turn"] == 3

        assert await conv_repo.delete_conversation(conn, cid) is True
        assert await conv_repo.get_conversation(conn, cid) is None
        assert await conv_repo.list_messages(conn, cid) == []
        assert await conv_repo.delete_conversation(conn, cid) is False


async def test_messages_for_turns(pool):
    async with pool.acquire() as conn:
        cid = (await conv_repo.create_conversation(conn, "t"))["id"]
        for turn in (1, 2, 3):
            await conv_repo.add_message(conn, cid, turn, "user", f"q{turn}")
            await conv_repo.add_message(conn, cid, turn, "assistant", f"a{turn}")
        msgs = await conv_repo.messages_between_turns(conn, cid, 2, 3)
        assert [m["content"] for m in msgs] == ["q2", "a2", "q3", "a3"]


async def test_memory_search_is_scoped_and_filtered(pool):
    emb = HashEmbedder(64)
    async with pool.acquire() as conn:
        c1 = (await conv_repo.create_conversation(conn, "c1"))["id"]
        c2 = (await conv_repo.create_conversation(conn, "c2"))["id"]
        texts = ["hồ sơ HS-2026-117 theo dõi tàu MSC", "thời tiết hôm nay", "tàu cá ở vịnh"]
        vecs = await emb.embed(texts)
        for i, (t, v) in enumerate(zip(texts, vecs), start=1):
            await mem_repo.add_chunk(conn, c1, i, t, v)
        await mem_repo.add_chunk(conn, c2, 1, texts[0], vecs[0])
        # chạy lại không nhân đôi
        await mem_repo.add_chunk(conn, c1, 1, texts[0], vecs[0])

        q = (await emb.embed(["mã hồ sơ HS-2026-117 là gì"]))[0]
        hits = await mem_repo.search_chunks(conn, c1, q, max_turn=10, k=2, min_score=0.05)
        assert hits[0]["turn_no"] == 1 and hits[0]["text"] == texts[0]
        assert len(hits) <= 2
        assert all(h["score"] >= 0.05 for h in hits)

        none = await mem_repo.search_chunks(conn, c1, q, max_turn=0, k=2, min_score=0.0)
        assert none == []
        assert await mem_repo.max_chunk_turn(conn, c1) == 3


async def test_map_data_roundtrip(pool):
    async with pool.acquire() as conn:
        cid = (await conv_repo.create_conversation(conn, "m"))["id"]
        payload = MapPayload(kind="track", geojson={"type": "FeatureCollection", "features": []},
                             summary={"x": 1}, bbox=[1, 2, 3, 4])
        did = await map_repo.save_map_data(conn, cid, payload)
        got = await map_repo.get_map_data(conn, did)
        assert got["kind"] == "track" and got["geojson"]["type"] == "FeatureCollection"
        assert got["bbox"] == [1, 2, 3, 4]
        items = await map_repo.list_map_data(conn, cid)
        assert [i["id"] for i in items] == [did] and "geojson" not in items[0]
        assert await map_repo.get_map_data(conn, "00000000-0000-0000-0000-000000000000") is None
