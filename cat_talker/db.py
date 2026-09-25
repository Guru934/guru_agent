import json
import os
import sqlite3
import uuid
from typing import Any, List, Optional

from cat_talker.logging_config import get_logger

logger = get_logger("cat_talker.db")

DB_DIR = os.path.expanduser("~/.local/share/cat-talker")
DB_PATH = os.path.join(DB_DIR, "history.db")


def init_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
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

    conn.commit()
    conn.close()


def create_session(model_id: str = "qwen2.5-coder") -> str:
    session_id = str(uuid.uuid4())
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO sessions (id, title, model_id) VALUES (?, ?, ?)",
        (session_id, "New Chat", model_id),
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS preferences (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )

    conn.commit()
    conn.close()
    return session_id


def purge_empty_sessions():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM sessions 
        WHERE id NOT IN (SELECT DISTINCT session_id FROM messages)
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

    conn.commit()
    conn.close()


def get_sessions():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, title, model_id, created_at FROM sessions ORDER BY updated_at DESC"
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {"id": r[0], "title": r[1], "model_id": r[2], "created_at": r[3]}
        for r in rows
    ]


def get_messages(session_id: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, content, tool_calls FROM messages WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,),
    )
    rows = cursor.fetchall()
    conn.close()
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
    conn = sqlite3.connect(DB_PATH)
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

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS preferences (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )

    conn.commit()
    conn.close()
    return msg_id


def update_session_model(session_id: str, model_id: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE sessions SET model_id = ? WHERE id = ?",
        (model_id, session_id),
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS preferences (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )

    conn.commit()
    conn.close()


def update_session_title(session_id: str, title: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE sessions SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (title, session_id),
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS preferences (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )

    conn.commit()
    conn.close()


def delete_session(session_id: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS preferences (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )

    conn.commit()
    conn.close()


def get_sessions_with_counts():
    """Get all sessions with their message count, excluding empty sessions."""
    conn = sqlite3.connect(DB_PATH)
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
    conn.close()
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
    conn = sqlite3.connect(DB_PATH)
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
    conn.close()
    if row and row[0]:
        preview = row[0].strip().replace("\n", " ")[:max_len]
        return preview if preview else "New Chat"
    return "New Chat"


def get_preference(key: str, default: str = "") -> str:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM preferences WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default

def set_preference(key: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO preferences (key, value) VALUES (?, ?)",
        (key, value)
    )
    conn.commit()
    conn.close()
