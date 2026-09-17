"""Truy vấn thông tin tàu và chủ sở hữu. Mọi giá trị người dùng đi qua tham số $n."""

import re
import uuid

import asyncpg

from ..normalize import norm_company, norm_name

VESSEL_COLUMNS = """
    v.vessel_id::text AS vessel_id, v.mmsi, v.imo, v.shipname, v.callsign, v.flag_code, v.flag,
    v.ship_type_summary, v.ship_type_group, v.ship_type_detail_name,
    v.length_m, v.width_m, v.dwt, v.grt, v.year_built
"""

_ID_QUERY = re.compile(r"^\s*(?:(imo|mmsi)\s*(?:no\.?|number|số)?\s*[:#]?\s*)?(\d{5,10})\s*$", re.IGNORECASE)


def _is_uuid(text: str) -> bool:
    try:
        uuid.UUID(text)
        return True
    except ValueError:
        return False


async def search_vessels(conn: asyncpg.Connection, query: str, limit: int, threshold: float) -> list[dict]:
    """Tìm tàu theo vessel_id, MMSI, IMO, callsign hoặc tên (không phân biệt hoa thường, chịu sai chính tả)."""
    q = (query or "").strip()
    if not q:
        return []

    if _is_uuid(q):
        rows = await conn.fetch(
            f"SELECT {VESSEL_COLUMNS}, 1.0::float AS score, 'id' AS match FROM vessels v WHERE v.vessel_id = $1", q
        )
        return [dict(r) for r in rows]

    m = _ID_QUERY.match(q)
    if m:
        kind, number = (m.group(1) or "").lower(), int(m.group(2))
        rows = await conn.fetch(
            f"""
            SELECT {VESSEL_COLUMNS}, 1.0::float AS score,
                   CASE WHEN v.mmsi = $1 THEN 'mmsi' ELSE 'imo' END AS match
            FROM vessels v
            WHERE ($2 IN ('', 'mmsi') AND v.mmsi = $1) OR ($2 IN ('', 'imo') AND v.imo = $1)
            ORDER BY v.shipname NULLS LAST
            LIMIT $3
            """,
            number, kind, limit,
        )
        return [dict(r) for r in rows]

    name = norm_name(q)
    if not name:
        return []
    rows = await conn.fetch(
        f"""
        SELECT {VESSEL_COLUMNS}, s.score, s.match
        FROM vessels v
        CROSS JOIN LATERAL (
            SELECT CASE
                     WHEN v.shipname_norm = $1 THEN 1.0
                     WHEN upper(v.callsign) = $1 THEN 1.0
                     ELSE greatest(similarity(v.shipname_norm, $1), word_similarity($1, v.shipname_norm) * 0.95)
                   END::float AS score,
                   CASE WHEN upper(v.callsign) = $1 AND v.shipname_norm <> $1 THEN 'callsign' ELSE 'name' END AS match
        ) s
        WHERE v.shipname_norm <> '' OR upper(v.callsign) = $1
        ORDER BY s.score DESC, v.shipname_norm
        LIMIT $2
        """,
        name, limit * 3,
    )
    out = [dict(r) for r in rows if r["score"] >= threshold]
    return out[:limit]


async def get_vessel(conn: asyncpg.Connection, vessel_id: str) -> dict | None:
    row = await conn.fetchrow(f"SELECT {VESSEL_COLUMNS} FROM vessels v WHERE v.vessel_id = $1", vessel_id)
    return dict(row) if row else None


async def get_ownership(conn: asyncpg.Connection, vessel_id: str) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT role, company_name, company_norm, company_country, start_date
        FROM ownership WHERE vessel_id = $1
        ORDER BY array_position(ARRAY['registered_owner','beneficial_owner','operator',
                 'commercial_manager','technical_manager','ism_manager'], role), start_date DESC NULLS LAST
        """,
        vessel_id,
    )
    return [dict(r) for r in rows]


async def match_companies(conn: asyncpg.Connection, name: str, threshold: float, limit: int = 10) -> list[dict]:
    """Nhóm các tên công ty theo dạng chuẩn hoá; khớp chính xác trước, rồi gần đúng."""
    norm = norm_company(name)
    if not norm:
        return []
    rows = await conn.fetch(
        """
        SELECT company_norm,
               array_agg(DISTINCT company_name ORDER BY company_name) AS variants,
               array_agg(DISTINCT role ORDER BY role) AS roles,
               count(DISTINCT vessel_id) AS vessel_count,
               (company_norm = $1) AS exact,
               CASE WHEN company_norm = $1 THEN 1.0
                    ELSE greatest(similarity(company_norm, $1), word_similarity($1, company_norm) * 0.9)
               END::float AS score
        FROM ownership
        WHERE company_norm = $1
           OR company_norm LIKE $1 || ' %'
           OR similarity(company_norm, $1) >= $2
           OR word_similarity($1, company_norm) >= $2
        GROUP BY company_norm
        ORDER BY score DESC, company_norm
        LIMIT $3
        """,
        norm, threshold, limit,
    )
    return [dict(r) for r in rows]


async def company_vessels(
    conn: asyncpg.Connection,
    company_norms: list[str],
    role: str | None,
    exclude_vessel_id: str | None = None,
) -> list[dict]:
    rows = await conn.fetch(
        f"""
        SELECT {VESSEL_COLUMNS},
               json_agg(json_build_object('role', o.role, 'company_name', o.company_name)
                        ORDER BY o.role, o.company_name)::jsonb AS roles
        FROM ownership o
        JOIN vessels v ON v.vessel_id = o.vessel_id
        WHERE o.company_norm = ANY($1::text[])
          AND ($2::text IS NULL OR o.role = $2)
          AND ($3::uuid IS NULL OR v.vessel_id <> $3)
        GROUP BY v.vessel_id
        ORDER BY v.shipname NULLS LAST, v.mmsi
        """,
        company_norms, role, exclude_vessel_id,
    )
    return [dict(r) for r in rows]


async def vessels_by_filter(
    conn: asyncpg.Connection,
    company_norms: list[str] | None = None,
    role: str | None = None,
    ship_type_group: str | None = None,
    limit: int = 1000,
) -> list[dict]:
    rows = await conn.fetch(
        f"""
        SELECT {VESSEL_COLUMNS}
        FROM vessels v
        WHERE ($3::text IS NULL OR v.ship_type_group = $3)
          AND ($1::text[] IS NULL OR EXISTS (
                SELECT 1 FROM ownership o
                WHERE o.vessel_id = v.vessel_id
                  AND o.company_norm = ANY($1::text[])
                  AND ($2::text IS NULL OR o.role = $2)))
        ORDER BY v.shipname NULLS LAST, v.mmsi
        LIMIT $4
        """,
        company_norms, role, ship_type_group, limit,
    )
    return [dict(r) for r in rows]


# Sắp xếp danh sách tàu: ánh xạ sang đoạn SQL cố định (không ghép chuỗi từ người dùng)
LIST_ORDER = {
    "name": "v.shipname_norm = '', v.shipname_norm, v.mmsi",
    "dwt": "v.dwt DESC NULLS LAST, v.shipname_norm",
    "length": "v.length_m DESC NULLS LAST, v.shipname_norm",
    "year_built": "v.year_built DESC NULLS LAST, v.shipname_norm",
}

_LIST_FILTER = """
    ($1::text IS NULL OR v.ship_type_group = $1)
    AND ($2::text IS NULL OR upper(v.flag_code) = upper($2) OR v.flag ILIKE '%' || $2 || '%')
    AND ($3::text IS NULL OR v.shipname_norm LIKE '%' || $3 || '%')
"""


async def list_vessels(
    conn: asyncpg.Connection,
    ship_type_group: str | None,
    flag: str | None,
    name_contains: str | None,
    order_by: str,
    limit: int,
    offset: int,
) -> tuple[int, list[dict]]:
    """Trang danh sách tàu theo bộ lọc; trả (tổng số tàu khớp, các tàu của trang)."""
    name = norm_name(name_contains) if name_contains else None
    total = await conn.fetchval(f"SELECT count(*) FROM vessels v WHERE {_LIST_FILTER}", ship_type_group, flag, name)
    rows = await conn.fetch(
        f"""
        SELECT {VESSEL_COLUMNS}
        FROM vessels v
        WHERE {_LIST_FILTER}
        ORDER BY {LIST_ORDER[order_by]}
        LIMIT $4 OFFSET $5
        """,
        ship_type_group, flag, name, limit, offset,
    )
    return total, [dict(r) for r in rows]


async def vessel_breakdown(
    conn: asyncpg.Connection, ship_type_group: str | None, flag: str | None, name_contains: str | None, top_flags: int
) -> dict:
    """Số tàu theo nhóm loại và theo cờ (trong tập đã lọc), cùng tổng số tàu của cả bộ dữ liệu."""
    name = norm_name(name_contains) if name_contains else None
    groups = await conn.fetch(
        f"""SELECT v.ship_type_group AS name, count(*) AS count FROM vessels v WHERE {_LIST_FILTER}
            GROUP BY 1 ORDER BY 2 DESC, 1""",
        ship_type_group, flag, name,
    )
    flags = await conn.fetch(
        f"""SELECT coalesce(v.flag, 'không rõ') AS name, count(*) AS count FROM vessels v WHERE {_LIST_FILTER}
            GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT $4""",
        ship_type_group, flag, name, top_flags,
    )
    extra = await conn.fetchrow(
        f"""SELECT (SELECT count(*) FROM vessels) AS dataset_total,
                   count(*) FILTER (WHERE v.shipname_norm = '') AS unnamed,
                   count(DISTINCT v.flag) AS flag_count
            FROM vessels v WHERE {_LIST_FILTER}""",
        ship_type_group, flag, name,
    )
    return {
        "dataset_total": extra["dataset_total"],
        "unnamed": extra["unnamed"],
        "flag_count": extra["flag_count"],
        "by_ship_type_group": [dict(g) for g in groups],
        "top_flags": [dict(f) for f in flags],
    }
