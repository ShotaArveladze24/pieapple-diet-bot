"""Logica applicativa piani pasto: accesso dati per plans/meals/consumption_log."""

import json
import sqlite3
from datetime import date, timedelta


def create_plan(
    conn: sqlite3.Connection, source_filename: str, source_language: str, week_start_date: str
) -> int:
    cursor = conn.execute(
        "INSERT INTO plans (source_filename, source_language, week_start_date) VALUES (?, ?, ?)",
        (source_filename, source_language, week_start_date),
    )
    conn.commit()
    return int(cursor.lastrowid)


def get_or_create_manual_plan(conn: sqlite3.Connection) -> int:
    """Restituisce l'id del plan 'manual' usato per le ricette aggiunte a mano,
    creandolo se non esiste ancora."""
    row = conn.execute(
        "SELECT id FROM plans WHERE source_filename = 'manual' ORDER BY id LIMIT 1"
    ).fetchone()
    if row:
        return row["id"]
    monday, _ = week_bounds()
    return create_plan(conn, "manual", "it", monday)


def add_meal(
    conn: sqlite3.Connection,
    plan_id: int,
    meal_date: str,
    meal_type: str,
    dish_name: str,
    description: str | None = None,
    ingredients: list[str] | None = None,
    instructions: str | None = None,
    recipe_link: str | None = None,
    calories: int | None = None,
    macros: dict | None = None,
) -> int:
    cursor = conn.execute(
        """INSERT INTO meals
           (plan_id, date, meal_type, dish_name, description, ingredients, instructions,
            recipe_link, calories, macros_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            plan_id,
            meal_date,
            meal_type,
            dish_name,
            description,
            json.dumps(ingredients, ensure_ascii=False) if ingredients else None,
            instructions,
            recipe_link,
            calories,
            json.dumps(macros, ensure_ascii=False) if macros else None,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def get_meal(conn: sqlite3.Connection, meal_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM meals WHERE id = ?", (meal_id,)).fetchone()


def get_plan(conn: sqlite3.Connection, plan_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()


def list_meals_for_date(conn: sqlite3.Connection, meal_date: str) -> list[sqlite3.Row]:
    order = "CASE meal_type WHEN 'breakfast' THEN 0 WHEN 'lunch' THEN 1 ELSE 2 END"
    return conn.execute(
        f"SELECT * FROM meals WHERE date = ? ORDER BY {order}", (meal_date,)
    ).fetchall()


def get_meal_by_date_type(conn: sqlite3.Connection, meal_date: str, meal_type: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM meals WHERE date = ? AND meal_type = ?", (meal_date, meal_type)
    ).fetchone()


def apply_recipe_choice(conn: sqlite3.Connection, meal_id: int, recipe: sqlite3.Row, link: str | None) -> None:
    """Overwrites a meal's dish with an existing recipe's stored data."""
    conn.execute(
        """UPDATE meals SET
               dish_name = ?, ingredients = ?, instructions = ?, recipe_link = ?,
               calories = ?, macros_json = ?, recipe_id = ?
           WHERE id = ?""",
        (
            recipe["name"],
            recipe["ingredients"],
            recipe["instructions"],
            link,
            recipe["calories"],
            recipe["macros_json"],
            recipe["id"],
            meal_id,
        ),
    )
    conn.commit()


def list_all_meals(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    order = "date, CASE meal_type WHEN 'breakfast' THEN 0 WHEN 'lunch' THEN 1 ELSE 2 END"
    return conn.execute(f"SELECT * FROM meals ORDER BY {order}").fetchall()


def list_meals_before(conn: sqlite3.Connection, day_date: str) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM meals WHERE date < ? ORDER BY date", (day_date,)).fetchall()


def list_meals_after(conn: sqlite3.Connection, day_date: str) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM meals WHERE date > ? ORDER BY date", (day_date,)).fetchall()


def delete_meal(conn: sqlite3.Connection, meal_id: int) -> None:
    conn.execute("DELETE FROM consumption_log WHERE meal_id = ?", (meal_id,))
    conn.execute("DELETE FROM meals WHERE id = ?", (meal_id,))
    conn.commit()


def list_meals_for_range(
    conn: sqlite3.Connection, start_date: str, end_date: str
) -> list[sqlite3.Row]:
    order = "date, CASE meal_type WHEN 'breakfast' THEN 0 WHEN 'lunch' THEN 1 ELSE 2 END"
    return conn.execute(
        f"SELECT * FROM meals WHERE date BETWEEN ? AND ? ORDER BY {order}",
        (start_date, end_date),
    ).fetchall()


def update_recipe_link(conn: sqlite3.Connection, meal_id: int, recipe_link: str) -> None:
    conn.execute("UPDATE meals SET recipe_link = ? WHERE id = ?", (recipe_link, meal_id))
    conn.commit()


def update_recipe_details(
    conn: sqlite3.Connection, meal_id: int, ingredients: list[str], instructions: str
) -> None:
    conn.execute(
        "UPDATE meals SET ingredients = ?, instructions = ? WHERE id = ?",
        (json.dumps(ingredients, ensure_ascii=False), instructions, meal_id),
    )
    conn.commit()


def set_recipe_id(conn: sqlite3.Connection, meal_id: int, recipe_id: int) -> None:
    conn.execute("UPDATE meals SET recipe_id = ? WHERE id = ?", (recipe_id, meal_id))
    conn.commit()


def list_meals_for_recipe(conn: sqlite3.Connection, recipe_id: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM meals WHERE recipe_id = ?", (recipe_id,)).fetchall()


def rename_meals_for_recipe(conn: sqlite3.Connection, recipe_id: int, new_name: str) -> None:
    conn.execute("UPDATE meals SET dish_name = ? WHERE recipe_id = ?", (new_name, recipe_id))
    conn.commit()


def update_nutrition(
    conn: sqlite3.Connection, meal_id: int, calories: int, macros: dict
) -> None:
    conn.execute(
        "UPDATE meals SET calories = ?, macros_json = ? WHERE id = ?",
        (calories, json.dumps(macros, ensure_ascii=False), meal_id),
    )
    conn.commit()


def apply_substitution(
    conn: sqlite3.Connection,
    meal_id: int,
    dish_name: str,
    description: str | None,
    ingredients: list[str] | None,
    instructions: str | None,
    recipe_link: str | None,
    calories: int | None,
    macros: dict | None,
) -> None:
    conn.execute(
        """UPDATE meals SET
               dish_name = ?, description = ?, ingredients = ?, instructions = ?,
               recipe_link = ?, calories = ?, macros_json = ?, is_substitution = 1
           WHERE id = ?""",
        (
            dish_name,
            description,
            json.dumps(ingredients, ensure_ascii=False) if ingredients else None,
            instructions,
            recipe_link,
            calories,
            json.dumps(macros, ensure_ascii=False) if macros else None,
            meal_id,
        ),
    )
    conn.commit()


def set_calendar_event_id(conn: sqlite3.Connection, meal_id: int, event_id: str) -> None:
    conn.execute("UPDATE meals SET calendar_event_id = ? WHERE id = ?", (event_id, meal_id))
    conn.commit()


def log_consumption(
    conn: sqlite3.Connection, meal_id: int, status: str, note: str | None = None
) -> int:
    cursor = conn.execute(
        "INSERT INTO consumption_log (meal_id, status, note) VALUES (?, ?, ?)",
        (meal_id, status, note),
    )
    conn.commit()
    return int(cursor.lastrowid)


def week_bounds(reference: date | None = None) -> tuple[str, str]:
    """Restituisce (lunedi, domenica) della settimana corrente in formato ISO."""
    today = reference or date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()


def mark_day_off(conn: sqlite3.Connection, day_date: str, note: str | None = None) -> None:
    conn.execute(
        "INSERT INTO days_off (date, note) VALUES (?, ?) "
        "ON CONFLICT(date) DO UPDATE SET note = excluded.note",
        (day_date, note),
    )
    conn.commit()


def unmark_day_off(conn: sqlite3.Connection, day_date: str) -> None:
    conn.execute("DELETE FROM days_off WHERE date = ?", (day_date,))
    conn.commit()


def is_day_off(conn: sqlite3.Connection, day_date: str) -> bool:
    row = conn.execute("SELECT 1 FROM days_off WHERE date = ?", (day_date,)).fetchone()
    return row is not None


def list_days_off_in_range(conn: sqlite3.Connection, start_date: str, end_date: str) -> list[str]:
    rows = conn.execute(
        "SELECT date FROM days_off WHERE date BETWEEN ? AND ? ORDER BY date", (start_date, end_date)
    ).fetchall()
    return [row["date"] for row in rows]


def week_adherence_report(conn: sqlite3.Connection, start_date: str, end_date: str) -> dict:
    days_off = set(list_days_off_in_range(conn, start_date, end_date))
    meals = [m for m in list_meals_for_range(conn, start_date, end_date) if m["date"] not in days_off]
    total = len(meals)
    logs_by_meal = {}
    for row in conn.execute(
        """SELECT consumption_log.* FROM consumption_log
           JOIN meals ON meals.id = consumption_log.meal_id
           WHERE meals.date BETWEEN ? AND ?""",
        (start_date, end_date),
    ):
        logs_by_meal[row["meal_id"]] = row

    on_plan = sum(1 for m in meals if logs_by_meal.get(m["id"], {}).get("status") == "eaten_as_planned")
    different = sum(1 for m in meals if logs_by_meal.get(m["id"], {}).get("status") == "eaten_different")
    skipped = sum(1 for m in meals if logs_by_meal.get(m["id"], {}).get("status") == "skipped")
    unlogged = total - on_plan - different - skipped

    return {
        "total": total,
        "on_plan": on_plan,
        "different": different,
        "skipped": skipped,
        "unlogged": unlogged,
        "days_off": len(days_off),
    }
