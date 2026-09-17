import json

import pytest

from vessel_chat.chat.evidence import build_evidence, cited_ids
from vessel_chat.tools import ToolContext, ToolResult, execute_tool

BETA = "00000000-0000-7000-8000-000000000003"


@pytest.fixture
def ctx(pool, settings):
    return ToolContext(pool=pool, settings=settings)


def facts(ev):
    return {f["label"]: f["value"] for f in ev["facts"]}


async def test_track_evidence_lists_sources_query_and_values(ctx):
    args = {"vessel": BETA, "start": "2026-09-11", "end": "2026-09-11"}
    result = await execute_tool(ctx, "get_track", json.dumps(args))
    ev = build_evidence("E3", "get_track", args, result)
    assert ev["id"] == "E3" and ev["ok"] is True
    assert ev["label"] == "Hành trình BETA SEA"
    assert ev["sources"] == ["ais_positions"]
    assert ev["query"] == args
    f = facts(ev)
    assert f["Số điểm dùng"] == "24"
    assert f["Điểm đầu"].startswith("2026-09-11T00:00:00Z")
    assert "hải lý" in f["Quãng đường"]


async def test_vessel_evidence_includes_companies(ctx):
    result = await execute_tool(ctx, "get_vessel_details", json.dumps({"vessel": "ALPHA STAR"}))
    f = facts(build_evidence("E1", "get_vessel_details", {"vessel": "ALPHA STAR"}, result))
    assert f["MMSI"] == "111111111"
    assert f["Chủ sở hữu đăng ký"] == "OCEAN LINE CO LTD (SINGAPORE)"


async def test_gap_and_knowledge_and_error_evidence(ctx):
    gaps = await execute_tool(ctx, "get_dark_gaps", json.dumps({"order_by": "duration", "limit": 1}))
    ev = build_evidence("E2", "get_dark_gaps", {"order_by": "duration"}, gaps)
    assert ev["sources"] == ["dark_gaps", "ais_positions"]
    assert any("DELTA FISH" in f["value"] for f in ev["facts"])

    kb = ToolResult(content={"status": "ok", "query": "dark gap", "results": [
        {"citation": "dark-gap.md › Định nghĩa", "text": "Một dark gap là…", "relevance": 0.8}]})
    ev = build_evidence("E4", "search_knowledge", {"query": "dark gap"}, kb)
    assert ev["sources"] == ["dark-gap.md"]
    assert ev["facts"][0] == {"label": "dark-gap.md › Định nghĩa", "value": "Một dark gap là…"}

    bad = build_evidence("E5", "get_track", {}, ToolResult(content={"error": "thiếu start"}))
    assert bad["ok"] is False and facts(bad)["Lỗi"] == "thiếu start"

    missing = build_evidence("E6", "get_last_position", {"vessel": "X"},
                             ToolResult(content={"status": "not_found", "message": "Không tìm thấy"}))
    assert facts(missing)["Kết quả"] == "Không tìm thấy"


def test_cited_ids():
    text = "Tàu đi 449 hải lý [E2], treo cờ Singapore [E1, E3]. Sai mã [E9]."
    assert cited_ids(text) == ["E2", "E1", "E3", "E9"]


def test_ambiguous_vessel_evidence_for_every_tool():
    result = ToolResult(content={"status": "ambiguous", "message": "Có nhiều tàu khớp",
                                 "candidates": [{"name": "ALPHA STAR", "mmsi": 1}, {"name": "ALPHA STAR II", "mmsi": 2}]})
    for tool in ("get_position_at", "get_track", "get_vessel_details", "get_dark_gaps", "get_multi_tracks"):
        ev = build_evidence("E1", tool, {}, result)
        assert facts(ev)["Kết quả"] == "Có nhiều tàu khớp"
        assert [f["value"] for f in ev["facts"] if f["label"] == "Ứng viên"] == ["ALPHA STAR 1", "ALPHA STAR II 2"]
