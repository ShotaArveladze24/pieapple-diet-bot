"""'Recipe' callback: shows ingredients and instructions for a meal."""

import json

from telegram import Update
from telegram.ext import ContextTypes

import meal_service
from access_control import owner_only


@owner_only
async def handle_recipe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    meal_id = int(query.data.split("_", 1)[1])
    conn = context.bot_data["conn"]

    meal = meal_service.get_meal(conn, meal_id)
    if meal is None:
        await query.answer("Meal not found.")
        return

    ingredients = json.loads(meal["ingredients"]) if meal["ingredients"] else None
    instructions = meal["instructions"]

    if not ingredients or not instructions:
        await query.answer()
        await query.message.reply_text(
            f"{meal['dish_name']}\n\nDetailed ingredients and instructions are not available."
        )
        return

    ingredients_text = "\n".join(f"- {item}" for item in ingredients)
    text = f"{meal['dish_name']}\n\n{ingredients_text}\n\n{instructions}"
    if meal["recipe_link"]:
        text += f"\n\n{meal['recipe_link']}"

    await query.answer()
    await query.message.reply_text(text)
