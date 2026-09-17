"""Truy vấn sự kiện mất tín hiệu AIS (dark gap)."""

from datetime import datetime

import asyncpg

# Giá trị order_by được ánh xạ sang đoạn SQL cố định (không ghép chuỗi từ người dùng)
_ORDER = {
    "duration": "g.gap_duration_seconds DESC",
    "start": "g.gap_start_ts",
    "distance": "g.distance_nm DESC NULLS LAST",
}


async def list_gaps(
    conn: asyncpg.Connection,
    vessel_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    order_by: str = "start",
    limit: int = 50,
) -> list[dict]:
    order = _ORDER.get(order_by)
    if order is None:
        raise ValueError(f"order_by không hợp lệ: {order_by}")
    rows = await conn.fetch(
        f"""
        SELECT g.gap_id::text AS gap_id, g.vessel_id::text AS vessel_id, g.mmsi, v.shipname,
               g.gap_start_ts, g.gap_end_ts, g.gap_duration_seconds, g.distance_nm, g.implied_speed_knots,
               g.start_lat, g.start_lon, g.end_lat, g.end_lon
        FROM dark_gaps g
        LEFT JOIN vessels v ON v.vessel_id = g.vessel_id
        WHERE ($1::uuid IS NULL OR g.vessel_id = $1)
          AND ($2::timestamptz IS NULL OR g.gap_end_ts >= $2)
          AND ($3::timestamptz IS NULL OR g.gap_start_ts <= $3)
        ORDER BY {order}, g.gap_id
        LIMIT $4
        """,
        vessel_id, start, end, limit,
    )
    return [dict(r) for r in rows]


async def count_gaps(conn: asyncpg.Connection, vessel_id: str | None = None) -> int:
    return await conn.fetchval(
        "SELECT count(*) FROM dark_gaps WHERE ($1::uuid IS NULL OR vessel_id = $1)", vessel_id
    )
