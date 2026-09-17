"""Bộ nhớ dài hạn: các lượt hội thoại cũ được nhúng vector (pgvector)."""

import asyncpg
import numpy as np


async def add_chunk(conn: asyncpg.Connection, conv_id: str, turn_no: int, text: str, embedding: list[float]) -> None:
    await conn.execute(
        """
        INSERT INTO memory_chunks (conversation_id, turn_no, text, embedding)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (conversation_id, turn_no) DO UPDATE SET text = EXCLUDED.text, embedding = EXCLUDED.embedding
        """,
        conv_id, turn_no, text, np.asarray(embedding, dtype=np.float32),
    )


async def search_chunks(
    conn: asyncpg.Connection,
    conv_id: str,
    embedding: list[float],
    max_turn: int,
    k: int,
    min_score: float,
) -> list[dict]:
    """Top-k đoạn ký ức (cosine similarity) của đúng hội thoại, chỉ trong các lượt <= max_turn.

    Tập ứng viên được lọc theo hội thoại trước (MATERIALIZED) rồi mới xếp hạng → kết quả chính xác,
    không bị thiếu như khi kết hợp index ANN với bộ lọc.
    """
    rows = await conn.fetch(
        """
        WITH candidates AS MATERIALIZED (
            SELECT turn_no, text, embedding FROM memory_chunks
            WHERE conversation_id = $1 AND turn_no <= $3
        )
        SELECT turn_no, text, 1 - (embedding <=> $2) AS score
        FROM candidates
        ORDER BY embedding <=> $2
        LIMIT $4
        """,
        conv_id, np.asarray(embedding, dtype=np.float32), max_turn, k,
    )
    return [dict(r) for r in rows if r["score"] >= min_score]


async def max_chunk_turn(conn: asyncpg.Connection, conv_id: str) -> int:
    return await conn.fetchval(
        "SELECT coalesce(max(turn_no), 0) FROM memory_chunks WHERE conversation_id = $1", conv_id
    )
