"""Đồng bộ thư mục tài liệu nghiệp vụ (KNOWLEDGE_DIR) vào kho tri thức pgvector.

    python scripts/ingest_knowledge.py            # chỉ nhúng đoạn mới/đã sửa, xoá đoạn không còn
API cũng tự đồng bộ khi khởi động nếu RAG_AUTO_INGEST=true.
"""

import asyncio
import logging

import asyncpg

from vessel_chat.config import get_settings
from vessel_chat.db import _init_connection, init_schema
from vessel_chat.llm.client import OpenAIEmbedder
from vessel_chat.rag.store import ingest_directory


async def main() -> None:
    settings = get_settings()
    settings.require("database_url", "knowledge_dir")
    conn = await asyncpg.connect(settings.database_url)
    try:
        await init_schema(conn, settings.embedding_dim)
        await _init_connection(conn)
        stats = await ingest_directory(conn, OpenAIEmbedder(settings), settings.knowledge_dir,
                                       settings.rag_chunk_max_chars)
    finally:
        await conn.close()
    print(f"Kho tri thức: {stats['total']} đoạn (thêm {stats['added']}, xoá {stats['removed']})")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
