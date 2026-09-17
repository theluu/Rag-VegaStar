"""GeoJSON sinh ra từ tool, lưu theo id để client tải về (không đi qua LLM)."""

import uuid

import asyncpg


async def save_map_data(conn: asyncpg.Connection, conv_id: str | None, payload) -> str:
    data_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO map_data (id, conversation_id, kind, summary, bbox, geojson) VALUES ($1, $2, $3, $4, $5, $6)",
        data_id, conv_id, payload.kind, payload.summary, payload.bbox, payload.geojson,
    )
    return str(data_id)


async def get_map_data(conn: asyncpg.Connection, data_id: str) -> dict | None:
    row = await conn.fetchrow(
        "SELECT id::text AS id, conversation_id::text AS conversation_id, kind, summary, bbox, geojson, created_at "
        "FROM map_data WHERE id = $1",
        data_id,
    )
    return dict(row) if row else None


async def list_map_data(conn: asyncpg.Connection, conv_id: str) -> list[dict]:
    rows = await conn.fetch(
        "SELECT id::text AS id, kind, summary, bbox, created_at FROM map_data "
        "WHERE conversation_id = $1 ORDER BY created_at",
        conv_id,
    )
    return [dict(r) for r in rows]
