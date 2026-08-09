"""'Substitute' callback: suggests an alternative dish and applies the substitution."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import meal_service
import recipe_service
import settings_service
from access_control import owner_only


@owner_only
async def handle_substitute_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    meal_id = int(query.data.split("_", 1)[1])
    conn = context.bot_data["conn"]

    meal = meal_service.get_meal(conn, meal_id)
    if meal is None:
        await query.answer("Meal not found.")
        return

    constraints = f"about {meal['calories']} kcal" if meal["calories"] else "comparable nutritional value"

    await query.answer()
    await query.message.reply_text("Looking for an alternative...")

    await query.answer()
    await query.message.reply_text(
        "Substitution is not available without AI integration. Use /replace_recipe or /addrecipe instead."
    )


@owner_only
async def handle_substitute_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    meal_id = int(query.data.split("_", 1)[1])
    suggestion = context.user_data.pop(f"pending_sub_{meal_id}", None)
    if suggestion is None:
        await query.answer("No pending suggestion.")
        return

    conn = context.bot_data["conn"]
    meal = meal_service.get_meal(conn, meal_id)
    meal_service.apply_substitution(
        conn,
        meal_id,
        suggestion["dish_name"],
        suggestion.get("description"),
        suggestion.get("ingredients"),
        suggestion.get("instructions"),
        suggestion.get("recipe_link"),
        suggestion.get("calories"),
        suggestion.get("macros"),
    )

    await query.answer()
    await query.edit_message_text("Substitution was cancelled or is unavailable.")


@owner_only
async def handle_substitute_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    meal_id = int(query.data.split("_", 1)[1])
    context.user_data.pop(f"pending_sub_{meal_id}", None)
    await query.answer()
    await query.edit_message_text("Cancelled.")
