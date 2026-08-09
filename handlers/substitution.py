"""'Substitute' callback: suggests an alternative dish and applies the substitution."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import calendar_service
import claude_client
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

    language = settings_service.get_content_language(conn) or "en"
    suggestion = claude_client.suggest_substitution(meal["dish_name"], language, constraints)
    context.user_data[f"pending_sub_{meal_id}"] = suggestion

    ingredients_text = "\n".join(f"- {item}" for item in suggestion.get("ingredients", []))
    text = f"Suggested alternative: {suggestion['dish_name']}\n\n{ingredients_text}\n\n{suggestion.get('instructions', '')}"

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Confirm", callback_data=f"subconfirm_{meal_id}"),
        InlineKeyboardButton("Cancel", callback_data=f"subcancel_{meal_id}"),
    ]])
    await query.message.reply_text(text, reply_markup=keyboard)


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

    language = settings_service.get_content_language(conn) or "en"
    recipe_id = None
    calendar_link = suggestion.get("recipe_link")
    try:
        recipe_id = recipe_service.link_meal_to_recipe(
            conn, suggestion["dish_name"], language, suggestion.get("recipe_link")
        )
        meal_service.set_recipe_id(conn, meal_id, recipe_id)
        recipe = recipe_service.get_recipe(conn, recipe_id)
        if recipe:
            calendar_link = recipe_service.pick_display_link(recipe) or calendar_link
    except Exception as exc:
        await query.message.reply_text(f"Warning: recipe lookup failed: {exc}")

    if meal["calendar_event_id"]:
        try:
            calendar_service.update_event(
                meal["calendar_event_id"], suggestion["dish_name"],
                suggestion.get("description") or "", meal["meal_type"],
                recipe_id=recipe_id, link=calendar_link,
            )
        except Exception as exc:
            await query.message.reply_text(f"Warning: Calendar update failed: {exc}")

    await query.answer()
    await query.edit_message_text(f"Substituted with: {suggestion['dish_name']}")


@owner_only
async def handle_substitute_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    meal_id = int(query.data.split("_", 1)[1])
    context.user_data.pop(f"pending_sub_{meal_id}", None)
    await query.answer()
    await query.edit_message_text("Cancelled.")
