"""Nạp 4 file CSV vào PostgreSQL.

Chạy lại nhiều lần không nhân đôi: toàn bộ được làm trong MỘT transaction —
COPY vào bảng tạm → TRUNCATE bảng đích → INSERT ... SELECT (dựng geometry, cột chuẩn hoá).
Bảng hội thoại/bộ nhớ không bị động tới.
"""

import csv
import logging
import time
import uuid
from datetime import date
from pathlib import Path

import asyncpg

from .normalize import norm_company, norm_name, ship_type_group
from .timeutil import parse_ts

log = logging.getLogger(__name__)

FILES = {
    "vessels": "vessels.csv",
    "ais_positions": "ais_positions.csv",
    "dark_gaps": "dark_gaps.csv",
    "ownership": "ownership.csv",
}


def _s(v: str | None) -> str | None:
    v = (v or "").strip()
    return v or None


def _f(v: str | None) -> float | None:
    v = _s(v)
    return float(v) if v is not None else None


def _i(v: str | None) -> int | None:
    x = _f(v)
    return int(round(x)) if x is not None else None


def _ts(v: str | None):
    v = _s(v)
    return parse_ts(v) if v else None


def _d(v: str | None) -> date | None:
    v = _s(v)
    return date.fromisoformat(v[:10]) if v else None


def _read(path: Path, convert) -> tuple[list[tuple], int]:
    rows, skipped = [], 0
    with path.open(newline="", encoding="utf-8") as f:
        for i, raw in enumerate(csv.DictReader(f), start=2):
            try:
                rows.append(convert(raw))
            except (ValueError, TypeError) as exc:
                skipped += 1
                log.warning("%s dòng %d bị bỏ qua: %s", path.name, i, exc)
    return rows, skipped


def _vessel(r: dict) -> tuple:
    name = _s(r["shipname"])
    summary = _s(r["ship_type_summary"])
    return (
        uuid.UUID(r["vessel_id"]), _i(r["mmsi"]), _i(r["imo"]), name, norm_name(name), _s(r["callsign"]),
        _s(r["flag_code"]), _s(r["flag"]), summary, ship_type_group(summary), _s(r["ship_type_detail_name"]),
        _f(r["length_m"]), _f(r["width_m"]), _f(r["dwt"]), _f(r["grt"]), _i(r["year_built"]),
    )


def _position(r: dict) -> tuple:
    lat, lon = float(r["lat"]), float(r["lon"])
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"toạ độ không hợp lệ {lat},{lon}")
    return (
        uuid.UUID(r["vessel_id"]), _i(r["mmsi"]), parse_ts(r["event_ts"]), lat, lon,
        _f(r["speed_knots"]), _f(r["course_deg"]), _f(r["heading_deg"]), _s(r["nav_status"]),
        _s(r.get("reported_dest")), _f(r["draught_m"]),
    )


def _gap(r: dict) -> tuple:
    return (
        uuid.UUID(r["gap_id"]), uuid.UUID(r["vessel_id"]), _i(r["mmsi"]), _ts(r["gap_start_ts"]), _ts(r["gap_end_ts"]),
        _i(r["gap_duration_seconds"]), _f(r["distance_nm"]), _f(r["implied_speed_knots"]),
        _f(r["start_lat"]), _f(r["start_lon"]), _f(r["end_lat"]), _f(r["end_lon"]),
    )


def _owner(r: dict) -> tuple:
    name = _s(r["company_name"])
    if not name:
        raise ValueError("thiếu company_name")
    return (
        uuid.UUID(r["vessel_id"]), r["role"].strip(), name, norm_company(name),
        _s(r["company_country"]), _d(r["start_date"]),
    )


STAGING = """
CREATE TEMP TABLE stg_vessels (LIKE vessels) ON COMMIT DROP;
CREATE TEMP TABLE stg_positions (
    vessel_id uuid, mmsi bigint, event_ts timestamptz, lat double precision, lon double precision,
    speed_knots double precision, course_deg double precision, heading_deg double precision,
    nav_status text, reported_dest text, draught_m double precision
) ON COMMIT DROP;
CREATE TEMP TABLE stg_gaps (
    gap_id uuid, vessel_id uuid, mmsi bigint, gap_start_ts timestamptz, gap_end_ts timestamptz,
    gap_duration_seconds bigint, distance_nm double precision, implied_speed_knots double precision,
    start_lat double precision, start_lon double precision, end_lat double precision, end_lon double precision
) ON COMMIT DROP;
CREATE TEMP TABLE stg_ownership (
    vessel_id uuid, role text, company_name text, company_norm text, company_country text, start_date date
) ON COMMIT DROP;
"""

PUBLISH = """
TRUNCATE vessels, ais_positions, dark_gaps, ownership RESTART IDENTITY;
INSERT INTO vessels SELECT DISTINCT ON (vessel_id) * FROM stg_vessels;
INSERT INTO ais_positions
    SELECT vessel_id, mmsi, event_ts, lat, lon, ST_SetSRID(ST_MakePoint(lon, lat), 4326),
           speed_knots, course_deg, heading_deg, nav_status, reported_dest, draught_m
    FROM stg_positions;
INSERT INTO dark_gaps
    SELECT DISTINCT ON (gap_id) g.*,
           ST_SetSRID(ST_MakePoint(start_lon, start_lat), 4326),
           ST_SetSRID(ST_MakePoint(end_lon, end_lat), 4326),
           ST_MakeLine(ST_SetSRID(ST_MakePoint(start_lon, start_lat), 4326),
                       ST_SetSRID(ST_MakePoint(end_lon, end_lat), 4326))
    FROM stg_gaps g;
INSERT INTO ownership (vessel_id, role, company_name, company_norm, company_country, start_date)
    SELECT DISTINCT vessel_id, role, company_name, company_norm, company_country, start_date FROM stg_ownership;
"""


async def load_all(conn: asyncpg.Connection, data_dir: str | Path) -> dict[str, int]:
    data_dir = Path(data_dir)
    missing = [n for n in FILES.values() if not (data_dir / n).exists()]
    if missing:
        raise FileNotFoundError(f"Không tìm thấy {missing} trong {data_dir}")

    started = time.perf_counter()
    vessels, s1 = _read(data_dir / FILES["vessels"], _vessel)
    positions, s2 = _read(data_dir / FILES["ais_positions"], _position)
    gaps, s3 = _read(data_dir / FILES["dark_gaps"], _gap)
    owners, s4 = _read(data_dir / FILES["ownership"], _owner)
    if s1 + s2 + s3 + s4:
        log.warning("Bỏ qua dòng lỗi: vessels=%d positions=%d gaps=%d ownership=%d", s1, s2, s3, s4)

    async with conn.transaction():
        await conn.execute(STAGING)
        await conn.copy_records_to_table("stg_vessels", records=vessels)
        await conn.copy_records_to_table("stg_positions", records=positions)
        await conn.copy_records_to_table("stg_gaps", records=gaps)
        await conn.copy_records_to_table("stg_ownership", records=owners)
        await conn.execute(PUBLISH)
    await conn.execute("ANALYZE vessels; ANALYZE ais_positions; ANALYZE dark_gaps; ANALYZE ownership;")

    counts = {t: await conn.fetchval(f"SELECT count(*) FROM {t}") for t in FILES}
    log.info("Nạp xong trong %.1fs: %s", time.perf_counter() - started, counts)
    return counts
