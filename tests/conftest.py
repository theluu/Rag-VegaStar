"""Fixture dùng chung.

Test chạy trên PostgreSQL thật (TEST_DATABASE_URL, mặc định DB `vessel_test` trong container),
dữ liệu tàu là bộ nhỏ trong tests/fixtures. LLM và embedding luôn là bản giả.
"""

from pathlib import Path

import pytest
import pytest_asyncio

from vessel_chat.config import Settings
from vessel_chat.db import create_pool
from vessel_chat.loader import load_all

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def settings() -> Settings:
    base = Settings()
    if not base.test_database_url:
        pytest.skip("TEST_DATABASE_URL chưa được cấu hình")
    return base.model_copy(
        update={
            "database_url": base.test_database_url,
            "openai_api_key": "test-key",
            "llm_model": "fake-llm",
            "embedding_model": "fake-embedding",
            "embedding_dim": 64,
            "data_dir": str(FIXTURES),
            "memory_window_turns": 2,
            "memory_min_score": 0.05,
            "memory_compaction_wait_seconds": 5,
            "debug_memory_events": True,
            "cors_origins": "http://localhost:5173",
            # Không phụ thuộc .env của máy chạy test: test nào cần xác thực sẽ tự bật
            "auth_users": "",
            "api_keys": "",
            "session_secret": "",
        }
    )


@pytest_asyncio.fixture(scope="session")
async def pool(settings):
    import asyncpg

    # Bảng memory_chunks phụ thuộc số chiều embedding → dựng lại schema hội thoại cho test
    conn = await asyncpg.connect(settings.database_url)
    await conn.execute("DROP TABLE IF EXISTS memory_chunks, kb_chunks, map_data, messages, conversations CASCADE")
    await conn.close()

    p = await create_pool(settings)
    async with p.acquire() as conn:
        await load_all(conn, FIXTURES)
    yield p
    await p.close()
