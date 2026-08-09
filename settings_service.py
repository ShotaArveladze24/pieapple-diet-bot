"""Small key/value store for bot-wide settings (e.g. content language)."""

import sqlite3


def get_setting(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def get_content_language(conn: sqlite3.Connection) -> str | None:
    return get_setting(conn, "content_language")


def set_content_language(conn: sqlite3.Connection, language: str) -> None:
    set_setting(conn, "content_language", language)
