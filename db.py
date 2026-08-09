"""Connessione database e inizializzazione schema."""

import sqlite3
from pathlib import Path

from config import DATABASE_PATH


def get_connection() -> sqlite3.Connection:
    db_path = Path(DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    schema_path = Path(__file__).parent / "schema.sql"
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    conn.commit()
    _migrate_add_recipe_id_column(conn)


def _migrate_add_recipe_id_column(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(meals)")}
    if "recipe_id" not in columns:
        conn.execute("ALTER TABLE meals ADD COLUMN recipe_id INTEGER REFERENCES recipes(id)")
        conn.commit()
