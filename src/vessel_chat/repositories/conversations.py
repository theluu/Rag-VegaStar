"""Lưu trữ hội thoại và tin nhắn (bền vững qua khởi động lại)."""

import uuid

import asyncpg

_CONV_COLS = "id::text AS id, title, created_at, updated_at, summary, summary_upto_turn, focus_state"
_MSG_COLS = "id, turn_no, role, content, tool_calls, tool_call_id, tool_name, meta, created_at"


async def create_conversation(conn: asyncpg.Connection, title: str) -> dict:
    row = await conn.fetchrow(
        f"INSERT INTO conversations (id, title) VALUES ($1, $2) RETURNING {_CONV_COLS}", uuid.uuid4(), title
    )
    return dict(row)


async def list_conversations(conn: asyncpg.Connection, limit: int = 200) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT c.id::text AS id, c.title, c.created_at, c.updated_at,
               (SELECT count(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count
        FROM conversations c
        ORDER BY c.updated_at DESC
        LIMIT $1
        """,
        limit,
    )
    return [dict(r) for r in rows]


async def get_conversation(conn: asyncpg.Connection, conv_id: str) -> dict | None:
    row = await conn.fetchrow(f"SELECT {_CONV_COLS} FROM conversations WHERE id = $1", conv_id)
    return dict(row) if row else None


async def delete_conversation(conn: asyncpg.Connection, conv_id: str) -> bool:
    status = await conn.execute("DELETE FROM conversations WHERE id = $1", conv_id)
    return status.endswith(" 1")


async def rename_conversation(conn: asyncpg.Connection, conv_id: str, title: str) -> None:
    await conn.execute("UPDATE conversations SET title = $2 WHERE id = $1", conv_id, title)


async def add_message(
    conn: asyncpg.Connection,
    conv_id: str,
    turn_no: int,
    role: str,
    content: str,
    tool_calls: list[dict] | None = None,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
    meta: dict | None = None,
) -> int:
    msg_id = await conn.fetchval(
        """
        INSERT INTO messages (conversation_id, turn_no, role, content, tool_calls, tool_call_id, tool_name, meta)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id
        """,
        conv_id, turn_no, role, content or "", tool_calls, tool_call_id, tool_name, meta,
    )
    await conn.execute("UPDATE conversations SET updated_at = now() WHERE id = $1", conv_id)
    return msg_id


async def list_messages(conn: asyncpg.Connection, conv_id: str) -> list[dict]:
    rows = await conn.fetch(f"SELECT {_MSG_COLS} FROM messages WHERE conversation_id = $1 ORDER BY id", conv_id)
    return [dict(r) for r in rows]


async def messages_between_turns(conn: asyncpg.Connection, conv_id: str, first_turn: int, last_turn: int) -> list[dict]:
    rows = await conn.fetch(
        f"""
        SELECT {_MSG_COLS} FROM messages
        WHERE conversation_id = $1 AND turn_no BETWEEN $2 AND $3
        ORDER BY id
        """,
        conv_id, first_turn, last_turn,
    )
    return [dict(r) for r in rows]


async def next_turn_no(conn: asyncpg.Connection, conv_id: str) -> int:
    return await conn.fetchval(
        "SELECT coalesce(max(turn_no), 0) + 1 FROM messages WHERE conversation_id = $1", conv_id
    )


async def update_focus(conn: asyncpg.Connection, conv_id: str, focus: dict) -> None:
    await conn.execute("UPDATE conversations SET focus_state = $2 WHERE id = $1", conv_id, focus)


async def update_summary(conn: asyncpg.Connection, conv_id: str, summary: str, upto_turn: int) -> None:
    await conn.execute(
        "UPDATE conversations SET summary = $2, summary_upto_turn = $3 WHERE id = $1", conv_id, summary, upto_turn
    )
