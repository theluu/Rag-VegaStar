"""Tổng hợp số liệu vận hành cho trang thống kê.

Mỗi lượt hỏi đáp kết thúc bằng một tin nhắn assistant không có `tool_calls` và có `meta`
(usage, chứng cứ, kiểm chứng, guardrail, telemetry). Mọi thống kê đọc từ đây nên vẫn còn sau khi
API khởi động lại, khác với bộ đếm Prometheus trong bộ nhớ.
"""

from datetime import datetime

import asyncpg

# CTE dùng chung: các lượt đã hoàn tất trong khoảng thời gian ($1 = mốc bắt đầu hoặc NULL)
_TURNS = """
WITH t AS (
    SELECT m.id, m.conversation_id, m.turn_no, m.created_at, m.meta,
           CASE
               WHEN m.meta->'telemetry'->>'outcome' IS NOT NULL THEN m.meta->'telemetry'->>'outcome'
               WHEN m.meta ? 'interrupted' THEN 'cancelled'
               WHEN m.meta ? 'error' THEN 'error'
               WHEN jsonb_path_exists(m.meta, '$.guardrail[*] ? (@.action == "block")') THEN 'blocked'
               ELSE 'ok'
           END AS outcome
    FROM messages m
    WHERE m.role = 'assistant' AND m.tool_calls IS NULL AND m.meta IS NOT NULL
      AND ($1::timestamptz IS NULL OR m.created_at >= $1)
)
"""


async def turn_summary(conn: asyncpg.Connection, since: datetime | None) -> dict:
    row = await conn.fetchrow(
        _TURNS
        + """
        SELECT count(*) AS turns,
               count(DISTINCT conversation_id) AS conversations,
               count(*) FILTER (WHERE outcome = 'ok') AS ok,
               count(*) FILTER (WHERE outcome = 'blocked') AS blocked,
               count(*) FILTER (WHERE outcome = 'error') AS error,
               count(*) FILTER (WHERE outcome = 'cancelled') AS cancelled,
               coalesce(sum((meta->'usage'->>'prompt_tokens')::bigint), 0) AS prompt_tokens,
               coalesce(sum((meta->'usage'->>'completion_tokens')::bigint), 0) AS completion_tokens,
               count(*) FILTER (WHERE meta ? 'telemetry') AS measured,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY (meta->'telemetry'->>'ttft_s')::float)
                   FILTER (WHERE outcome = 'ok') AS ttft_p50,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY (meta->'telemetry'->>'ttft_s')::float)
                   FILTER (WHERE outcome = 'ok') AS ttft_p95,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY (meta->'telemetry'->>'duration_s')::float)
                   FILTER (WHERE outcome = 'ok') AS duration_p50,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY (meta->'telemetry'->>'duration_s')::float)
                   FILTER (WHERE outcome = 'ok') AS duration_p95,
               min(created_at) AS first_at,
               max(created_at) AS last_at
        FROM t
        """,
        since,
    )
    return dict(row)


async def daily_series(conn: asyncpg.Connection, since: datetime | None, tz: str) -> list[dict]:
    rows = await conn.fetch(
        _TURNS
        + """
        SELECT (created_at AT TIME ZONE $2)::date AS day,
               count(*) AS turns,
               count(*) FILTER (WHERE outcome = 'blocked') AS blocked,
               count(*) FILTER (WHERE outcome = 'error') AS errors,
               coalesce(sum((meta->'usage'->>'prompt_tokens')::bigint), 0) AS prompt_tokens,
               coalesce(sum((meta->'usage'->>'completion_tokens')::bigint), 0) AS completion_tokens
        FROM t
        GROUP BY 1
        ORDER BY 1
        """,
        since,
        tz,
    )
    return [dict(r) for r in rows]


async def tool_usage(conn: asyncpg.Connection, since: datetime | None) -> list[dict]:
    """Số lần gọi và tỉ lệ thành công lấy từ chứng cứ (có ở mọi lượt); cache và độ trễ từ telemetry."""
    rows = await conn.fetch(
        _TURNS
        + """
        , calls AS (
            SELECT e->>'tool' AS name, count(*) AS calls,
                   count(*) FILTER (WHERE (e->>'ok')::boolean) AS ok
            FROM t, jsonb_array_elements(coalesce(t.meta->'evidence', '[]'::jsonb)) e
            GROUP BY 1
        ), timed AS (
            SELECT x->>'name' AS name, count(*) AS measured,
                   count(*) FILTER (WHERE x->>'cache' = 'hit') AS cache_hits,
                   count(*) FILTER (WHERE x->>'cache' IN ('hit', 'miss')) AS cacheable,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY (x->>'ms')::float) AS ms_p50,
                   percentile_cont(0.95) WITHIN GROUP (ORDER BY (x->>'ms')::float) AS ms_p95
            FROM t, jsonb_array_elements(coalesce(t.meta->'telemetry'->'tools', '[]'::jsonb)) x
            GROUP BY 1
        )
        SELECT c.name, c.calls, c.ok, coalesce(d.measured, 0) AS measured,
               coalesce(d.cache_hits, 0) AS cache_hits, coalesce(d.cacheable, 0) AS cacheable,
               d.ms_p50, d.ms_p95
        FROM calls c LEFT JOIN timed d USING (name)
        ORDER BY c.calls DESC, c.name
        """,
        since,
    )
    return [dict(r) for r in rows]


async def guardrail_counts(conn: asyncpg.Connection, since: datetime | None) -> list[dict]:
    rows = await conn.fetch(
        _TURNS
        + """
        SELECT g->>'stage' AS stage, g->>'action' AS action, g->>'kind' AS kind, count(*) AS count
        FROM t, jsonb_array_elements(coalesce(t.meta->'guardrail', '[]'::jsonb)) g
        GROUP BY 1, 2, 3
        ORDER BY count DESC, stage, action, kind
        """,
        since,
    )
    return [dict(r) for r in rows]


async def verification_summary(conn: asyncpg.Connection, since: datetime | None) -> dict:
    row = await conn.fetchrow(
        _TURNS
        + """
        SELECT count(*) FILTER (WHERE meta ? 'verification') AS verified,
               count(*) FILTER (WHERE (meta->'verification'->>'grounded')::boolean) AS grounded,
               count(*) FILTER (WHERE (meta->'verification'->>'auto_cited')::boolean) AS auto_cited,
               coalesce(sum((meta->'verification'->>'numbers_checked')::int), 0) AS numbers_checked,
               count(*) FILTER (WHERE outcome = 'ok' AND jsonb_array_length(coalesce(meta->'evidence', '[]')) > 0)
                   AS with_evidence,
               count(*) FILTER (WHERE outcome = 'ok' AND jsonb_array_length(coalesce(meta->'evidence', '[]')) > 0
                                AND jsonb_array_length(coalesce(meta->'verification'->'citations', '[]')) > 0)
                   AS cited
        FROM t
        """,
        since,
    )
    return dict(row)


async def recent_turns(conn: asyncpg.Connection, since: datetime | None, limit: int) -> list[dict]:
    rows = await conn.fetch(
        _TURNS
        + """
        SELECT t.id, t.conversation_id, c.title, t.turn_no, t.created_at, t.outcome,
               left(q.content, 240) AS question,
               (SELECT coalesce(jsonb_agg(DISTINCT e->>'tool'), '[]'::jsonb)
                  FROM jsonb_array_elements(coalesce(t.meta->'evidence', '[]'::jsonb)) e) AS tools,
               (t.meta->'usage'->>'prompt_tokens')::int AS prompt_tokens,
               (t.meta->'usage'->>'completion_tokens')::int AS completion_tokens,
               (t.meta->'telemetry'->>'ttft_s')::float AS ttft_s,
               (t.meta->'telemetry'->>'duration_s')::float AS duration_s,
               (t.meta->'verification'->>'grounded')::boolean AS grounded,
               jsonb_array_length(coalesce(t.meta->'evidence', '[]'::jsonb)) AS evidence_count,
               (SELECT g->>'kind' FROM jsonb_array_elements(coalesce(t.meta->'guardrail', '[]'::jsonb)) g
                 LIMIT 1) AS guardrail_kind
        FROM t
        JOIN conversations c ON c.id = t.conversation_id
        LEFT JOIN LATERAL (
            SELECT content FROM messages u
            WHERE u.conversation_id = t.conversation_id AND u.turn_no = t.turn_no AND u.role = 'user'
            ORDER BY u.id LIMIT 1
        ) q ON true
        ORDER BY t.created_at DESC
        LIMIT $2
        """,
        since,
        limit,
    )
    return [dict(r) for r in rows]


async def memory_summary(conn: asyncpg.Connection) -> dict:
    row = await conn.fetchrow(
        """
        SELECT (SELECT count(*) FROM conversations) AS conversations,
               (SELECT count(*) FROM conversations WHERE summary <> '') AS summarized,
               (SELECT count(*) FROM memory_chunks) AS memory_chunks,
               (SELECT count(*) FROM map_data) AS map_layers
        """
    )
    return dict(row)


async def data_inventory(conn: asyncpg.Connection) -> dict:
    """Quy mô dữ liệu nguồn và kho tri thức (không đổi giữa các lần gọi → nơi gọi nên cache)."""
    row = await conn.fetchrow(
        """
        SELECT (SELECT count(*) FROM vessels) AS vessels,
               (SELECT count(*) FROM ais_positions) AS positions,
               (SELECT min(event_ts) FROM ais_positions) AS positions_from,
               (SELECT max(event_ts) FROM ais_positions) AS positions_to,
               (SELECT count(DISTINCT vessel_id) FROM ais_positions) AS vessels_with_positions,
               (SELECT count(*) FROM dark_gaps) AS dark_gaps,
               (SELECT count(*) FROM ownership) AS ownership_rows,
               (SELECT count(DISTINCT company_norm) FROM ownership) AS companies,
               (SELECT count(*) FROM kb_chunks) AS knowledge_chunks,
               (SELECT count(DISTINCT source) FROM kb_chunks) AS knowledge_docs
        """
    )
    groups = await conn.fetch(
        "SELECT ship_type_group AS name, count(*) AS count FROM vessels GROUP BY 1 ORDER BY 2 DESC, 1"
    )
    return {**dict(row), "ship_type_groups": [dict(g) for g in groups]}
