"""Tính đáp án bằng SQL trực tiếp để đối chiếu với câu trả lời của chatbot.

    python scripts/verify_facts.py                  # chạy scenarios/fact_checks.yaml → results/facts.md

Độc lập với tầng tool: quãng đường đo bằng PostGIS (geography, mét → hải lý) trên điểm thô, không lọc nhiễu,
nên có thể chênh rất nhỏ so với tool (tool dùng haversine và loại điểm GPS nhảy).
"""

import asyncio
from datetime import date
from pathlib import Path

import asyncpg
import yaml

from vessel_chat.config import get_settings
from vessel_chat.normalize import norm_company
from vessel_chat.timeutil import parse_ts

ROOT = Path(__file__).resolve().parent.parent
NM = 1852.0


def table(rows: list, cols: list[str] | None = None) -> str:
    if not rows:
        return "_(không có dòng nào)_\n"
    cols = cols or list(rows[0].keys())
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join("" if r[c] is None else str(r[c]) for c in cols) + " |")
    return "\n".join(out) + "\n"


async def vessel_id(conn, name=None, mmsi=None):
    if mmsi:
        return await conn.fetchval("SELECT vessel_id FROM vessels WHERE mmsi = $1", int(mmsi))
    return await conn.fetchval("SELECT vessel_id FROM vessels WHERE upper(shipname) = upper($1)", name)


async def check(conn, c: dict) -> str:
    kind = c["check"]
    vid = await vessel_id(conn, c.get("vessel"), c.get("mmsi")) if (c.get("vessel") or c.get("mmsi")) else None
    if kind == "vessel":
        v = await conn.fetch("SELECT shipname, mmsi, imo, callsign, flag, ship_type_summary, ship_type_detail_name, "
                             "length_m, width_m, dwt, grt, year_built FROM vessels WHERE vessel_id = $1", vid)
        o = await conn.fetch("SELECT role, company_name, company_country, start_date FROM ownership "
                             "WHERE vessel_id = $1 ORDER BY role", vid)
        return table([dict(r) for r in v]) + "\n" + table([dict(r) for r in o])
    if kind == "owner_fleet":
        rows = await conn.fetch(
            """SELECT DISTINCT v.shipname, v.mmsi, o2.company_name FROM ownership o1
               JOIN ownership o2 ON o2.company_norm = o1.company_norm AND o2.role = o1.role
               JOIN vessels v ON v.vessel_id = o2.vessel_id
               WHERE o1.vessel_id = $1 AND o1.role = $2 AND o2.vessel_id <> $1 ORDER BY 1""", vid, c["role"])
        return f"{len(rows)} tàu khác\n\n" + table([dict(r) for r in rows])
    if kind == "position_at":
        rows = await conn.fetch(
            """(SELECT 'trước' AS side, event_ts, lat, lon, speed_knots FROM ais_positions
                WHERE vessel_id = $1 AND event_ts <= $2::timestamptz ORDER BY event_ts DESC LIMIT 1)
               UNION ALL
               (SELECT 'sau', event_ts, lat, lon, speed_knots FROM ais_positions
                WHERE vessel_id = $1 AND event_ts > $2::timestamptz ORDER BY event_ts LIMIT 1)""",
            vid, parse_ts(c["ts"]))
        return table([dict(r) for r in rows])
    if kind == "daily_distance":
        out = []
        for day in c["days"]:
            r = await conn.fetchrow(
                """SELECT count(*) AS points, min(event_ts) AS first_ts, max(event_ts) AS last_ts,
                          round((ST_Length(ST_MakeLine(geom ORDER BY event_ts)::geography) / $3)::numeric, 2) AS distance_nm
                   FROM ais_positions WHERE vessel_id = $1
                     AND event_ts >= $2::date AND event_ts < $2::date + 1""", vid, date.fromisoformat(day), NM)
            first = await conn.fetchrow("SELECT lat, lon FROM ais_positions WHERE vessel_id=$1 AND event_ts=$2", vid, r["first_ts"])
            last = await conn.fetchrow("SELECT lat, lon FROM ais_positions WHERE vessel_id=$1 AND event_ts=$2", vid, r["last_ts"])
            out.append({"day": day, **dict(r), "first": first and (first["lat"], first["lon"]),
                        "last": last and (last["lat"], last["lon"])})
        return table(out)
    if kind == "gaps":
        rows = await conn.fetch(
            """SELECT gap_start_ts, gap_end_ts, round(gap_duration_seconds / 3600.0, 2) AS hours,
                      start_lat, start_lon, end_lat, end_lon FROM dark_gaps WHERE vessel_id = $1 ORDER BY 1""", vid)
        return table([dict(r) for r in rows])
    if kind == "last_position":
        r = await conn.fetch("SELECT event_ts, lat, lon, speed_knots, nav_status FROM ais_positions "
                             "WHERE vessel_id = $1 ORDER BY event_ts DESC LIMIT 1", vid)
        return table([dict(x) for x in r])
    if kind == "longest_gap":
        g = await conn.fetchrow("SELECT g.*, v.shipname FROM dark_gaps g JOIN vessels v USING (vessel_id) "
                                "ORDER BY gap_duration_seconds DESC LIMIT 1")
        owner = await conn.fetch("SELECT role, company_name FROM ownership WHERE vessel_id = $1", g["vessel_id"])
        before = await conn.fetchrow("SELECT event_ts, speed_knots FROM ais_positions WHERE vessel_id = $1 "
                                     "AND event_ts <= $2 ORDER BY event_ts DESC LIMIT 1", g["vessel_id"], g["gap_start_ts"])
        info = {k: g[k] for k in ("shipname", "mmsi", "gap_start_ts", "gap_end_ts", "gap_duration_seconds",
                                  "start_lat", "start_lon", "end_lat", "end_lon")}
        return (table([info]) + "\nChủ sở hữu/công ty:\n\n" + table([dict(r) for r in owner])
                + "\nĐiểm AIS cuối trước khi mất:\n\n" + table([dict(before)] if before else []))
    if kind == "company_tracks":
        rows = await conn.fetch(
            """SELECT v.shipname, v.mmsi, count(p.*) AS points,
                      round((ST_Length(ST_MakeLine(p.geom ORDER BY p.event_ts)::geography) / $5)::numeric, 2) AS distance_nm
               FROM vessels v JOIN ais_positions p USING (vessel_id)
               WHERE v.vessel_id IN (SELECT vessel_id FROM ownership WHERE company_norm = $1 AND role = $2)
                 AND p.event_ts >= $3::date AND p.event_ts < $4::date
               GROUP BY v.vessel_id ORDER BY distance_nm DESC""",
            norm_company(c["company"]), c["role"], date.fromisoformat(c["start"]), date.fromisoformat(c["end"]), NM)
        return f"{len(rows)} tàu có dữ liệu, tổng {sum(r['points'] for r in rows)} điểm\n\n" + table([dict(r) for r in rows[:10]])
    if kind == "type_day":
        r = await conn.fetchrow(
            """SELECT count(DISTINCT v.vessel_id) AS vessels_in_group,
                      count(DISTINCT p.vessel_id) AS vessels_with_data, count(p.*) AS points
               FROM vessels v LEFT JOIN ais_positions p
                 ON p.vessel_id = v.vessel_id AND p.event_ts >= $2::date AND p.event_ts < $2::date + 1
               WHERE v.ship_type_group = $1""", c["group"], date.fromisoformat(c["day"]))
        return table([dict(r)])
    raise ValueError(kind)


async def main() -> None:
    settings = get_settings()
    checks = yaml.safe_load((ROOT / "scenarios" / "fact_checks.yaml").read_text(encoding="utf-8"))
    conn = await asyncpg.connect(settings.database_url)
    parts = ["# Đáp án đối chiếu (SQL trực tiếp)", "",
             "Sinh bởi `scripts/verify_facts.py`. Quãng đường: PostGIS geography trên điểm thô.", ""]
    try:
        for c in checks:
            title = ", ".join(f"{k}={v}" for k, v in c.items())
            parts += [f"## {title}", "", await check(conn, c), ""]
    finally:
        await conn.close()
    out = ROOT / "results" / "facts.md"
    out.write_text("\n".join(parts), encoding="utf-8")
    print("Đã ghi", out)


if __name__ == "__main__":
    asyncio.run(main())
