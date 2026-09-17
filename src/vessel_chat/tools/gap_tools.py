from typing import Literal

from pydantic import BaseModel, Field

from ..repositories import gaps as gap_repo
from ..timeutil import iso
from .base import MapPayload, Tool, ToolContext, ToolResult, register
from .common import (
    VESSEL_ARG_DESC,
    bbox_from_lonlats,
    collection,
    feature,
    fmt_duration,
    parse_time_arg,
    point_geom,
    resolve_vessel,
    vessel_brief,
    vessel_focus,
)


def _pos(lat, lon):
    return None if lat is None else {"lat": round(lat, 5), "lon": round(lon, 5)}


def _speed(ts, speed, status):
    if ts is None:
        return None
    return {"ts": iso(ts), "speed_knots": None if speed is None else round(speed, 1), "nav_status": status or None}


@register
class GetDarkGaps(Tool):
    name = "get_dark_gaps"
    description = (
        "Các lần tàu mất tín hiệu AIS (≥ 3 giờ): thời gian mất/có lại, độ dài, vị trí mất và vị trí xuất hiện lại, "
        "khoảng cách thẳng, tốc độ báo cáo ngay trước khi mất và ngay sau khi có lại. Bỏ trống vessel để tìm trên "
        "toàn bộ đội tàu (vd. order_by=duration, limit=1 cho lần mất tín hiệu lâu nhất). Hiển thị trên bản đồ."
    )

    class Args(BaseModel):
        vessel: str | None = Field(default=None, description=VESSEL_ARG_DESC + " Bỏ trống = mọi tàu.")
        start: str | None = Field(default=None, description="Chỉ lấy sự kiện kết thúc sau thời điểm này (UTC)")
        end: str | None = Field(default=None, description="Chỉ lấy sự kiện bắt đầu trước thời điểm này (UTC)")
        order_by: Literal["start", "duration", "distance"] = Field(
            default="start", description="start = theo thời gian; duration = lâu nhất trước; distance = xa nhất trước"
        )
        limit: int = Field(default=10, ge=1, le=50)

    async def run(self, ctx: ToolContext, args: Args) -> ToolResult:
        s = ctx.settings
        start = parse_time_arg(args.start, "start") if args.start else None
        end = parse_time_arg(args.end, "end") if args.end else None
        limit = min(args.limit, s.tool_result_max_rows)
        async with ctx.pool.acquire() as conn:
            v = None
            if args.vessel:
                v, problem = await resolve_vessel(conn, s, args.vessel)
                if problem:
                    return ToolResult(content=problem)
            vid = v["vessel_id"] if v else None
            rows = await gap_repo.list_gaps(conn, vid, start, end, order_by=args.order_by, limit=limit)
            total = await gap_repo.count_gaps(conn, vid, start, end)
        gaps = []
        for g in rows:
            gaps.append({
                "gap_id": g["gap_id"],
                "vessel": vessel_brief(g),
                "gap_start_ts": iso(g["gap_start_ts"]),
                "gap_end_ts": iso(g["gap_end_ts"]),
                "duration_seconds": g["gap_duration_seconds"],
                "duration_hours": round(g["gap_duration_seconds"] / 3600, 2),
                "duration_text": fmt_duration(g["gap_duration_seconds"]),
                "start_position": _pos(g["start_lat"], g["start_lon"]),
                "end_position": _pos(g["end_lat"], g["end_lon"]),
                "straight_distance_nm": None if g["distance_nm"] is None else round(g["distance_nm"], 2),
                "implied_speed_knots": None if g["implied_speed_knots"] is None else round(g["implied_speed_knots"], 2),
                "speed_before_gap": _speed(g["before_ts"], g["before_speed"], g["before_status"]),
                "speed_after_gap": _speed(g["after_ts"], g["after_speed"], g["after_status"]),
            })

        content = {
            "status": "ok",
            "vessel": vessel_brief(v) if v else None,
            "scope": "one_vessel" if v else "all_vessels",
            "order_by": args.order_by,
            "total_matching": total,
            "returned": len(gaps),
            "gaps": gaps,
        }
        if not gaps:
            content["message"] = "Không có sự kiện mất tín hiệu AIS nào khớp điều kiện."

        focus = {}
        if v:
            focus = vessel_focus(v)
        elif gaps:
            focus = {"vessel": gaps[0]["vessel"]}

        map_data = []
        if gaps:
            features, coords = [], []
            for g in gaps:
                sp, ep = g["start_position"], g["end_position"]
                name = g["vessel"]["name"]
                if sp:
                    features.append(feature(point_geom(sp["lat"], sp["lon"]), kind="gap_start", name=name,
                                            ts=g["gap_start_ts"], duration=g["duration_text"]))
                    coords.append((sp["lon"], sp["lat"]))
                if ep:
                    features.append(feature(point_geom(ep["lat"], ep["lon"]), kind="gap_end", name=name,
                                            ts=g["gap_end_ts"], duration=g["duration_text"]))
                    coords.append((ep["lon"], ep["lat"]))
                if sp and ep:
                    features.append(feature(
                        {"type": "LineString", "coordinates": [[sp["lon"], sp["lat"]], [ep["lon"], ep["lat"]]]},
                        kind="gap_link", name=name, duration=g["duration_text"],
                    ))
            map_data.append(MapPayload(
                kind="gaps",
                geojson=collection(features),
                summary={"vessel": content["vessel"], "count": len(gaps), "total_matching": total},
                bbox=bbox_from_lonlats(coords),
            ))
        return ToolResult(content=content, map_data=map_data, focus=focus)
