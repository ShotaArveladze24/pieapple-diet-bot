"""/replace_recipe: swap in an existing library recipe for a given date/meal slot."""

from telegram import Update
from telegram.ext import ContextTypes

import meal_service
import recipe_service
from access_control import owner_only
from date_utils import parse_user_date
from handlers.recipe_library import parse_meal_type
from i18n import meal_type_label


def _list_recipes_text(conn) -> str | None:
    recipes = conn.execute("SELECT id, name FROM recipes ORDER BY name COLLATE NOCASE").fetchall()
    if not recipes:
        return None
    lines = [f"{row['id']} - {row['name']}" for row in recipes]
    return "\n".join(lines)


@owner_only
async def replace_recipe_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = context.bot_data["conn"]
    listing = _list_recipes_text(conn)
    if listing is None:
        await update.message.reply_text("No saved recipes yet. Upload a PDF, send a URL, or use /addrecipe.")
        return

    context.user_data["awaiting_replace"] = {"step": "recipe_id"}
    await update.message.reply_text(
        f"Available recipes:\n{listing}\n\nWhich recipe do you want to use? Send its ID."
    )


async def try_handle_replace_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    pending = context.user_data.get("awaiting_replace")
    if pending is None:
        return False

    text = update.message.text.strip()
    step = pending["step"]
    conn = context.bot_data["conn"]

    if step == "recipe_id":
        if not text.isdigit() or recipe_service.get_recipe(conn, int(text)) is None:
            await update.message.reply_text("I didn't recognize that recipe ID. Try again.")
            return True
        pending["recipe_id"] = int(text)
        pending["step"] = "date"
        await update.message.reply_text(
            "Which day? (e.g. 'today', 'tomorrow', 'monday', or a date like 2026-08-15)"
        )
        return True

    if step == "date":
        resolved = parse_user_date(text)
        if resolved is None:
            await update.message.reply_text("I didn't understand that date. Try again.")
            return True
        pending["date"] = resolved
        pending["step"] = "meal_type"
        await update.message.reply_text("Breakfast, lunch or dinner?")
        return True

    if step == "meal_type":
        meal_type = parse_meal_type(text)
        if meal_type is None:
            await update.message.reply_text("I didn't understand. Write: breakfast, lunch or dinner.")
            return True
        pending["meal_type"] = meal_type
        context.user_data.pop("awaiting_replace", None)
        await _apply_replacement(update, context, pending)
        return True

    context.user_data.pop("awaiting_replace", None)
    return False


async def _apply_replacement(update: Update, context: ContextTypes.DEFAULT_TYPE, pending: dict) -> None:
    conn = context.bot_data["conn"]
    recipe = recipe_service.get_recipe(conn, pending["recipe_id"])
    if recipe is None:
        await update.message.reply_text("That recipe no longer exists.")
        return

    link = recipe_service.pick_display_link(recipe)
    existing_meal = meal_service.get_meal_by_date_type(conn, pending["date"], pending["meal_type"])
    label = meal_type_label(pending["meal_type"])

    if existing_meal is None:
        plan_id = meal_service.get_or_create_manual_plan(conn)
        meal_id = meal_service.add_meal(
            conn,
            plan_id=plan_id,
            meal_date=pending["date"],
            meal_type=pending["meal_type"],
            dish_name=recipe["name"],
            recipe_link=link,
        )
        meal_service.apply_recipe_choice(conn, meal_id, recipe, link)
        prefix = "Nothing was scheduled there — added"
    else:
        meal_id = existing_meal["id"]
        meal_service.apply_recipe_choice(conn, meal_id, recipe, link)
        prefix = "Replaced with"

    await update.message.reply_text(
        f"{prefix} {recipe['name']} for {label} on {pending['date']}."
    )
