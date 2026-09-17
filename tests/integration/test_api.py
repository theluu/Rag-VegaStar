"""Test tích hợp API chat với LLM giả (không gọi OpenAI)."""

import asyncio
import json

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from fakes import HashEmbedder, ScriptedLLM, Step, last_user_text
from vessel_chat.api.app import create_app

BETA = "00000000-0000-7000-8000-000000000003"


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        name, data = None, []
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].strip())
        if name and data:
            events.append((name, json.loads("\n".join(data))))
    return events


def router(messages):
    """LLM giả 'hiểu' vài câu hỏi để kiểm tra luồng end-to-end."""
    q = last_user_text(messages)
    if messages[-1]["role"] == "tool":
        return [Step(text="Đã có kết quả từ công cụ.")]
    if "hành trình" in q:
        return [Step(tool_calls=[("get_track", {"vessel": "BETA SEA", "start": "2026-09-11", "end": "2026-09-11"})])]
    if "lỗi tool" in q:
        return [Step(tool_calls=[("get_track", {"vessel": "BETA SEA"})])]
    if "lỗi llm" in q:
        return [Step(error=RuntimeError("boom"))]
    if "chậm" in q:
        return [Step(text=f"trả lời chậm cho: {q}", delay=0.2)]
    return [Step(text=f"Bạn hỏi: {q}")]


@pytest_asyncio.fixture
async def client(settings, pool):
    llm = ScriptedLLM(router=router)
    app = create_app(settings=settings, llm=llm, embedder=HashEmbedder(settings.embedding_dim))
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30) as c:
            c.llm = llm
            c.app = app
            yield c


async def new_conv(client, title=None):
    r = await client.post("/conversations", json={"title": title} if title else {})
    assert r.status_code == 201
    return r.json()["id"]


async def chat(client, cid, message):
    r = await client.post(f"/conversations/{cid}/chat", json={"message": message})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")
    return parse_sse(r.text)


async def test_health(client):
    r = await client.get("/health")
    assert r.json()["status"] == "ok" and r.json()["vessels"] == 6


async def test_conversation_lifecycle(client):
    cid = await new_conv(client)
    events = await chat(client, cid, "Xin chào")
    names = [e for e, _ in events]
    assert names[0] == "memory"
    assert names.count("token") >= 2  # văn bản đến dần
    assert names[-1] == "done"
    text = "".join(d["text"] for e, d in events if e == "token")
    assert text == "Bạn hỏi: Xin chào"

    listed = (await client.get("/conversations")).json()
    entry = next(c for c in listed if c["id"] == cid)
    assert entry["title"] == "Xin chào"  # tiêu đề tự đặt từ câu hỏi đầu

    msgs = (await client.get(f"/conversations/{cid}/messages")).json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["content"] == text

    assert (await client.delete(f"/conversations/{cid}")).status_code == 204
    assert (await client.get(f"/conversations/{cid}/messages")).status_code == 404
    assert (await client.delete(f"/conversations/{cid}")).status_code == 404


async def test_tool_flow_emits_structured_events_and_map_data(client):
    cid = await new_conv(client)
    events = await chat(client, cid, "Cho xem hành trình tàu BETA SEA ngày 11/09")
    names = [e for e, _ in events]
    i_call, i_data, i_result = names.index("tool_call"), names.index("data"), names.index("tool_result")
    assert i_call < i_data < i_result < names.index("token") < names.index("done")

    call = events[i_call][1]
    assert call["name"] == "get_track" and call["args"]["vessel"] == "BETA SEA"
    data = events[i_data][1]
    assert data["kind"] == "track" and len(data["bbox"]) == 4
    assert events[i_result][1]["ok"] is True
    assert events[i_result][1]["summary"]["point_count"] == 24

    geo = (await client.get(f"/map-data/{data['data_id']}")).json()
    assert geo["geojson"]["type"] == "FeatureCollection"
    refs = (await client.get(f"/conversations/{cid}/map-data")).json()
    assert [r["id"] for r in refs] == [data["data_id"]]

    # Tin nhắn tool được lưu và LLM nhận kết quả tool ở lượt gọi thứ hai
    msgs = (await client.get(f"/conversations/{cid}/messages")).json()
    assert [m["role"] for m in msgs] == ["user", "assistant", "tool", "assistant"]
    tool_msg = json.loads(msgs[2]["content"])
    assert tool_msg["vessel"]["name"] == "BETA SEA" and "coordinates" not in msgs[2]["content"]
    assert msgs[3]["meta"]["data_ids"] == [data["data_id"]]

    conv = (await client.get(f"/conversations/{cid}")).json()
    assert conv["focus_state"]["vessel"]["vessel_id"] == BETA


async def test_tool_error_is_reported_and_stream_completes(client):
    cid = await new_conv(client)
    events = await chat(client, cid, "gây lỗi tool")
    result = next(d for e, d in events if e == "tool_result")
    assert result["ok"] is False and "error" in result["summary"]
    assert events[-1][0] == "done"


async def test_llm_error_emits_error_event_then_done(client):
    cid = await new_conv(client)
    events = await chat(client, cid, "gây lỗi llm")
    names = [e for e, _ in events]
    assert "error" in names and names[-1] == "done"
    # hội thoại vẫn dùng tiếp được
    events = await chat(client, cid, "câu tiếp theo")
    assert "".join(d["text"] for e, d in events if e == "token") == "Bạn hỏi: câu tiếp theo"


async def test_parallel_conversations_do_not_mix(client):
    a, b = await new_conv(client), await new_conv(client)
    ra, rb = await asyncio.gather(chat(client, a, "chậm A"), chat(client, b, "chậm B"))
    ta = "".join(d["text"] for e, d in ra if e == "token")
    tb = "".join(d["text"] for e, d in rb if e == "token")
    assert ta == "trả lời chậm cho: chậm A" and tb == "trả lời chậm cho: chậm B"
    ma = (await client.get(f"/conversations/{a}/messages")).json()
    assert all("B" not in m["content"] for m in ma)


async def test_long_conversation_recalls_first_turn(client, settings):
    """Kịch bản 3 thu nhỏ: window = 2 lượt, thông tin ở lượt 1 vẫn vào được prompt sau 10+ lượt."""
    cid = await new_conv(client)
    await chat(client, cid, "Ghi nhớ giúp tôi: tôi phụ trách hồ sơ HS-2099-777 và đang theo dõi tàu ALPHA STAR.")
    for i in range(11):
        await chat(client, cid, f"Câu hỏi xen giữa số {i} về thời tiết")
    events = await chat(client, cid, "Hồ sơ HS tôi nhắc từ đầu cuộc trò chuyện có mã gì, tôi theo dõi tàu nào?")

    memory = next(d for e, d in events if e == "memory")
    assert memory["summary_used"] is True
    assert memory["window_turns"] == [11, 12]  # lượt hiện tại là 13
    prompt = client.llm.requests[-1]
    user_turns = [m["content"] for m in prompt if m["role"] == "user"]
    assert not any("HS-2099-777" in u for u in user_turns)  # lượt 1 không còn trong cửa sổ
    assert "HS-2099-777" in prompt[1]["content"]  # nhưng có trong phần bộ nhớ
    assert "ALPHA STAR" in prompt[1]["content"]


async def test_history_survives_app_restart(settings, pool):
    llm = ScriptedLLM(router=router)
    app = create_app(settings=settings, llm=llm, embedder=HashEmbedder(settings.embedding_dim))
    async with LifespanManager(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            cid = await new_conv(c)
            await chat(c, cid, "lần đầu")
    app2 = create_app(settings=settings, llm=ScriptedLLM(router=router), embedder=HashEmbedder(settings.embedding_dim))
    async with LifespanManager(app2):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app2), base_url="http://t") as c:
            msgs = (await c.get(f"/conversations/{cid}/messages")).json()
            assert [m["content"] for m in msgs] == ["lần đầu", "Bạn hỏi: lần đầu"]
            await chat(c, cid, "lần hai")
            assert len((await c.get(f"/conversations/{cid}/messages")).json()) == 4


async def test_validation_and_not_found(client):
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await client.post(f"/conversations/{missing}/chat", json={"message": "x"})).status_code == 404
    assert (await client.post("/conversations/not-a-uuid/chat", json={"message": "x"})).status_code == 422
    cid = await new_conv(client)
    assert (await client.post(f"/conversations/{cid}/chat", json={"message": ""})).status_code == 422
    assert (await client.get(f"/map-data/{missing}")).status_code == 404


async def test_tracks_endpoint_paginates(client):
    r = await client.get("/tracks", params={"start": "2026-09-10", "end": "2026-09-12", "limit": 2})
    body = r.json()
    assert r.status_code == 200 and body["type"] == "FeatureCollection"
    assert body["pagination"] == {"offset": 0, "limit": 2, "total_vessels": 6, "next_offset": 2}
    assert len(body["summary"]["vessels"]) == 2

    r = await client.get("/tracks", params={"start": "2026-09-10", "end": "2026-09-12",
                                            "vessel": ["BETA SEA", "111111111"]})
    assert {f["properties"]["name"] for f in r.json()["features"]} == {"BETA SEA", "ALPHA STAR"}

    r = await client.get("/tracks", params={"start": "2026-09-10", "end": "2026-09-12",
                                            "company": "Ocean Line", "role": "registered_owner"})
    assert r.json()["pagination"]["total_vessels"] == 2

    assert (await client.get("/tracks", params={"start": "x", "end": "y"})).status_code == 422
    assert (await client.get("/tracks", params={"start": "2026-09-10", "end": "2026-09-12",
                                                "company": "ocean"})).status_code == 409


async def test_dark_gaps_endpoint(client):
    r = await client.get("/vessels/BETA SEA/dark-gaps")
    body = r.json()
    assert r.status_code == 200 and body["type"] == "FeatureCollection"
    assert body["summary"]["total_matching"] == 1
    assert (await client.get("/vessels/NOPE ZZZ/dark-gaps")).status_code == 404
    assert (await client.get("/vessels/search", params={"q": "alpha"})).json()[0]["shipname"].startswith("ALPHA")
