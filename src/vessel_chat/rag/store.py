"""Lưu trữ và truy xuất kho tri thức: pgvector (HNSW) + full-text, gộp bằng Reciprocal Rank Fusion."""

import logging
import re
from pathlib import Path

import asyncpg
import numpy as np

from ..llm.client import Embedder
from ..textutil import fold
from .chunker import Chunk, chunk_markdown

log = logging.getLogger(__name__)

RRF_K = 60
EMBED_BATCH = 64


def load_chunks(directory: Path, max_chars: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(directory.glob("*.md")):
        chunks.extend(chunk_markdown(path.name, path.read_text(encoding="utf-8"), max_chars))
    return chunks


async def ingest_directory(conn: asyncpg.Connection, embedder: Embedder, directory: str | Path, max_chars: int) -> dict:
    """Đồng bộ thư mục tài liệu vào kb_chunks. Chỉ nhúng đoạn mới/đã sửa; xoá đoạn không còn."""
    chunks = load_chunks(Path(directory), max_chars)
    wanted = {c.content_hash: c for c in chunks}
    existing = {r["content_hash"] for r in await conn.fetch("SELECT content_hash FROM kb_chunks")}
    new = [c for h, c in wanted.items() if h not in existing]

    async with conn.transaction():
        for i in range(0, len(new), EMBED_BATCH):
            batch = new[i:i + EMBED_BATCH]
            vectors = await embedder.embed([c.embed_text for c in batch])
            await conn.executemany(
                """
                INSERT INTO kb_chunks (source, section, ordinal, content, content_hash, embedding, tsv)
                VALUES ($1, $2, $3, $4, $5, $6, to_tsvector('simple', $7))
                ON CONFLICT (content_hash) DO NOTHING
                """,
                [
                    (c.source, c.section, c.ordinal, c.content, c.content_hash,
                     np.asarray(v, dtype=np.float32), fold(f"{c.title} {c.section} {c.content}"))
                    for c, v in zip(batch, vectors)
                ],
            )
        removed = await conn.fetch(
            "DELETE FROM kb_chunks WHERE NOT (content_hash = ANY($1::text[])) RETURNING id", list(wanted)
        )
    stats = {"total": len(wanted), "added": len(new), "removed": len(removed)}
    log.info("Đồng bộ kho tri thức", extra={"fields": stats})
    return stats


def _tsquery(query: str) -> str | None:
    words = list(dict.fromkeys(re.findall(r"[a-z0-9]{2,}", fold(query))))
    return " | ".join(words[:32]) or None


async def search(
    conn: asyncpg.Connection,
    embedder: Embedder,
    query: str,
    k: int,
    candidates: int,
    min_score: float,
) -> list[dict]:
    """Tìm lai: top theo cosine + top theo ts_rank, xếp hạng lại bằng RRF."""
    [vec] = await embedder.embed([query])
    vec = np.asarray(vec, dtype=np.float32)
    rows = await conn.fetch(
        """
        WITH vec AS (
            SELECT id, row_number() OVER (ORDER BY d) AS r
            FROM (SELECT id, embedding <=> $1 AS d FROM kb_chunks ORDER BY embedding <=> $1 LIMIT $2) s
        ),
        kw AS (
            SELECT id, row_number() OVER (ORDER BY rank DESC, id) AS r
            FROM (
                SELECT id, ts_rank(tsv, q) AS rank
                FROM kb_chunks, to_tsquery('simple', coalesce($3, '')) q
                WHERE $3 IS NOT NULL AND tsv @@ q
                ORDER BY rank DESC LIMIT $2
            ) s
        )
        SELECT c.source, c.section, c.ordinal, c.content,
               1 - (c.embedding <=> $1) AS score,
               vec.r AS vector_rank, kw.r AS keyword_rank,
               coalesce(1.0 / ($5 + vec.r), 0) + coalesce(1.0 / ($5 + kw.r), 0) AS rrf
        FROM kb_chunks c
        LEFT JOIN vec ON vec.id = c.id
        LEFT JOIN kw ON kw.id = c.id
        WHERE vec.id IS NOT NULL OR kw.id IS NOT NULL
        ORDER BY rrf DESC, score DESC
        LIMIT $4
        """,
        vec, candidates, _tsquery(query), k, RRF_K,
    )
    return [
        dict(r) for r in rows
        if r["keyword_rank"] is not None or r["score"] >= min_score
    ]
