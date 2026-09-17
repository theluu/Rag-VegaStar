import json
from pathlib import Path

import pytest

from fakes import HashEmbedder
from vessel_chat.rag.chunker import chunk_markdown
from vessel_chat.rag.store import ingest_directory, search
from vessel_chat.tools import ToolContext, execute_tool

DOC = """# Tài liệu thử

Đoạn mở đầu không thuộc mục nào.

## Trạng thái hành hải
Mã 1 nghĩa là tàu đang thả neo (At anchor). Mã 5 là đã cập cầu (Moored).

## Mục rất dài
{long}
"""


def test_chunker_splits_by_heading_and_size():
    long = "\n\n".join(f"Đoạn văn số {i} " + "chữ " * 60 for i in range(6))
    chunks = chunk_markdown("thu.md", DOC.format(long=long), max_chars=500)
    assert chunks[0].section == "Tổng quan" and "mở đầu" in chunks[0].content
    assert chunks[1].section == "Trạng thái hành hải"
    long_parts = [c for c in chunks if c.section == "Mục rất dài"]
    assert len(long_parts) >= 3 and all(len(c.content) <= 500 for c in long_parts)
    assert all(c.title == "Tài liệu thử" for c in chunks)
    assert len({c.content_hash for c in chunks}) == len(chunks)


@pytest.fixture
def kb_dir(tmp_path: Path) -> Path:
    (tmp_path / "ais.md").write_text(DOC.format(long="Nội dung phụ."), encoding="utf-8")
    (tmp_path / "donvi.md").write_text(
        "# Đơn vị\n\n## Hải lý\nMột hải lý bằng 1852 mét. Knot là hải lý trên giờ.\n", encoding="utf-8"
    )
    return tmp_path


async def test_ingest_is_idempotent_and_removes_stale(pool, settings, kb_dir):
    emb = HashEmbedder(settings.embedding_dim)
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM kb_chunks")
        first = await ingest_directory(conn, emb, kb_dir, max_chars=800)
        calls = emb.calls
        second = await ingest_directory(conn, emb, kb_dir, max_chars=800)
        assert first["added"] == first["total"] > 0 and first["removed"] == 0
        assert second == {"total": first["total"], "added": 0, "removed": 0}
        assert emb.calls == calls  # không nhúng lại nội dung không đổi

        (kb_dir / "donvi.md").unlink()
        third = await ingest_directory(conn, emb, kb_dir, max_chars=800)
        assert third["removed"] >= 1
        assert await conn.fetchval("SELECT count(*) FROM kb_chunks WHERE source = 'donvi.md'") == 0


async def test_hybrid_search_finds_relevant_chunk_without_accents(pool, settings, kb_dir):
    emb = HashEmbedder(settings.embedding_dim)
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM kb_chunks")
        await ingest_directory(conn, emb, kb_dir, max_chars=800)
        hits = await search(conn, emb, "hai ly bang bao nhieu met", k=2, candidates=10, min_score=0.0)
    assert hits[0]["source"] == "donvi.md" and hits[0]["section"] == "Hải lý"
    assert hits[0]["keyword_rank"] == 1


async def test_search_knowledge_tool_returns_citations(pool, settings, kb_dir):
    emb = HashEmbedder(settings.embedding_dim)
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM kb_chunks")
        await ingest_directory(conn, emb, kb_dir, max_chars=800)
    ctx = ToolContext(pool=pool, settings=settings.model_copy(update={"rag_min_score": 0.0}), embedder=emb)
    r = await execute_tool(ctx, "search_knowledge", json.dumps({"query": "trạng thái thả neo At anchor"}))
    assert r.content["status"] == "ok"
    top = r.content["results"][0]
    assert top["citation"] == "ais.md › Trạng thái hành hải"
    assert "thả neo" in top["text"]

    empty = await execute_tool(ctx, "search_knowledge", json.dumps({"query": "zzzz qqqq"}))
    assert empty.content["status"] in ("ok", "no_results")
