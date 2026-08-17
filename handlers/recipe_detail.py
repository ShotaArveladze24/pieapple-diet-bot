"""'Recipe' callback: shows ingredients and instructions for a meal.

The `meals` row is often thin (dish_name only); the richer, per-language data
lives on the linked `recipes` library row (meal["recipe_id"]), so that's the
fallback source for ingredients/instructions/link and any other cooking info."""

import json

from telegram import Update
from telegram.ext import ContextTypes

import meal_service
import recipe_service
import settings_service
from access_control import owner_only

DEFAULT_LANGUAGE = "it"


def _format_extra_details(recipe) -> str:
    """Cooking info/nutrition/notes/rating that's actually set on the recipe, for the
    Recipe button. Unlike the /edit_recipe screen, fields that aren't set are omitted
    rather than shown as '(not set)'."""
    lines = []

    if recipe["calories_per_100g"] is not None:
        lines.append(
            "Nutrition (per 100g): "
            f"{recipe['calories_per_100g']} kcal, "
            f"fat {recipe['fat_per_100g_g']} g, "
            f"protein {recipe['protein_per_100g_g']} g, "
            f"carbs {recipe['carbs_per_100g_g']} g"
        )

    if recipe["difficulty"] is not None:
        lines.append(f"Difficulty: {recipe_service.DIFFICULTY_LABELS.get(recipe['difficulty'])}")
    if recipe["prep_time_minutes"] is not None:
        lines.append(f"Prep time: {recipe['prep_time_minutes']} min")
    if recipe["cook_time_minutes"] is not None:
        lines.append(f"Cook time: {recipe['cook_time_minutes']} min")
    if recipe["oven_temperature_c"] is not None:
        lines.append(f"Oven temperature: {recipe['oven_temperature_c']} °C")
    if recipe["rating"] is not None:
        lines.append(f"Rating: {recipe['rating']}/10")
    if recipe["notes"]:
        lines.append(f"Notes: {recipe['notes']}")

    return "\n".join(lines)


@owner_only
async def handle_recipe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    meal_id = int(query.data.split("_", 1)[1])
    conn = context.bot_data["conn"]

    meal = meal_service.get_meal(conn, meal_id)
    if meal is None:
        await query.answer("Meal not found.")
        return

    recipe = recipe_service.get_recipe(conn, meal["recipe_id"]) if meal["recipe_id"] else None

    ingredients = json.loads(meal["ingredients"]) if meal["ingredients"] else None
    instructions = meal["instructions"]
    if recipe is not None:
        if not ingredients and recipe["ingredients"]:
            ingredients = json.loads(recipe["ingredients"])
        if not instructions and recipe["instructions"]:
            instructions = recipe["instructions"]

    language = settings_service.get_content_language(conn) or DEFAULT_LANGUAGE
    link = recipe_service.pick_display_link(recipe, language) if recipe is not None else None
    if not link:
        link = meal["recipe_link"]

    extra_details = _format_extra_details(recipe) if recipe is not None else ""

    if not ingredients and not instructions and not link and not extra_details:
        await query.answer()
        await query.message.reply_text(
            f"{meal['dish_name']}\n\nDetailed ingredients and instructions are not available."
        )
        return

    parts = [meal["dish_name"]]
    if ingredients:
        parts.append("\n".join(f"- {item}" for item in ingredients))
    if instructions:
        parts.append(instructions)
    if link:
        parts.append(link)
    if extra_details:
        parts.append(extra_details)

    await query.answer()
    await query.message.reply_text("\n\n".join(parts))
