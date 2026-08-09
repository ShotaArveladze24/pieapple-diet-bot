"""'Nutrition facts' callback: shows or estimates calories and macros."""

import json

from telegram import Update
from telegram.ext import ContextTypes

import claude_client
import meal_service
from access_control import owner_only


@owner_only
async def handle_nutrition(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    meal_id = int(query.data.split("_", 1)[1])
    conn = context.bot_data["conn"]

    meal = meal_service.get_meal(conn, meal_id)
    if meal is None:
        await query.answer("Meal not found.")
        return

    if meal["calories"] and meal["macros_json"]:
        calories = meal["calories"]
        macros = json.loads(meal["macros_json"])
    else:
        ingredients = json.loads(meal["ingredients"]) if meal["ingredients"] else None
        estimate = claude_client.estimate_nutrition(meal["dish_name"], ingredients)
        calories = estimate["calories"]
        macros = {
            "protein_g": estimate["protein_g"],
            "carbs_g": estimate["carbs_g"],
            "fat_g": estimate["fat_g"],
        }
        meal_service.update_nutrition(conn, meal_id, calories, macros)

    text = (
        f"{meal['dish_name']}\n"
        f"Calories: {calories} kcal\n"
        f"Protein: {macros.get('protein_g', '?')} g\n"
        f"Carbs: {macros.get('carbs_g', '?')} g\n"
        f"Fat: {macros.get('fat_g', '?')} g"
    )
    await query.answer()
    await query.message.reply_text(text)
