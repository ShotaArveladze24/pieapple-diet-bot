"""Shared recipe library: dedup by name, cached details/nutrition, per-language links."""

import json
import sqlite3

_LANG_COLUMNS = {"it": "link_it", "es": "link_es", "en": "link_en"}
_LINK_PRIORITY = ("link_it", "link_es", "link_en")


def find_recipe_by_name(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM recipes WHERE name = ? COLLATE NOCASE", (name,)).fetchone()


def create_recipe(conn: sqlite3.Connection, name: str) -> int:
    cursor = conn.execute("INSERT INTO recipes (name) VALUES (?)", (name,))
    conn.commit()
    return int(cursor.lastrowid)


def get_or_create_recipe(conn: sqlite3.Connection, name: str) -> tuple[int, bool]:
    """Returns (recipe_id, is_new). An existing recipe (matched case-insensitively by
    name) is always reused rather than creating a duplicate."""
    existing = find_recipe_by_name(conn, name)
    if existing:
        return existing["id"], False
    return create_recipe(conn, name), True


def get_recipe(conn: sqlite3.Connection, recipe_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()


def rename_recipe(conn: sqlite3.Connection, recipe_id: int, new_name: str) -> None:
    conn.execute("UPDATE recipes SET name = ? WHERE id = ?", (new_name, recipe_id))
    conn.commit()


def set_link_for_language(conn: sqlite3.Connection, recipe_id: int, language: str, link: str) -> None:
    """Overwrites the link for one language slot (it/es/en), leaving the others untouched."""
    column = _LANG_COLUMNS.get(language, "link_en")
    conn.execute(f"UPDATE recipes SET {column} = ? WHERE id = ?", (link, recipe_id))
    conn.commit()


def pick_display_link(recipe: sqlite3.Row) -> str | None:
    """Picks a single link to show (e.g. in a Calendar description) by priority IT > ES > EN."""
    for column in _LINK_PRIORITY:
        if recipe[column]:
            return recipe[column]
    return None


def update_details(conn: sqlite3.Connection, recipe_id: int, ingredients: list[str], instructions: str) -> None:
    conn.execute(
        "UPDATE recipes SET ingredients = ?, instructions = ? WHERE id = ?",
        (json.dumps(ingredients, ensure_ascii=False), instructions, recipe_id),
    )
    conn.commit()


def update_nutrition(conn: sqlite3.Connection, recipe_id: int, calories: int, macros: dict) -> None:
    conn.execute(
        "UPDATE recipes SET calories = ?, macros_json = ? WHERE id = ?",
        (calories, json.dumps(macros, ensure_ascii=False), recipe_id),
    )
    conn.commit()


def link_meal_to_recipe(conn: sqlite3.Connection, dish_name: str, language: str, link: str | None) -> int:
    """Finds or creates the shared recipe for this dish name.
    The given link (if any) is stored under the detected/given language."""
    recipe_id, _ = get_or_create_recipe(conn, dish_name)

    if link:
        set_link_for_language(conn, recipe_id, language, link)

    return recipe_id
