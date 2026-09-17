import json

import pytest

from vessel_chat.tools import ToolContext, execute_tool, openai_tool_specs

ALPHA = "00000000-0000-7000-8000-000000000001"
BETA = "00000000-0000-7000-8000-000000000003"
DELTA = "00000000-0000-7000-8000-000000000006"


@pytest.fixture
def ctx(pool, settings):
    return ToolContext(pool=pool, settings=settings)


async def call(ctx, name, **args):
    return await execute_tool(ctx, name, json.dumps(args))


def test_specs_cover_all_tools():
    names = {s["function"]["name"] for s in openai_tool_specs()}
    assert names == {
        "search_vessels", "get_vessel_details", "find_company_vessels", "get_position_at",
        "get_last_position", "get_track", "get_dark_gaps", "get_multi_tracks",
    }
    for s in openai_tool_specs():
        assert s["type"] == "function" and s["function"]["description"]
        assert s["function"]["parameters"]["type"] == "object"


async def test_search_vessels(ctx):
    r = await call(ctx, "search_vessels", query="alpha star")
    assert r.content["count"] == 2
    assert r.content["results"][0]["name"] == "ALPHA STAR"


async def test_vessel_details_with_owners_and_focus(ctx):
    r = await call(ctx, "get_vessel_details", vessel="Alpha Star")
    c = r.content
    assert c["vessel"]["mmsi"] == 111111111 and c["vessel"]["ship_type_group"] == "cargo"
    assert c["ownership_available"] is True
    assert {"role": "registered_owner", "company_name": "OCEAN LINE CO LTD", "company_country": "SINGAPORE",
            "start_date": "2015-01-01"} in c["companies"]
    assert c["ais_summary"]["position_count"] == 43
    assert c["ais_summary"]["dark_gap_count"] == 1
    assert r.focus["vessel"]["vessel_id"] == ALPHA
    assert r.focus["company"]["name"] == "OCEAN LINE CO LTD"


async def test_vessel_details_without_ownership(ctx):
    r = await call(ctx, "get_vessel_details", vessel="GAMMA")
    assert r.content["ownership_available"] is False and r.content["companies"] == []


async def test_ambiguous_vessel_returns_candidates(ctx):
    r = await call(ctx, "get_vessel_details", vessel="alpha")
    assert r.content["status"] == "ambiguous"
    assert {c["name"] for c in r.content["candidates"]} == {"ALPHA STAR", "ALPHA STAR II"}
    assert r.focus == {}


async def test_unknown_vessel(ctx):
    r = await call(ctx, "get_last_position", vessel="NO SUCH SHIP XYZ")
    assert r.content["status"] == "not_found"


async def test_find_company_vessels_merges_variants(ctx):
    r = await call(ctx, "find_company_vessels", company_name="Ocean Line Co., Ltd", role="registered_owner")
    c = r.content
    assert c["status"] == "ok"
    assert set(c["name_variants"]) == {"OCEAN LINE CO LTD", "OCEAN LINE CO"}
    assert [v["name"] for v in c["vessels"]] == ["ALPHA STAR", "BETA SEA"]
    assert "OCEAN LINE ASIA" in c["similar_companies_not_included"]
    assert r.focus["company"]["norm"] == "OCEAN LINE"


async def test_find_company_vessels_excludes_vessel(ctx):
    r = await call(ctx, "find_company_vessels", company_name="OCEAN LINE CO LTD", role="registered_owner",
                   exclude_vessel=ALPHA)
    assert [v["name"] for v in r.content["vessels"]] == ["BETA SEA"]


async def test_find_company_ambiguous(ctx):
    r = await call(ctx, "find_company_vessels", company_name="ocean")
    assert r.content["status"] == "ambiguous"
    assert {"OCEAN LINE", "OCEAN HOLDINGS", "OCEAN LINE ASIA"} <= {c["company"] for c in r.content["candidates"]}


async def test_position_interpolated(ctx):
    r = await call(ctx, "get_position_at", vessel=BETA, timestamp="2026-09-11T05:30:00Z")
    c = r.content
    assert c["status"] == "ok"
    assert c["method"] == "interpolated"
    assert c["position"]["lon"] == pytest.approx(105.55)
    assert c["nearest_offset_minutes"] == 30
    assert r.map_data and r.map_data[0].kind == "position"


async def test_position_exact(ctx):
    r = await call(ctx, "get_position_at", vessel=BETA, timestamp="2026-09-11 05:00")
    assert r.content["method"] == "exact" and r.content["position"]["lon"] == pytest.approx(105.5)


async def test_position_no_data_near_time_inside_gap(ctx):
    r = await call(ctx, "get_position_at", vessel="alpha star", timestamp="2026-09-10T12:00:00Z")
    c = r.content
    assert c["status"] == "no_data_near_time"
    assert c["before"]["ts"] == "2026-09-10T10:00:00Z" and c["after"]["ts"] == "2026-09-10T15:00:00Z"
    assert c["before_offset_minutes"] == 120
    assert c["in_dark_gap"]["gap_start_ts"] == "2026-09-10T10:00:00Z"
    assert "position" not in c


async def test_position_outside_dataset(ctx):
    r = await call(ctx, "get_position_at", vessel=BETA, timestamp="2026-09-20T00:00:00Z")
    assert r.content["status"] == "no_data_near_time"
    assert r.content["after"] is None


async def test_last_position(ctx):
    r = await call(ctx, "get_last_position", vessel="222222222")
    assert r.content["position"]["ts"] == "2026-09-12T23:00:00Z"
    assert r.focus["vessel"]["name"] == "BETA SEA"


async def test_track_filters_jump_and_reports_gap(ctx):
    r = await call(ctx, "get_track", vessel=ALPHA, start="2026-09-10T00:00:00Z", end="2026-09-10T23:59:59Z")
    c = r.content
    assert c["status"] == "ok"
    assert c["raw_point_count"] == 30 and c["removed_noise_points"] == 1 and c["point_count"] == 29
    assert c["start"]["ts"] == "2026-09-10T00:00:00Z" and c["end"]["ts"] == "2026-09-10T23:00:00Z"
    assert len(c["gaps"]) == 1 and c["gaps"][0]["hours"] == 5.0
    assert c["distance_nm"] > 0 and c["avg_speed_knots"] > 0
    track = r.map_data[0]
    assert track.kind == "track"
    geoms = [f["geometry"]["type"] for f in track.geojson["features"]]
    assert "MultiLineString" in geoms
    assert r.focus["time_range"] == {"start": "2026-09-10T00:00:00Z", "end": "2026-09-10T23:59:59Z"}


async def test_track_day_comparison(ctx):
    d11 = await call(ctx, "get_track", vessel=BETA, start="2026-09-11", end="2026-09-11T23:59:59")
    d12 = await call(ctx, "get_track", vessel=BETA, start="2026-09-12", end="2026-09-12T23:59:59")
    assert d12.content["distance_nm"] > d11.content["distance_nm"] * 1.5


async def test_track_no_data(ctx):
    r = await call(ctx, "get_track", vessel="GAMMA", start="2026-09-11", end="2026-09-12")
    assert r.content["status"] == "no_data"
    assert r.content["last_before"]["ts"] == "2026-09-10T06:00:00Z"
    assert r.map_data == []


async def test_track_rejects_inverted_range(ctx):
    r = await call(ctx, "get_track", vessel=BETA, start="2026-09-12", end="2026-09-11")
    assert "error" in r.content


async def test_longest_dark_gap_fleet_wide(ctx):
    r = await call(ctx, "get_dark_gaps", order_by="duration", limit=1)
    g = r.content["gaps"][0]
    assert g["vessel"]["vessel_id"] == DELTA
    assert g["duration_hours"] == 26.0
    assert g["start_position"] == {"lat": 8.11, "lon": 107.0}
    assert g["speed_before_gap"]["speed_knots"] == pytest.approx(5.1)
    assert g["speed_before_gap"]["ts"] == "2026-09-10T22:00:00Z"
    assert r.content["total_matching"] == 3
    assert r.focus["vessel"]["vessel_id"] == DELTA
    assert r.map_data[0].kind == "gaps"


async def test_dark_gaps_for_vessel(ctx):
    r = await call(ctx, "get_dark_gaps", vessel="BETA SEA")
    assert r.content["total_matching"] == 1
    assert r.content["gaps"][0]["speed_before_gap"]["speed_knots"] == 12.5


async def test_dark_gaps_none(ctx):
    r = await call(ctx, "get_dark_gaps", vessel="GAMMA")
    assert r.content["total_matching"] == 0 and r.content["gaps"] == []


async def test_multi_tracks_by_type(ctx, settings):
    small = ToolContext(pool=ctx.pool, settings=settings.model_copy(update={"multi_track_max_points": 10}))
    r = await call(small, "get_multi_tracks", ship_type_group="cargo", start="2026-09-11", end="2026-09-11T23:59:59")
    c = r.content
    assert c["matched_vessels"] == 2 and c["vessels_with_data"] == 2
    assert c["top_by_distance"][0]["name"] == "ALPHA STAR"
    assert c["rendered_points"] <= 10 < c["total_points"]
    fc = r.map_data[0].geojson
    assert fc["type"] == "FeatureCollection" and len(fc["features"]) == 2
    assert "coordinates" not in json.dumps(c)  # dữ liệu hình học không đi vào LLM


async def test_multi_tracks_by_company_role(ctx):
    r = await call(ctx, "get_multi_tracks", company_name="Blue Ops", role="operator",
                   start="2026-09-10", end="2026-09-12T23:59:59")
    assert r.content["company"]["norm"] == "BLUE OPS"
    assert {v["name"] for v in r.content["top_by_distance"]} == {"ALPHA STAR", "BETA SEA"}


async def test_execute_tool_errors(ctx):
    assert "error" in (await execute_tool(ctx, "nope", "{}")).content
    assert "error" in (await execute_tool(ctx, "get_track", "{not json")).content
    assert "error" in (await call(ctx, "get_track", vessel=BETA)).content
    assert "error" in (await call(ctx, "get_position_at", vessel=BETA, timestamp="yesterday")).content
