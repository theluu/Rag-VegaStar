from pydantic import BaseModel, Field

from ..geo import bbox_of, filter_jumps, interpolate, point_json, track_geometry, track_stats
from ..repositories import gaps as gap_repo
from ..repositories import positions as pos_repo
from ..repositories import vessels as vessel_repo
from ..timeutil import iso
from ..tracks import build_multi_tracks
from .base import MapPayload, Tool, ToolContext, ToolResult, register
from .common import (
    TIME_ARG_DESC,
    VESSEL_ARG_DESC,
    Role,
    ShipTypeGroup,
    bbox_from_lonlats,
    collection,
    company_focus,
    feature,
    fmt_duration,
    minutes_between,
    parse_range,
    parse_time_arg,
    point_geom,
    resolve_company,
    resolve_vessel,
    time_range_json,
    vessel_brief,
    vessel_focus,
)


def _fmt_point(label: str, p: dict | None, offset: float | None) -> str:
    if not p:
        return f"không có điểm {label}"
    return f"điểm {label} lúc {p['ts']} ({p['lat']}, {p['lon']}), lệch {offset:g} phút"


def _position_explanation(c: dict) -> str:
    before = _fmt_point("trước", c["before"], c["before_offset_minutes"])
    after = _fmt_point("sau", c["after"], c["after_offset_minutes"])
    method = c.get("method")
    if method == "exact":
        text = "Có điểm AIS đúng thời điểm hỏi."
    elif method == "interpolated":
        text = f"Vị trí là NỘI SUY tuyến tính theo thời gian giữa {before} và {after}."
    elif method == "nearest_point":
        text = f"Vị trí lấy theo điểm AIS gần nhất (không nội suy vì hai điểm cách nhau quá xa): {before}; {after}."
    else:
        text = (f"KHÔNG có dữ liệu trong phạm vi ±{c['max_offset_minutes_allowed']:g} phút quanh thời điểm hỏi: "
                f"{before}; {after}.")
    if c.get("in_dark_gap"):
        g = c["in_dark_gap"]
        text += f" Thời điểm này nằm trong một lần mất tín hiệu AIS ({g['gap_start_ts']} → {g['gap_end_ts']}, {g['duration']})."
    return text


@register
class GetPositionAt(Tool):
    name = "get_position_at"
    description = (
        "Vị trí của một tàu tại một thời điểm (UTC): điểm AIS gần nhất trước/sau, độ lệch thời gian, vị trí nội suy "
        "nếu hai điểm đủ gần. status=no_data_near_time nghĩa là KHÔNG có dữ liệu đủ gần thời điểm đó — phải nói rõ "
        "với người dùng, kèm điểm gần nhất và độ lệch. Kết quả được hiển thị trên bản đồ."
    )

    class Args(BaseModel):
        vessel: str = Field(description=VESSEL_ARG_DESC)
        timestamp: str = Field(description=TIME_ARG_DESC)

    async def run(self, ctx: ToolContext, args: Args) -> ToolResult:
        s = ctx.settings
        ts = parse_time_arg(args.timestamp, "timestamp")
        async with ctx.pool.acquire() as conn:
            v, problem = await resolve_vessel(conn, s, args.vessel)
            if problem:
                return ToolResult(content=problem)
            before, after = await pos_repo.nearest_positions(conn, v["vessel_id"], ts)
            gap = await gap_repo.gap_covering(conn, v["vessel_id"], ts)

        before_off = minutes_between(before.ts, ts) if before else None
        after_off = minutes_between(ts, after.ts) if after else None
        offsets = [o for o in (before_off, after_off) if o is not None]
        nearest_off = min(offsets) if offsets else None

        content = {
            "vessel": vessel_brief(v),
            "requested_ts": iso(ts),
            "before": point_json(before),
            "before_offset_minutes": before_off,
            "after": point_json(after),
            "after_offset_minutes": after_off,
            "nearest_offset_minutes": nearest_off,
            "max_offset_minutes_allowed": s.position_max_offset_minutes,
        }
        if gap:
            content["in_dark_gap"] = {
                "gap_start_ts": iso(gap["gap_start_ts"]),
                "gap_end_ts": iso(gap["gap_end_ts"]),
                "duration": fmt_duration(gap["gap_duration_seconds"]),
            }

        position = None
        if before and before_off == 0:
            content.update(status="ok", method="exact")
            position = point_json(before)
        elif nearest_off is not None and nearest_off <= s.position_max_offset_minutes:
            content["status"] = "ok"
            if before and after and minutes_between(before.ts, after.ts) <= s.interpolation_max_gap_minutes:
                lat, lon = interpolate(before, after, ts)
                content["method"] = "interpolated"
                position = {"ts": iso(ts), "lat": round(lat, 5), "lon": round(lon, 5)}
            else:
                nearest = before if before_off == nearest_off else after
                content["method"] = "nearest_point"
                position = point_json(nearest)
        else:
            content["status"] = "no_data_near_time"
            if not before:
                content["message"] = "Thời điểm này trước điểm AIS đầu tiên của tàu."
            elif not after:
                content["message"] = "Thời điểm này sau điểm AIS cuối cùng của tàu."
            else:
                content["message"] = "Không có điểm AIS đủ gần thời điểm này (tàu có thể mất tín hiệu hoặc ở ngoài vùng dữ liệu)."
        if position:
            content["position"] = position
        content["explanation"] = _position_explanation(content)

        features = []
        if position:
            features.append(feature(point_geom(position["lat"], position["lon"]), kind="position",
                                    label=f"{vessel_brief(v)['name']} @ {iso(ts)}", method=content["method"]))
        for p, role in ((before, "before"), (after, "after")):
            if p and not (position and content.get("method") == "exact" and role == "before"):
                features.append(feature(point_geom(p.lat, p.lon), kind="reference", role=role, ts=iso(p.ts)))
        map_data = []
        if features:
            coords = [tuple(f["geometry"]["coordinates"]) for f in features]
            map_data.append(MapPayload(
                kind="position",
                geojson=collection(features),
                summary={"vessel": vessel_brief(v), "requested_ts": iso(ts), "status": content["status"]},
                bbox=bbox_from_lonlats(coords),
            ))
        focus = {**vessel_focus(v), "time": iso(ts)}
        return ToolResult(content=content, map_data=map_data, focus=focus)


@register
class GetLastPosition(Tool):
    name = "get_last_position"
    description = "Vị trí cuối cùng có trong dữ liệu của một tàu (thời điểm, toạ độ, tốc độ, trạng thái). Hiển thị trên bản đồ."

    class Args(BaseModel):
        vessel: str = Field(description=VESSEL_ARG_DESC)

    async def run(self, ctx: ToolContext, args: Args) -> ToolResult:
        async with ctx.pool.acquire() as conn:
            v, problem = await resolve_vessel(conn, ctx.settings, args.vessel)
            if problem:
                return ToolResult(content=problem)
            last = await pos_repo.last_position(conn, v["vessel_id"])
        if not last:
            return ToolResult(content={"status": "no_data", "vessel": vessel_brief(v),
                                       "message": "Tàu không có điểm AIS nào trong dữ liệu."}, focus=vessel_focus(v))
        pos = point_json(last)
        payload = MapPayload(
            kind="position",
            geojson=collection([feature(point_geom(last.lat, last.lon), kind="position",
                                        label=f"{vessel_brief(v)['name']} @ {pos['ts']}", method="last")]),
            summary={"vessel": vessel_brief(v), "requested_ts": pos["ts"], "status": "ok"},
            bbox=[last.lon, last.lat, last.lon, last.lat],
        )
        return ToolResult(
            content={"status": "ok", "vessel": vessel_brief(v), "position": pos},
            map_data=[payload],
            focus={**vessel_focus(v), "time": pos["ts"]},
        )


def _coverage_warnings(start, end, pts, stats, tolerance_minutes: float) -> list[str]:
    """Cảnh báo sinh từ dữ liệu khi hành trình không phủ hết khoảng thời gian được hỏi."""
    warnings = []
    if minutes_between(start, pts[0].ts) > tolerance_minutes:
        warnings.append(f"Điểm AIS đầu tiên trong khoảng hỏi là {iso(pts[0].ts)} (muộn hơn thời điểm bắt đầu {iso(start)}).")
    if minutes_between(pts[-1].ts, end) > tolerance_minutes:
        warnings.append(f"Điểm AIS cuối cùng trong khoảng hỏi là {iso(pts[-1].ts)} (sớm hơn thời điểm kết thúc {iso(end)}); "
                        "sau đó không có dữ liệu (tàu có thể mất tín hiệu hoặc rời vùng dữ liệu).")
    for g in stats["gaps"]:
        warnings.append(f"Không có dữ liệu từ {g['from']} đến {g['to']} ({g['hours']} giờ); "
                        f"{g['distance_nm']} hải lý của quãng đường là khoảng cách thẳng qua khe này.")
    if warnings:
        warnings.append("Vì vậy quãng đường chỉ phản ánh phần có dữ liệu; cần nói rõ điều này khi so sánh.")
    return warnings


@register
class GetTrack(Tool):
    name = "get_track"
    description = (
        "Hành trình của một tàu trong khoảng thời gian (UTC): điểm đầu, điểm cuối, số điểm, quãng đường (hải lý), "
        "tốc độ trung bình, các khe không có dữ liệu, cảng đích tàu tự khai báo. Điểm GPS nhảy bất thường đã được "
        "loại. Hành trình được vẽ lên bản đồ. Dùng lần lượt cho từng ngày khi cần so sánh các ngày."
    )

    class Args(BaseModel):
        vessel: str = Field(description=VESSEL_ARG_DESC)
        start: str = Field(description="Bắt đầu, " + TIME_ARG_DESC)
        end: str = Field(description="Kết thúc, " + TIME_ARG_DESC + " Chỉ ghi ngày nghĩa là hết ngày đó.")

    async def run(self, ctx: ToolContext, args: Args) -> ToolResult:
        s = ctx.settings
        start, end = parse_range(args.start, args.end)
        async with ctx.pool.acquire() as conn:
            v, problem = await resolve_vessel(conn, s, args.vessel)
            if problem:
                return ToolResult(content=problem)
            raw = await pos_repo.positions_between(conn, v["vessel_id"], start, end)
            dests = await pos_repo.destinations_between(conn, v["vessel_id"], start, end) if raw else []
            before = after = None
            if not raw:
                before, _ = await pos_repo.nearest_positions(conn, v["vessel_id"], start)
                after = await pos_repo.first_at_or_after(conn, v["vessel_id"], end)

        focus = {**vessel_focus(v), "time_range": time_range_json(start, end)}
        base = {"vessel": vessel_brief(v), "time_range": time_range_json(start, end)}
        if not raw:
            return ToolResult(
                content={**base, "status": "no_data",
                         "message": "Không có điểm AIS nào của tàu trong khoảng thời gian này.",
                         "last_before": point_json(before), "first_after": point_json(after)},
                focus=focus,
            )

        pts, removed = filter_jumps(raw, s.max_plausible_speed_knots)
        stats = track_stats(pts, s.track_gap_split_hours)
        max_rows = s.tool_result_max_rows
        content = {
            **base,
            "status": "ok",
            "raw_point_count": len(raw),
            "removed_noise_points": removed,
            "point_count": stats["point_count"],
            "start": point_json(pts[0]),
            "end": point_json(pts[-1]),
            "distance_nm": stats["distance_nm"],
            "gap_distance_nm": stats["gap_distance_nm"],
            "duration_hours": stats["duration_hours"],
            "avg_speed_knots": stats["avg_speed_knots"],
            "gaps": stats["gaps"][:max_rows],
            "reported_destinations": dests[:max_rows],
            "bbox": bbox_of(pts),
            "note": "distance_nm tính theo đường nối các điểm AIS liên tiếp; gap_distance_nm là phần đi qua các khe "
                    "không có dữ liệu (tính đường thẳng).",
        }
        warnings = _coverage_warnings(start, end, pts, stats, s.position_max_offset_minutes)
        if warnings:
            content["coverage_warnings"] = warnings
        name = vessel_brief(v)["name"]
        features = [
            feature(track_geometry(pts, s.track_gap_split_hours), kind="track", name=name,
                    vessel_id=v["vessel_id"], distance_nm=stats["distance_nm"]),
            feature(point_geom(pts[0].lat, pts[0].lon), kind="track_start", name=name, ts=iso(pts[0].ts)),
            feature(point_geom(pts[-1].lat, pts[-1].lon), kind="track_end", name=name, ts=iso(pts[-1].ts)),
        ]
        payload = MapPayload(
            kind="track",
            geojson=collection(features),
            summary={"vessel": vessel_brief(v), "time_range": base["time_range"],
                     "distance_nm": stats["distance_nm"], "point_count": stats["point_count"]},
            bbox=content["bbox"],
        )
        return ToolResult(content=content, map_data=[payload], focus=focus)


@register
class GetMultiTracks(Tool):
    name = "get_multi_tracks"
    description = (
        "Vẽ hành trình của NHIỀU tàu lên bản đồ trong khoảng thời gian (UTC), lọc theo công ty (+ vai trò) và/hoặc "
        "nhóm loại tàu (tanker = tàu chở dầu/hoá chất/khí, cargo = tàu hàng/container/hàng rời, fishing = tàu cá, "
        "tug = tàu kéo, passenger = tàu khách). Dữ liệu điểm đi thẳng lên bản đồ; tool chỉ trả tóm tắt: số tàu, "
        "số điểm, khung toạ độ và danh sách tàu xếp theo quãng đường giảm dần."
    )

    class Args(BaseModel):
        start: str = Field(description="Bắt đầu, " + TIME_ARG_DESC)
        end: str = Field(description="Kết thúc, " + TIME_ARG_DESC + " Chỉ ghi ngày nghĩa là hết ngày đó.")
        company_name: str | None = Field(default=None, description="Lọc theo công ty")
        role: Role | None = Field(default=None, description="Vai trò của công ty; 'khai thác' = operator")
        ship_type_group: ShipTypeGroup | None = Field(default=None, description="Lọc theo nhóm loại tàu")

    async def run(self, ctx: ToolContext, args: Args) -> ToolResult:
        s = ctx.settings
        start, end = parse_range(args.start, args.end)
        company = None
        others: list[str] = []
        async with ctx.pool.acquire() as conn:
            if args.company_name:
                company, others, problem = await resolve_company(conn, s, args.company_name)
                if problem:
                    return ToolResult(content=problem)
            vessels = await vessel_repo.vessels_by_filter(
                conn,
                company_norms=[company["company_norm"]] if company else None,
                role=args.role,
                ship_type_group=args.ship_type_group,
                limit=s.multi_track_max_vessels + 1,
            )
            capped = len(vessels) > s.multi_track_max_vessels
            vessels = vessels[: s.multi_track_max_vessels]
            positions = await pos_repo.positions_for_vessels(conn, [v["vessel_id"] for v in vessels], start, end)

        fc, per_vessel, totals = build_multi_tracks(vessels, positions, s, s.multi_track_max_points)
        max_rows = s.tool_result_max_rows
        filters = {"company": company["company_norm"] if company else None, "role": args.role,
                   "ship_type_group": args.ship_type_group, **time_range_json(start, end)}
        content = {
            "status": "ok" if per_vessel else "no_data",
            "filters": filters,
            "company": {"norm": company["company_norm"], "name_variants": company["variants"]} if company else None,
            "similar_companies_not_included": others,
            "matched_vessels": len(vessels),
            "matched_vessels_capped": capped,
            "vessels_without_data": len(vessels) - totals["vessels_with_data"],
            **totals,
            "top_by_distance": [
                {k: p[k] for k in ("vessel_id", "name", "mmsi", "distance_nm", "avg_speed_knots", "point_count")}
                for p in per_vessel[:max_rows]
            ],
            "list_truncated": len(per_vessel) > max_rows,
        }
        focus = {"time_range": time_range_json(start, end), "multi_track": filters}
        if company:
            focus.update(company_focus(company))
        map_data = []
        if per_vessel:
            map_data.append(MapPayload(
                kind="tracks",
                geojson=fc,
                summary={"filters": filters, **totals, "vessels": per_vessel},
                bbox=totals["bbox"],
            ))
        return ToolResult(content=content, map_data=map_data, focus=focus)
