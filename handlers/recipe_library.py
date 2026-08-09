"""/recipes: list of saved meals with their recipe id and link editing.
/addrecipe: manually add a recipe to the plan (also used, pre-filled, by URL import).
/add_link: add or overwrite a recipe's link for one language.
/edit_recipe_name: rename a recipe.
/recipe_details: full detail (quantities, instructions, nutrition, links) for a recipe id."""

import json
import unicodedata

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import json
import unicodedata

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import meal_service
import recipe_service
import settings_service
from access_control import owner_only
from date_utils import parse_user_date
from i18n import meal_type_label

_MEAL_TYPE_WORDS = {
    "colazione": "breakfast", "desayuno": "breakfast", "breakfast": "breakfast",
    "pranzo": "lunch", "almuerzo": "lunch", "lunch": "lunch",
    "cena": "dinner", "dinner": "dinner",
}

_LANGUAGE_WORDS = {
    "it": "it", "italiano": "it", "italian": "it",
    "es": "es", "espanol": "es", "spagnolo": "es", "spanish": "es",
    "en": "en", "inglese": "en", "english": "en",
}


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower().strip())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def parse_meal_type(text: str) -> str | None:
    normalized = _normalize(text)
    for word, meal_type in _MEAL_TYPE_WORDS.items():
        if word in normalized:
            return meal_type
    return None


def parse_language(text: str) -> str | None:
    return _LANGUAGE_WORDS.get(_normalize(text))


@owner_only
async def list_recipes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = context.bot_data["conn"]
    meals = meal_service.list_all_meals(conn)

    if not meals:
        await update.message.reply_text("No saved recipes yet. Upload a PDF, send a URL, or use /addrecipe.")
        return

    for meal in meals:
        label = meal_type_label(meal["meal_type"])
        text = f"📅 {meal['date']} - {label}: {meal['dish_name']}"
        if meal["recipe_id"]:
            text += f"\nRecipe ID: {meal['recipe_id']} (use /recipe_details {meal['recipe_id']})"
        buttons = []
        if meal["recipe_link"]:
            text += f"\n{meal['recipe_link']}"
            if meal["recipe_link"].startswith(("http://", "https://")):
                buttons.append(InlineKeyboardButton("Open link", url=meal["recipe_link"]))
        buttons.append(InlineKeyboardButton("Edit link", callback_data=f"editlink_{meal['id']}"))
        keyboard = InlineKeyboardMarkup([buttons])
        await update.message.reply_text(text, reply_markup=keyboard)


@owner_only
async def handle_edit_link_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    meal_id = int(query.data.split("_", 1)[1])
    conn = context.bot_data["conn"]
    meal = meal_service.get_meal(conn, meal_id)
    if meal is None:
        await query.answer("Meal not found.")
        return

    context.user_data["awaiting_link_for_meal"] = meal_id
    await query.answer()
    await query.message.reply_text(
        f"Send the new link for '{meal['dish_name']}' (or '-' to remove it)."
    )


async def try_handle_link_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    meal_id = context.user_data.get("awaiting_link_for_meal")
    if meal_id is None:
        return False

    context.user_data.pop("awaiting_link_for_meal", None)
    conn = context.bot_data["conn"]
    meal = meal_service.get_meal(conn, meal_id)
    text = update.message.text.strip()
    new_link = None if text == "-" else text
    meal_service.update_recipe_link(conn, meal_id, new_link)

    await update.message.reply_text("Link updated." if new_link else "Link removed.")
    return True


@owner_only
async def add_recipe_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["new_recipe"] = {"step": "date"}
    await update.message.reply_text(
        "Which day should it go on? (e.g. 'today', 'tomorrow', 'monday', or a date like 2026-08-15)"
    )


async def _finalize_new_recipe(update: Update, context: ContextTypes.DEFAULT_TYPE, pending: dict) -> None:
    conn = context.bot_data["conn"]
    plan_id = meal_service.get_or_create_manual_plan(conn)
    meal_id = meal_service.add_meal(
        conn,
        plan_id=plan_id,
        meal_date=pending["date"],
        meal_type=pending["meal_type"],
        dish_name=pending["dish_name"],
        ingredients=pending.get("ingredients"),
        instructions=pending.get("instructions"),
        recipe_link=pending.get("link"),
        calories=pending.get("calories"),
        macros=pending.get("macros"),
    )

    recipe_id = None
    try:
        recipe_id = recipe_service.link_meal_to_recipe(
            conn, pending["dish_name"], pending["language"], pending.get("link")
        )
        meal_service.set_recipe_id(conn, meal_id, recipe_id)
    except Exception as exc:
        await update.message.reply_text(f"Warning: recipe lookup failed: {exc}")

    confirmation = f"Recipe added: {pending['dish_name']} ({pending['date']})."
    if recipe_id:
        confirmation += f"\nRecipe ID: {recipe_id} (use /recipe_details {recipe_id})"
    await update.message.reply_text(confirmation)


async def try_handle_new_recipe_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    pending = context.user_data.get("new_recipe")
    if pending is None:
        return False

    text = update.message.text.strip()
    step = pending["step"]

    if step == "date":
        resolved = parse_user_date(text)
        if resolved is None:
            await update.message.reply_text(
                "I didn't understand that date. Try again (e.g. 'today', 'tomorrow', 'monday', 2026-08-15)."
            )
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

        if pending.get("prefilled"):
            context.user_data.pop("new_recipe", None)
            await _finalize_new_recipe(update, context, pending)
            return True

        pending["step"] = "dish_name"
        await update.message.reply_text("Dish name?")
        return True

    if step == "dish_name":
        pending["dish_name"] = text
        pending["step"] = "language"
        await update.message.reply_text("What language is this recipe in? (IT/ES/EN)")
        return True

    if step == "language":
        language = parse_language(text)
        if language is None:
            await update.message.reply_text("I didn't understand. Write IT, ES or EN.")
            return True
        pending["language"] = language
        pending["step"] = "link"
        await update.message.reply_text("Recipe link? (write '-' to skip)")
        return True

    if step == "link":
        pending["link"] = None if text == "-" else text
        context.user_data.pop("new_recipe", None)
        await _finalize_new_recipe(update, context, pending)
        return True

    context.user_data.pop("new_recipe", None)
    return False


@owner_only
async def add_link_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /add_link <recipe id> <it|es|en>")
        return

    recipe_id = int(context.args[0])
    language = parse_language(context.args[1])
    if language is None:
        await update.message.reply_text("Language must be one of: it, es, en.")
        return

    conn = context.bot_data["conn"]
    recipe = recipe_service.get_recipe(conn, recipe_id)
    if recipe is None:
        await update.message.reply_text(f"No recipe found with id {recipe_id}.")
        return

    context.user_data["awaiting_add_link"] = {"recipe_id": recipe_id, "language": language}
    await update.message.reply_text(f"Send the {language.upper()} URL for '{recipe['name']}'.")


async def try_handle_add_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    pending = context.user_data.get("awaiting_add_link")
    if pending is None:
        return False

    context.user_data.pop("awaiting_add_link", None)
    conn = context.bot_data["conn"]
    link = update.message.text.strip()
    recipe_service.set_link_for_language(conn, pending["recipe_id"], pending["language"], link)
    await update.message.reply_text(
        f"{pending['language'].upper()} link updated for recipe #{pending['recipe_id']}."
    )
    return True


@owner_only
async def edit_recipe_name_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /edit_recipe_name <id>")
        return

    recipe_id = int(context.args[0])
    conn = context.bot_data["conn"]
    recipe = recipe_service.get_recipe(conn, recipe_id)
    if recipe is None:
        await update.message.reply_text(f"No recipe found with id {recipe_id}.")
        return

    context.user_data["awaiting_rename_recipe"] = recipe_id
    await update.message.reply_text(f"Current name: {recipe['name']}\nSend the new name.")


async def try_handle_rename_recipe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    recipe_id = context.user_data.get("awaiting_rename_recipe")
    if recipe_id is None:
        return False

    context.user_data.pop("awaiting_rename_recipe", None)
    new_name = update.message.text.strip()
    conn = context.bot_data["conn"]

    try:
        recipe_service.rename_recipe(conn, recipe_id, new_name)
    except Exception:
        await update.message.reply_text(f"A recipe named '{new_name}' already exists.")
        return True

    meal_service.rename_meals_for_recipe(conn, recipe_id, new_name)

    for meal in meal_service.list_meals_for_recipe(conn, recipe_id):
        await update.message.reply_text(f"Recipe #{recipe_id} renamed to '{new_name}'.")
    return True


@owner_only
async def recipe_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /recipe_details <id>. Use /recipes to see the IDs.")
        return

    recipe_id = int(context.args[0])
    conn = context.bot_data["conn"]
    recipe = recipe_service.get_recipe(conn, recipe_id)
    if recipe is None:
        await update.message.reply_text(f"No recipe found with id {recipe_id}.")
        return

    ingredients = json.loads(recipe["ingredients"]) if recipe["ingredients"] else None
    instructions = recipe["instructions"]
    if not ingredients or not instructions:
        details_text = "Detailed ingredients and instructions are not available."
        await update.message.reply_text(
            f"Recipe #{recipe_id}: {recipe['name']}\n\n" + details_text
        )
        return

    if recipe["calories"] and recipe["macros_json"]:
        calories = recipe["calories"]
        macros = json.loads(recipe["macros_json"])
        nutrition_text = (
            f"\n\nCalories: {calories} kcal\n"
            f"Protein: {macros.get('protein_g', '?')} g\n"
            f"Carbs: {macros.get('carbs_g', '?')} g\n"
            f"Fat: {macros.get('fat_g', '?')} g"
        )
    else:
        nutrition_text = "\n\nNutrition information is not available."

    ingredients_text = "\n".join(f"- {item}" for item in ingredients)
    text = (
        f"Recipe #{recipe_id}: {recipe['name']}\n\n"
        f"Ingredients:\n{ingredients_text}\n\n"
        f"Instructions:\n{instructions}\n\n"
        f"Calories: {calories} kcal\n"
        f"Protein: {macros.get('protein_g', '?')} g\n"
        f"Carbs: {macros.get('carbs_g', '?')} g\n"
        f"Fat: {macros.get('fat_g', '?')} g"
    )

    buttons = []
    for lang, label in (("link_it", "Open (IT)"), ("link_es", "Open (ES)"), ("link_en", "Open (EN)")):
        link = recipe[lang]
        if link and link.startswith(("http://", "https://")):
            buttons.append(InlineKeyboardButton(label, url=link))

    keyboard = InlineKeyboardMarkup([buttons]) if buttons else None
    await update.message.reply_text(text, reply_markup=keyboard)
