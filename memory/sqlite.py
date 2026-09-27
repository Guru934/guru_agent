import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from typing import Any, List, Optional

from utils import get_logger

logger = get_logger("memory.sqlite")

from config import DB_PATH, USER_STATE_DIR as DB_DIR


@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    os.makedirs(DB_DIR, exist_ok=True)
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                model_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                role TEXT,
                content TEXT,
                tool_calls TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS preferences (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS capability_grants (
                id TEXT PRIMARY KEY,
                capability TEXT NOT NULL,
                constraints_json TEXT NOT NULL DEFAULT '{}',
                scope TEXT NOT NULL DEFAULT 'persistent',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            )
            """
        )

        conn.commit()


def create_session(model_id: str = "qwen2.5-coder") -> str:
    session_id = str(uuid.uuid4())
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO sessions (id, title, model_id) VALUES (?, ?, ?)",
            (session_id, "New Chat", model_id),
        )
        conn.commit()
    return session_id


def purge_empty_sessions():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM sessions 
            WHERE id NOT IN (SELECT DISTINCT session_id FROM messages)
            """
        )
        conn.commit()


def get_sessions():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, title, model_id, created_at FROM sessions ORDER BY updated_at DESC"
        )
        rows = cursor.fetchall()
    return [
        {"id": r[0], "title": r[1], "model_id": r[2], "created_at": r[3]}
        for r in rows
    ]


def get_messages(session_id: str):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT role, content, tool_calls FROM messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        )
        rows = cursor.fetchall()
    return [
        {
            "role": r[0],
            "content": r[1],
            "tool_calls": json.loads(r[2]) if r[2] else None,
        }
        for r in rows
    ]


def insert_message(
    session_id: str,
    role: str,
    content: str,
    tool_calls: Optional[List[Any]] = None,
):
    msg_id = str(uuid.uuid4())
    with get_db_connection() as conn:
        cursor = conn.cursor()
        tool_calls_json = json.dumps(tool_calls) if tool_calls else None
        cursor.execute(
            """
            INSERT INTO messages (id, session_id, role, content, tool_calls) 
            VALUES (?, ?, ?, ?, ?)
            """,
            (msg_id, session_id, role, content, tool_calls_json),
        )

        cursor.execute(
            "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (session_id,),
        )

        conn.commit()
    return msg_id


def update_session_model(session_id: str, model_id: str):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE sessions SET model_id = ? WHERE id = ?",
            (model_id, session_id),
        )
        conn.commit()


def update_session_title(session_id: str, title: str):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE sessions SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (title, session_id),
        )
        conn.commit()


def delete_session(session_id: str):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()


def get_sessions_with_counts():
    """Get all sessions with their message count, excluding empty sessions."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.id, s.title, s.model_id, s.created_at, COUNT(m.id) as msg_count
            FROM sessions s
            LEFT JOIN messages m ON s.id = m.session_id
            GROUP BY s.id
            HAVING msg_count > 0
            ORDER BY s.updated_at DESC
            """
        )
        rows = cursor.fetchall()
    return [
        {
            "id": r[0],
            "title": r[1],
            "model_id": r[2],
            "created_at": r[3],
            "msg_count": r[4],
        }
        for r in rows
    ]


def get_session_title_preview(session_id: str, max_len: int = 25) -> str:
    """Get a preview of the first user message for session title."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT content FROM messages 
            WHERE session_id = ? AND role = 'user' 
            ORDER BY created_at ASC LIMIT 1
            """,
            (session_id,),
        )
        row = cursor.fetchone()
    if row and row[0]:
        preview = row[0].strip().replace("\n", " ")[:max_len]
        return preview if preview else "New Chat"
    return "New Chat"


def get_preference(key: str, default: str = "") -> str:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM preferences WHERE key = ?", (key,))
        row = cursor.fetchone()
    return row[0] if row else default


def set_preference(key: str, value: str):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO preferences (key, value) VALUES (?, ?)",
            (key, value),
        )
        conn.commit()


# Auto-initialize on import
init_db()