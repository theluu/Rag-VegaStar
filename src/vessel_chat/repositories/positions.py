"""Truy vấn vị trí AIS (dùng chỉ mục (vessel_id, event_ts))."""

from datetime import datetime

import asyncpg

from ..geo import Point

_COLS = "event_ts, lat, lon, speed_knots, course_deg, nav_status"


def _point(r) -> Point:
    return Point(
        ts=r["event_ts"], lat=r["lat"], lon=r["lon"],
        speed=r["speed_knots"], course=r["course_deg"], nav_status=r["nav_status"],
    )


async def positions_between(conn: asyncpg.Connection, vessel_id: str, start: datetime, end: datetime) -> list[Point]:
    rows = await conn.fetch(
        f"SELECT {_COLS} FROM ais_positions WHERE vessel_id = $1 AND event_ts BETWEEN $2 AND $3 ORDER BY event_ts",
        vessel_id, start, end,
    )
    return [_point(r) for r in rows]


async def nearest_positions(
    conn: asyncpg.Connection, vessel_id: str, ts: datetime
) -> tuple[Point | None, Point | None]:
    """Điểm gần nhất tại/trước và sau thời điểm ts."""
    before = await conn.fetchrow(
        f"SELECT {_COLS} FROM ais_positions WHERE vessel_id = $1 AND event_ts <= $2 ORDER BY event_ts DESC LIMIT 1",
        vessel_id, ts,
    )
    after = await conn.fetchrow(
        f"SELECT {_COLS} FROM ais_positions WHERE vessel_id = $1 AND event_ts > $2 ORDER BY event_ts LIMIT 1",
        vessel_id, ts,
    )
    return (_point(before) if before else None, _point(after) if after else None)


async def last_position(conn: asyncpg.Connection, vessel_id: str) -> Point | None:
    row = await conn.fetchrow(
        f"SELECT {_COLS} FROM ais_positions WHERE vessel_id = $1 ORDER BY event_ts DESC LIMIT 1", vessel_id
    )
    return _point(row) if row else None


async def data_time_range(conn: asyncpg.Connection) -> tuple[datetime | None, datetime | None]:
    row = await conn.fetchrow("SELECT min(event_ts) AS a, max(event_ts) AS b FROM ais_positions")
    return row["a"], row["b"]


async def positions_for_vessels(
    conn: asyncpg.Connection, vessel_ids: list[str], start: datetime, end: datetime
) -> dict[str, list[Point]]:
    rows = await conn.fetch(
        f"""
        SELECT vessel_id::text AS vessel_id, {_COLS}
        FROM ais_positions
        WHERE vessel_id = ANY($1::uuid[]) AND event_ts BETWEEN $2 AND $3
        ORDER BY vessel_id, event_ts
        """,
        vessel_ids, start, end,
    )
    out: dict[str, list[Point]] = {}
    for r in rows:
        out.setdefault(r["vessel_id"], []).append(_point(r))
    return out


async def first_at_or_after(conn: asyncpg.Connection, vessel_id: str, ts: datetime) -> Point | None:
    row = await conn.fetchrow(
        f"SELECT {_COLS} FROM ais_positions WHERE vessel_id = $1 AND event_ts >= $2 ORDER BY event_ts LIMIT 1",
        vessel_id, ts,
    )
    return _point(row) if row else None


async def vessel_ais_summary(conn: asyncpg.Connection, vessel_id: str) -> dict:
    row = await conn.fetchrow(
        """
        SELECT count(*) AS position_count, min(event_ts) AS first_ts, max(event_ts) AS last_ts
        FROM ais_positions WHERE vessel_id = $1
        """,
        vessel_id,
    )
    return dict(row)


async def destinations_between(conn: asyncpg.Connection, vessel_id: str, start: datetime, end: datetime) -> list[str]:
    """Các cảng đích tàu tự khai báo (reported_dest), theo thứ tự xuất hiện."""
    rows = await conn.fetch(
        """
        SELECT reported_dest, min(event_ts) AS first_seen
        FROM ais_positions
        WHERE vessel_id = $1 AND event_ts BETWEEN $2 AND $3 AND coalesce(reported_dest, '') <> ''
        GROUP BY reported_dest
        ORDER BY first_seen
        """,
        vessel_id, start, end,
    )
    return [r["reported_dest"] for r in rows]
