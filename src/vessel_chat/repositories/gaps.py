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
    """Các sự kiện mất tín hiệu kèm điểm AIS ngay trước khi mất và ngay khi có lại (một truy vấn duy nhất)."""
    order = _ORDER.get(order_by)
    if order is None:
        raise ValueError(f"order_by không hợp lệ: {order_by}")
    rows = await conn.fetch(
        f"""
        WITH picked AS (
            SELECT g.* FROM dark_gaps g
            WHERE ($1::uuid IS NULL OR g.vessel_id = $1)
              AND ($2::timestamptz IS NULL OR g.gap_end_ts >= $2)
              AND ($3::timestamptz IS NULL OR g.gap_start_ts <= $3)
            ORDER BY {order}, g.gap_id
            LIMIT $4
        )
        SELECT g.gap_id::text AS gap_id, g.vessel_id::text AS vessel_id, g.mmsi, v.imo, v.shipname,
               g.gap_start_ts, g.gap_end_ts, g.gap_duration_seconds, g.distance_nm, g.implied_speed_knots,
               g.start_lat, g.start_lon, g.end_lat, g.end_lon,
               b.event_ts AS before_ts, b.speed_knots AS before_speed, b.nav_status AS before_status,
               a.event_ts AS after_ts, a.speed_knots AS after_speed, a.nav_status AS after_status
        FROM picked g
        LEFT JOIN vessels v ON v.vessel_id = g.vessel_id
        LEFT JOIN LATERAL (
            SELECT event_ts, speed_knots, nav_status FROM ais_positions p
            WHERE p.vessel_id = g.vessel_id AND p.event_ts <= g.gap_start_ts
            ORDER BY p.event_ts DESC LIMIT 1
        ) b ON true
        LEFT JOIN LATERAL (
            SELECT event_ts, speed_knots, nav_status FROM ais_positions p
            WHERE p.vessel_id = g.vessel_id AND p.event_ts >= g.gap_end_ts - interval '1 second'
            ORDER BY p.event_ts LIMIT 1
        ) a ON true
        ORDER BY {order}, g.gap_id
        """,
        vessel_id, start, end, limit,
    )
    return [dict(r) for r in rows]


async def count_gaps(
    conn: asyncpg.Connection,
    vessel_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> int:
    return await conn.fetchval(
        """
        SELECT count(*) FROM dark_gaps
        WHERE ($1::uuid IS NULL OR vessel_id = $1)
          AND ($2::timestamptz IS NULL OR gap_end_ts >= $2)
          AND ($3::timestamptz IS NULL OR gap_start_ts <= $3)
        """,
        vessel_id, start, end,
    )


async def gap_covering(conn: asyncpg.Connection, vessel_id: str, ts: datetime) -> dict | None:
    """Sự kiện mất tín hiệu bao trùm thời điểm ts (nếu có)."""
    row = await conn.fetchrow(
        """
        SELECT gap_start_ts, gap_end_ts, gap_duration_seconds
        FROM dark_gaps WHERE vessel_id = $1 AND gap_start_ts <= $2 AND gap_end_ts >= $2
        ORDER BY gap_start_ts LIMIT 1
        """,
        vessel_id, ts,
    )
    return dict(row) if row else None
