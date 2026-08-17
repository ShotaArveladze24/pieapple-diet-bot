"""Normalized Italian ingredient storage: dedup by name, linked to recipes with a
per-recipe quantity, so ingredients can be counted across the whole recipe library."""

import sqlite3


def find_ingredient_by_name(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM ingredients_it WHERE name = ? COLLATE NOCASE", (name,)).fetchone()


def get_or_create_ingredient(conn: sqlite3.Connection, name: str) -> int:
    existing = find_ingredient_by_name(conn, name)
    if existing:
        return existing["id"]
    cursor = conn.execute("INSERT INTO ingredients_it (name) VALUES (?)", (name,))
    conn.commit()
    return int(cursor.lastrowid)


def has_ingredients_it(conn: sqlite3.Connection, recipe_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM recipe_ingredients_it WHERE recipe_id = ? LIMIT 1", (recipe_id,)
    ).fetchone()
    return row is not None


def set_recipe_ingredients_it(conn: sqlite3.Connection, recipe_id: int, ingredients: list[dict]) -> int:
    """Replaces this recipe's saved Italian ingredients with `ingredients` (each a
    {"name", "quantity"} dict). Delete-then-reinsert rather than a pure upsert, so a
    rescan also drops ingredients no longer listed on the page, not just adds new ones.
    Entries with a missing/blank name are skipped rather than raising, since this is
    fed directly from AI-scraped output. Returns the number of ingredients saved."""
    conn.execute("DELETE FROM recipe_ingredients_it WHERE recipe_id = ?", (recipe_id,))

    saved = 0
    for item in ingredients:
        name = (item.get("name") or "").strip() if isinstance(item, dict) else ""
        if not name:
            continue
        quantity = item.get("quantity") if isinstance(item, dict) else None
        ingredient_id = get_or_create_ingredient(conn, name)
        conn.execute(
            """INSERT INTO recipe_ingredients_it (recipe_id, ingredient_id, quantity)
               VALUES (?, ?, ?)
               ON CONFLICT(recipe_id, ingredient_id) DO UPDATE SET quantity = excluded.quantity""",
            (recipe_id, ingredient_id, quantity),
        )
        saved += 1

    conn.commit()
    return saved


def list_ingredient_usage_it(conn: sqlite3.Connection) -> list[dict]:
    """One row per Italian ingredient that's actually linked to at least one recipe:
    {"name", "count", "top_recipe_ids"} (up to the 3 highest recipe ids using it)."""
    rows = conn.execute(
        """SELECT i.name AS name, ri.recipe_id AS recipe_id
           FROM ingredients_it i
           JOIN recipe_ingredients_it ri ON ri.ingredient_id = i.id
           ORDER BY i.name COLLATE NOCASE, ri.recipe_id DESC"""
    ).fetchall()

    usage: dict[str, dict] = {}
    for row in rows:
        entry = usage.setdefault(row["name"], {"name": row["name"], "recipe_ids": []})
        entry["recipe_ids"].append(row["recipe_id"])

    return [
        {"name": entry["name"], "count": len(entry["recipe_ids"]), "top_recipe_ids": entry["recipe_ids"][:3]}
        for entry in usage.values()
    ]
