"""Local-first AI agent package for Ollama + Gemini workflows."""

from .db import init_db, create_session, get_sessions, get_messages, insert_message

__all__ = [
    "init_db",
    "create_session",
    "get_sessions",
    "get_messages",
    "insert_message",
]
