"""Tạo schema và nạp CSV vào PostgreSQL.

    python scripts/load_data.py              # dùng DATA_DIR và DATABASE_URL từ .env
    python scripts/load_data.py --data-dir /path/to/data
"""

import argparse
import asyncio
import logging

import asyncpg

from vessel_chat.config import get_settings
from vessel_chat.db import init_schema
from vessel_chat.loader import load_all


async def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default=settings.data_dir)
    parser.add_argument("--database-url", default=settings.database_url)
    args = parser.parse_args()
    if not args.data_dir or not args.database_url:
        settings.require("data_dir", "database_url")

    conn = await asyncpg.connect(args.database_url)
    try:
        await init_schema(conn, settings.embedding_dim)
        counts = await load_all(conn, args.data_dir)
    finally:
        await conn.close()
    for table, n in counts.items():
        print(f"{table:15s} {n:>9,}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(main())
