"""Shared recipe library: dedup by name, cached details/nutrition, per-language links."""

import json
import sqlite3

_LANG_COLUMNS = {"it": "link_it", "es": "link_es", "en": "link_en"}
_LINK_PRIORITY = ("link_it", "link_es", "link_en")
_NAME_LANG_COLUMNS = {"it": "name_it", "es": "name_es", "en": "name_en"}

DIFFICULTY_LABELS = {
    0: "Mimis",
    1: "Easy",
    2: "Medium",
    3: "Difficult",
    4: "Masterchef",
}


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


def list_all_recipes(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM recipes ORDER BY name COLLATE NOCASE").fetchall()


def rename_recipe(conn: sqlite3.Connection, recipe_id: int, new_name: str) -> None:
    conn.execute("UPDATE recipes SET name = ? WHERE id = ?", (new_name, recipe_id))
    conn.commit()


def set_link_for_language(conn: sqlite3.Connection, recipe_id: int, language: str, link: str) -> None:
    """Overwrites the link for one language slot (it/es/en), leaving the others untouched."""
    column = _LANG_COLUMNS.get(language, "link_en")
    conn.execute(f"UPDATE recipes SET {column} = ? WHERE id = ?", (link, recipe_id))
    conn.commit()


def pick_display_link(recipe: sqlite3.Row, preferred_language: str | None = None) -> str | None:
    """Picks a single link to show (e.g. in a Calendar description). Tries
    `preferred_language` (it/es/en) first if given, then falls back to priority IT > ES > EN."""
    if preferred_language:
        preferred_column = _LANG_COLUMNS.get(preferred_language)
        if preferred_column and recipe[preferred_column]:
            return recipe[preferred_column]
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


def set_name_for_language(conn: sqlite3.Connection, recipe_id: int, language: str, name: str | None) -> None:
    """Sets the per-language display name (it/es/en) shown/edited in /edit_recipe.
    Independent of the recipe's canonical `name`, which stays the dish-matching key."""
    column = _NAME_LANG_COLUMNS.get(language)
    if column is None:
        raise ValueError(f"Unknown language: {language}")
    conn.execute(f"UPDATE recipes SET {column} = ? WHERE id = ?", (name, recipe_id))
    conn.commit()


def update_notes(conn: sqlite3.Connection, recipe_id: int, notes: str | None) -> None:
    conn.execute("UPDATE recipes SET notes = ? WHERE id = ?", (notes, recipe_id))
    conn.commit()


def update_nutrition_per_100g(
    conn: sqlite3.Connection,
    recipe_id: int,
    calories: int,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
) -> None:
    conn.execute(
        "UPDATE recipes SET calories_per_100g = ?, protein_per_100g_g = ?, "
        "carbs_per_100g_g = ?, fat_per_100g_g = ? WHERE id = ?",
        (calories, protein_g, carbs_g, fat_g, recipe_id),
    )
    conn.commit()


def set_difficulty(conn: sqlite3.Connection, recipe_id: int, difficulty: int | None) -> None:
    if difficulty is not None and difficulty not in DIFFICULTY_LABELS:
        raise ValueError(f"Unknown difficulty: {difficulty}")
    conn.execute("UPDATE recipes SET difficulty = ? WHERE id = ?", (difficulty, recipe_id))
    conn.commit()


def set_prep_time_minutes(conn: sqlite3.Connection, recipe_id: int, minutes: int | None) -> None:
    conn.execute("UPDATE recipes SET prep_time_minutes = ? WHERE id = ?", (minutes, recipe_id))
    conn.commit()


def set_cook_time_minutes(conn: sqlite3.Connection, recipe_id: int, minutes: int | None) -> None:
    conn.execute("UPDATE recipes SET cook_time_minutes = ? WHERE id = ?", (minutes, recipe_id))
    conn.commit()


def set_oven_temperature_c(conn: sqlite3.Connection, recipe_id: int, celsius: int | None) -> None:
    conn.execute("UPDATE recipes SET oven_temperature_c = ? WHERE id = ?", (celsius, recipe_id))
    conn.commit()


def set_rating(conn: sqlite3.Connection, recipe_id: int, rating: int | None) -> None:
    if rating is not None and not (1 <= rating <= 10):
        raise ValueError(f"Rating must be between 1 and 10: {rating}")
    conn.execute("UPDATE recipes SET rating = ? WHERE id = ?", (rating, recipe_id))
    conn.commit()


def link_meal_to_recipe(conn: sqlite3.Connection, dish_name: str, language: str, link: str | None) -> int:
    """Finds or creates the shared recipe for this dish name.
    The given link (if any) is stored under the detected/given language."""
    recipe_id, _ = get_or_create_recipe(conn, dish_name)

    if link:
        set_link_for_language(conn, recipe_id, language, link)

    return recipe_id
