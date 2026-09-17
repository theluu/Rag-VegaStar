import json
from importlib import resources

import asyncpg
from pgvector.asyncpg import register_vector

from .config import Settings


def schema_sql(embedding_dim: int) -> str:
    text = resources.files("vessel_chat").joinpath("schema.sql").read_text(encoding="utf-8")
    return text.format(embedding_dim=int(embedding_dim))


async def _init_connection(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    try:
        await register_vector(conn)
    except ValueError:
        # Extension vector chưa tồn tại (lần chạy đầu trước init_schema)
        pass


async def init_schema(conn: asyncpg.Connection, embedding_dim: int) -> None:
    await conn.execute(schema_sql(embedding_dim))


async def create_pool(settings: Settings, dsn: str | None = None) -> asyncpg.Pool:
    dsn = dsn or settings.database_url
    if not dsn:
        settings.require("database_url")
    # Đảm bảo extension/schema có sẵn trước khi pool đăng ký codec vector
    conn = await asyncpg.connect(dsn)
    try:
        await init_schema(conn, settings.embedding_dim)
    finally:
        await conn.close()
    return await asyncpg.create_pool(
        dsn,
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
        init=_init_connection,
        server_settings={"statement_timeout": str(settings.db_statement_timeout_ms), "timezone": "UTC"},
    )
