"""Hàm dùng chung giữa các tool: phân giải tàu/công ty, định dạng, dựng GeoJSON."""

from datetime import datetime
from typing import Literal

import asyncpg

from ..config import Settings
from ..repositories import vessels as vessel_repo
from ..timeutil import iso, parse_ts
from .base import ToolInputError

Role = Literal[
    "registered_owner", "beneficial_owner", "operator",
    "commercial_manager", "technical_manager", "ism_manager",
]
ShipTypeGroup = Literal[
    "tanker", "cargo", "fishing", "tug", "passenger", "high_speed", "pleasure", "special", "other", "unknown",
]

VESSEL_ARG_DESC = (
    "Tàu cần tra: tên tàu (không phân biệt hoa thường, chấp nhận sai chính tả nhẹ), MMSI (9 số), "
    "IMO (7 số), callsign, hoặc vessel_id lấy từ kết quả tool trước. Ưu tiên vessel_id khi đã biết."
)
TIME_ARG_DESC = "Thời điểm ISO-8601 theo UTC, vd. 2026-09-11T21:00:00Z. Không có múi giờ thì coi là UTC."

# Khớp mờ: chấp nhận ứng viên đứng đầu khi đủ cao và bỏ xa ứng viên thứ hai
AUTO_PICK_MIN_SCORE = 0.6
AUTO_PICK_MARGIN = 0.2


def parse_time_arg(value: str, field: str) -> datetime:
    try:
        return parse_ts(value)
    except (ValueError, TypeError):
        raise ToolInputError(f"{field} không phải thời gian ISO-8601 hợp lệ: {value!r}") from None


def parse_range(start: str, end: str) -> tuple[datetime, datetime]:
    s, e = parse_time_arg(start, "start"), parse_time_arg(end, "end")
    # "đến 2026-09-12" (chỉ có ngày) nghĩa là hết ngày 12
    if len(end.strip()) == 10:
        e = e.replace(hour=23, minute=59, second=59)
    if e <= s:
        raise ToolInputError("end phải sau start")
    return s, e


def vessel_brief(v: dict) -> dict:
    return {
        "vessel_id": v["vessel_id"],
        "name": v.get("shipname") or "(không tên)",
        "mmsi": v.get("mmsi"),
        "imo": v.get("imo"),
    }


def vessel_focus(v: dict) -> dict:
    return {"vessel": vessel_brief(v)}


def fmt_duration(seconds: float) -> str:
    minutes = int(round(seconds / 60))
    h, m = divmod(minutes, 60)
    d, h = divmod(h, 24)
    parts = ([f"{d} ngày"] if d else []) + ([f"{h} giờ"] if h or d else []) + [f"{m} phút"]
    return " ".join(parts)


def minutes_between(a: datetime, b: datetime) -> float:
    return round(abs((b - a).total_seconds()) / 60, 1)


async def resolve_vessel(conn: asyncpg.Connection, settings: Settings, query: str) -> tuple[dict | None, dict | None]:
    """Trả (tàu, None) khi xác định được duy nhất, hoặc (None, nội dung báo lỗi/ứng viên)."""
    results = await vessel_repo.search_vessels(conn, query, limit=8, threshold=settings.vessel_match_threshold)
    if not results:
        return None, {
            "status": "not_found",
            "query": query,
            "message": "Không tìm thấy tàu nào khớp trong dữ liệu.",
        }
    top = results[0]
    exact = [r for r in results if r["score"] >= 1.0]
    if len(results) == 1 or len(exact) == 1:
        chosen = exact[0] if exact else top
    elif not exact and top["score"] >= AUTO_PICK_MIN_SCORE and top["score"] - results[1]["score"] >= AUTO_PICK_MARGIN:
        chosen = top
    else:
        return None, {
            "status": "ambiguous",
            "query": query,
            "message": "Có nhiều tàu khớp; hãy hỏi lại người dùng muốn tàu nào (nêu tên, MMSI, cờ).",
            "candidates": [
                {**vessel_brief(r), "flag": r["flag"], "ship_type": r["ship_type_summary"], "match_score": round(r["score"], 2)}
                for r in results
            ],
        }
    vessel = await vessel_repo.get_vessel(conn, chosen["vessel_id"])
    if chosen["score"] < 1.0:
        vessel["_matched_approximately"] = True
    return vessel, None


async def resolve_company(
    conn: asyncpg.Connection, settings: Settings, name: str
) -> tuple[dict | None, list[str], dict | None]:
    """Trả (công ty đã chọn, các công ty tương tự không gộp vào, nội dung lỗi/ứng viên)."""
    matches = await vessel_repo.match_companies(conn, name, threshold=settings.company_match_threshold)
    if not matches:
        return None, [], {"status": "not_found", "query": name, "message": "Không tìm thấy công ty nào khớp."}
    exact = [m for m in matches if m["exact"]]
    if exact:
        chosen = exact[0]
    elif len(matches) == 1 or (
        matches[0]["score"] >= AUTO_PICK_MIN_SCORE and matches[0]["score"] - matches[1]["score"] >= AUTO_PICK_MARGIN
    ):
        chosen = matches[0]
    else:
        return None, [], {
            "status": "ambiguous",
            "query": name,
            "message": "Có nhiều công ty khớp; hãy hỏi lại người dùng hoặc chọn đúng tên đầy đủ.",
            "candidates": [
                {"company": m["company_norm"], "name_variants": m["variants"], "roles": m["roles"],
                 "vessel_count": m["vessel_count"]}
                for m in matches
            ],
        }
    others = [m["company_norm"] for m in matches if m is not chosen]
    return chosen, others, None


def company_focus(company: dict) -> dict:
    return {"company": {"norm": company["company_norm"], "name": company["variants"][0]}}


def feature(geometry: dict, **props) -> dict:
    return {"type": "Feature", "geometry": geometry, "properties": props}


def point_geom(lat: float, lon: float) -> dict:
    return {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]}


def collection(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def bbox_from_lonlats(coords: list[tuple[float, float]]) -> list[float] | None:
    if not coords:
        return None
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return [min(lons), min(lats), max(lons), max(lats)]


def time_range_json(start: datetime, end: datetime) -> dict:
    return {"start": iso(start), "end": iso(end)}
