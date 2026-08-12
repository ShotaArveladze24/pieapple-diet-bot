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
    _migrate_add_recipe_edit_columns(conn)


def _migrate_add_recipe_id_column(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(meals)")}
    if "recipe_id" not in columns:
        conn.execute("ALTER TABLE meals ADD COLUMN recipe_id INTEGER REFERENCES recipes(id)")
        conn.commit()


def _migrate_add_recipe_edit_columns(conn: sqlite3.Connection) -> None:
    """Adds the columns backing /edit_recipe: per-language display names, free-text
    notes, and per-100g nutrition (kept separate from the existing whole-dish
    calories/macros_json columns used by /recipe_details and meal-level nutrition)."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(recipes)")}
    new_columns = {
        "name_it": "TEXT",
        "name_es": "TEXT",
        "name_en": "TEXT",
        "notes": "TEXT",
        "calories_per_100g": "INTEGER",
        "protein_per_100g_g": "REAL",
        "carbs_per_100g_g": "REAL",
        "fat_per_100g_g": "REAL",
        "difficulty": "INTEGER",
        "prep_time_minutes": "INTEGER",
        "cook_time_minutes": "INTEGER",
        "oven_temperature_c": "INTEGER",
    }
    for column, col_type in new_columns.items():
        if column not in columns:
            conn.execute(f"ALTER TABLE recipes ADD COLUMN {column} {col_type}")
    conn.commit()
