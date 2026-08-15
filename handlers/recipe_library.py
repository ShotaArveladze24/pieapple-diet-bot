"""/recipes: list of saved meals with their recipe id and link editing.
/addrecipe: manually add a recipe to the plan (also used, pre-filled, by URL import).
/add_link: add or overwrite a recipe's link for one language.
/edit_recipe: view and edit a recipe's per-language names, links, per-100g nutrition
and notes, with a Scan action that looks up missing links/translations/nutrition.
/scan: runs that same Scan directly on one recipe id, without going through /edit_recipe.
/scan_week, /scan_all: batch Scan over this week's recipes, or the whole library.
/recipe_details: full detail (quantities, instructions, nutrition, links) for a recipe id."""

import json
import logging
import re
import unicodedata

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import ai_queue_service
import meal_service
import recipe_service
import settings_service
from access_control import owner_only
from date_utils import parse_user_date
from text_utils import chunk_message

logger = logging.getLogger(__name__)

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

_LANG_LABELS = {"it": "IT", "es": "ES", "en": "EN"}

_VER_LINK_RE = re.compile(r"\(\s*ver\s+link\s*\)|ver\s+link", re.IGNORECASE)


def _strip_ver_link(name: str) -> str:
    """Removes the '(VER LINK)' / 'VER LINK' PDF-extraction artifact (a hyperlinked
    'see link' label in the source PDF that plain-text extraction can't resolve to an
    actual URL, so it sometimes lands as literal text in the dish name instead)."""
    cleaned = _VER_LINK_RE.sub("", name)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


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
    recipes = recipe_service.list_all_recipes(conn)

    if not recipes:
        await update.message.reply_text("No saved recipes yet. Upload a PDF, send a URL, or use /addrecipe.")
        return

    lines = []
    for recipe in recipes:
        line = f"#{recipe['id']} {recipe['name']}"
        link = recipe_service.pick_display_link(recipe)
        if link:
            line += f"\n{link}"
        lines.append(line)

    lines.append("\nUse /recipe_details <id> for full details, or /edit_recipe (then send the id) to edit.")

    for chunk in chunk_message("\n\n".join(lines)):
        await update.message.reply_text(chunk)


@owner_only
async def clean_titles(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = context.bot_data["conn"]

    meals = conn.execute(
        "SELECT id, dish_name, recipe_id FROM meals WHERE dish_name LIKE '%ver link%'"
    ).fetchall()
    if not meals:
        await update.message.reply_text('No meal titles contain "VER LINK".')
        return

    lines = []
    cleaned_recipe_ids: set[int] = set()
    for meal in meals:
        cleaned = _strip_ver_link(meal["dish_name"])
        if not cleaned or cleaned == meal["dish_name"]:
            continue

        conn.execute("UPDATE meals SET dish_name = ? WHERE id = ?", (cleaned, meal["id"]))
        lines.append(f"#{meal['id']}: '{meal['dish_name']}' -> '{cleaned}'")

        recipe_id = meal["recipe_id"]
        if recipe_id is not None and recipe_id not in cleaned_recipe_ids:
            cleaned_recipe_ids.add(recipe_id)
            recipe = recipe_service.get_recipe(conn, recipe_id)
            if recipe and "ver link" in recipe["name"].lower():
                recipe_cleaned = _strip_ver_link(recipe["name"])
                if recipe_cleaned:
                    try:
                        recipe_service.rename_recipe(conn, recipe_id, recipe_cleaned)
                    except Exception:
                        # Renamed value collided with another recipe's name (unique,
                        # case-insensitive) - leave that recipe's name as-is.
                        logger.exception("Could not rename recipe #%s after title cleanup", recipe_id)

    conn.commit()

    if not lines:
        await update.message.reply_text('No meal titles contain "VER LINK".')
        return

    text = "Cleaned up these meal titles:\n\n" + "\n".join(lines)
    for chunk in chunk_message(text):
        await update.message.reply_text(chunk)


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
async def edit_recipe_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["awaiting_edit_recipe_id"] = True
    await update.message.reply_text("Which recipe ID do you want to edit? Use /recipes to see the IDs.")


async def try_handle_edit_recipe_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not context.user_data.get("awaiting_edit_recipe_id"):
        return False

    context.user_data.pop("awaiting_edit_recipe_id", None)
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text(
            "That doesn't look like a valid recipe ID. Use /edit_recipe to try again."
        )
        return True

    recipe_id = int(text)
    conn = context.bot_data["conn"]
    if recipe_service.get_recipe(conn, recipe_id) is None:
        await update.message.reply_text(f"No recipe found with id {recipe_id}.")
        return True

    await _send_edit_recipe_screen(update.message, context, recipe_id)
    return True


def _format_recipe_text(recipe) -> str:
    lines = [f"Recipe #{recipe['id']}", "", "Name:"]
    for lang in ("it", "es", "en"):
        lines.append(f"  {_LANG_LABELS[lang]}: {recipe[f'name_{lang}'] or '(empty)'}")

    lines += ["", "Links:"]
    for lang in ("it", "es", "en"):
        lines.append(f"  LINK {_LANG_LABELS[lang]}: {recipe[f'link_{lang}'] or '(not set)'}")

    lines.append("")
    if recipe["calories_per_100g"] is not None:
        lines.append(
            "Nutrition (per 100g):\n"
            f"  Calories: {recipe['calories_per_100g']} kcal\n"
            f"  Fat: {recipe['fat_per_100g_g']} g\n"
            f"  Protein: {recipe['protein_per_100g_g']} g\n"
            f"  Carbs: {recipe['carbs_per_100g_g']} g"
        )
    else:
        lines.append("Nutrition (per 100g): not set")

    difficulty = recipe["difficulty"]
    difficulty_label = recipe_service.DIFFICULTY_LABELS.get(difficulty, "(not set)") if difficulty is not None else "(not set)"
    prep_time = recipe["prep_time_minutes"]
    cook_time = recipe["cook_time_minutes"]
    oven_temp = recipe["oven_temperature_c"]
    lines += [
        "",
        "Cooking info:",
        f"  Difficulty: {difficulty_label}",
        f"  Prep time: {prep_time} min" if prep_time is not None else "  Prep time: (not set)",
        f"  Cook time: {cook_time} min" if cook_time is not None else "  Cook time: (not set)",
        f"  Oven temperature: {oven_temp} °C" if oven_temp is not None else "  Oven temperature: (not set)",
    ]

    rating = recipe["rating"]
    lines += ["", f"Rating: {rating}/10" if rating is not None else "Rating: (not set)"]
    lines += ["", f"Notes: {recipe['notes'] or '(empty)'}"]
    return "\n".join(lines)


def _edit_recipe_keyboard(recipe_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔍 Scan", callback_data=f"erscan_{recipe_id}")],
            [
                InlineKeyboardButton("Edit name IT", callback_data=f"ername_it_{recipe_id}"),
                InlineKeyboardButton("Edit name ES", callback_data=f"ername_es_{recipe_id}"),
                InlineKeyboardButton("Edit name EN", callback_data=f"ername_en_{recipe_id}"),
            ],
            [
                InlineKeyboardButton("Edit LINK IT", callback_data=f"erlink_it_{recipe_id}"),
                InlineKeyboardButton("Edit LINK ES", callback_data=f"erlink_es_{recipe_id}"),
                InlineKeyboardButton("Edit LINK EN", callback_data=f"erlink_en_{recipe_id}"),
            ],
            [InlineKeyboardButton("Edit nutrition", callback_data=f"ernutrition_{recipe_id}")],
            [InlineKeyboardButton("Edit difficulty", callback_data=f"erdiff_{recipe_id}")],
            [
                InlineKeyboardButton("Edit prep time", callback_data=f"erprep_{recipe_id}"),
                InlineKeyboardButton("Edit cook time", callback_data=f"ercook_{recipe_id}"),
                InlineKeyboardButton("Edit oven temp", callback_data=f"eroven_{recipe_id}"),
            ],
            [InlineKeyboardButton("Edit notes", callback_data=f"ernotes_{recipe_id}")],
        ]
    )


async def _send_edit_recipe_screen(message, context: ContextTypes.DEFAULT_TYPE, recipe_id: int) -> None:
    conn = context.bot_data["conn"]
    recipe = recipe_service.get_recipe(conn, recipe_id)
    if recipe is None:
        return

    # Whatever edit (or Scan) triggered this refresh is already committed to the DB by
    # this point, so a failure sending this screen (e.g. a Telegram API timeout) is only
    # logged, not reported as an error - the next /edit_recipe or /recipe_details will
    # show it. This is the single call site shared by every edit_recipe action.
    try:
        await message.reply_text(_format_recipe_text(recipe), reply_markup=_edit_recipe_keyboard(recipe_id))
    except Exception:
        logger.exception("Could not send updated recipe screen")


def _recipe_needs_scan(recipe) -> bool:
    """True if Scan would have anything to fill in: a missing per-language link or
    name, or missing per-100g nutrition."""
    for lang in ("it", "es", "en"):
        if not recipe[f"link_{lang}"] or not recipe[f"name_{lang}"]:
            return True
    return recipe["calories_per_100g"] is None


def _enqueue_recipe_scan(chat_id: int, recipe) -> None:
    """Queues a scan_recipe AI request for whatever this recipe is currently missing
    (see ai_queue/SPEC.md). Already-populated fields are left untouched and notes are
    never touched by Scan. handlers/ai_consumer.py applies the result via
    apply_scan_result() once the response comes back."""
    ingredients = json.loads(recipe["ingredients"]) if recipe["ingredients"] else None
    ai_queue_service.enqueue(
        "scan_recipe",
        chat_id=chat_id,
        payload={
            "recipe_id": recipe["id"],
            "name": recipe["name"],
            "ingredients": ingredients,
            "missing_links": [lang for lang in ("it", "es", "en") if not recipe[f"link_{lang}"]],
            "missing_names": [lang for lang in ("it", "es", "en") if not recipe[f"name_{lang}"]],
            "needs_nutrition": recipe["calories_per_100g"] is None,
        },
    )


def apply_scan_result(conn, recipe_id: int, result: dict) -> dict:
    """Applies a consumed scan_recipe response's result to the DB. Called by
    handlers/ai_consumer.py. Returns a summary of what was actually written, for the
    follow-up Telegram message."""
    links = result.get("links") or {}
    names = result.get("names") or {}
    nutrition = result.get("nutrition")

    for lang, link in links.items():
        recipe_service.set_link_for_language(conn, recipe_id, lang, link)
    for lang, name in names.items():
        recipe_service.set_name_for_language(conn, recipe_id, lang, name)
    if nutrition is not None:
        recipe_service.update_nutrition_per_100g(
            conn,
            recipe_id,
            nutrition["calories"],
            nutrition["protein_g"],
            nutrition["carbs_g"],
            nutrition["fat_g"],
        )

    return {"links": len(links), "names": len(names), "nutrition": nutrition is not None}


@owner_only
async def handle_edit_recipe_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    recipe_id = int(query.data.rsplit("_", 1)[1])
    conn = context.bot_data["conn"]
    recipe = recipe_service.get_recipe(conn, recipe_id)
    if recipe is None:
        await query.answer("Recipe not found.")
        return

    await query.answer()
    if not _recipe_needs_scan(recipe):
        await query.message.reply_text("Nothing missing for this recipe - nothing to scan.")
        return

    _enqueue_recipe_scan(update.effective_chat.id, recipe)
    await query.message.reply_text(
        "Queued for scanning (links, translations, nutrition) - I'll update this recipe "
        "once it comes back."
    )


@owner_only
async def scan_recipe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/scan <id>: the same Scan used in /edit_recipe, callable directly by id."""
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /scan <recipe id>. Use /recipes to see the IDs.")
        return

    recipe_id = int(context.args[0])
    conn = context.bot_data["conn"]
    recipe = recipe_service.get_recipe(conn, recipe_id)
    if recipe is None:
        await update.message.reply_text(f"No recipe found with id {recipe_id}.")
        return

    if not _recipe_needs_scan(recipe):
        await update.message.reply_text("Nothing missing for this recipe - nothing to scan.")
        return

    _enqueue_recipe_scan(update.effective_chat.id, recipe)
    await update.message.reply_text(
        "Queued for scanning (links, translations, nutrition) - I'll update this recipe "
        "once it comes back."
    )


async def _scan_recipes_batch(message, chat_id: int, recipes: list) -> None:
    """Shared body for /scan_week and /scan_all: queues a scan for every recipe in
    `recipes` that's still missing a link, translation or nutrition, skipping the rest
    so a full library scan doesn't queue requests for recipes with nothing to fill in."""
    pending = [r for r in recipes if _recipe_needs_scan(r)]
    if not pending:
        await message.reply_text(f"Checked {len(recipes)} recipe(s) - nothing missing, nothing to scan.")
        return

    for recipe in pending:
        _enqueue_recipe_scan(chat_id, recipe)

    await message.reply_text(
        f"Queued {len(pending)} of {len(recipes)} recipe(s) for scanning "
        f"({len(recipes) - len(pending)} already complete). I'll message you as each one finishes."
    )


@owner_only
async def scan_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/scan_week: batch Scan over every recipe scheduled in the current week's plan."""
    conn = context.bot_data["conn"]
    start_date, end_date = meal_service.week_bounds()
    meals = meal_service.list_meals_for_range(conn, start_date, end_date)
    recipe_ids = sorted({m["recipe_id"] for m in meals if m["recipe_id"] is not None})
    if not recipe_ids:
        await update.message.reply_text("No recipes with a saved id in this week's plan.")
        return

    recipes = [recipe_service.get_recipe(conn, rid) for rid in recipe_ids]
    recipes = [r for r in recipes if r is not None]
    await _scan_recipes_batch(update.message, update.effective_chat.id, recipes)


@owner_only
async def scan_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/scan_all: batch Scan over every saved recipe in the library."""
    conn = context.bot_data["conn"]
    recipes = recipe_service.list_all_recipes(conn)
    if not recipes:
        await update.message.reply_text("No saved recipes yet.")
        return

    await _scan_recipes_batch(update.message, update.effective_chat.id, recipes)


@owner_only
async def handle_edit_recipe_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    _, lang, recipe_id_str = query.data.split("_")
    recipe_id = int(recipe_id_str)
    conn = context.bot_data["conn"]
    recipe = recipe_service.get_recipe(conn, recipe_id)
    if recipe is None:
        await query.answer("Recipe not found.")
        return

    context.user_data["awaiting_edit_recipe_name"] = {"recipe_id": recipe_id, "language": lang}
    await query.answer()
    current = recipe[f"name_{lang}"] or "(empty)"
    await query.message.reply_text(
        f"Current {_LANG_LABELS[lang]} name: {current}\nSend the new {_LANG_LABELS[lang]} name."
    )


async def try_handle_edit_recipe_name_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    pending = context.user_data.get("awaiting_edit_recipe_name")
    if pending is None:
        return False

    context.user_data.pop("awaiting_edit_recipe_name", None)
    conn = context.bot_data["conn"]
    new_name = update.message.text.strip()
    recipe_service.set_name_for_language(conn, pending["recipe_id"], pending["language"], new_name)
    await update.message.reply_text("Name updated.")
    await _send_edit_recipe_screen(update.message, context, pending["recipe_id"])
    return True


@owner_only
async def handle_edit_recipe_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    _, lang, recipe_id_str = query.data.split("_")
    recipe_id = int(recipe_id_str)
    conn = context.bot_data["conn"]
    recipe = recipe_service.get_recipe(conn, recipe_id)
    if recipe is None:
        await query.answer("Recipe not found.")
        return

    context.user_data["awaiting_edit_recipe_link"] = {"recipe_id": recipe_id, "language": lang}
    await query.answer()
    current = recipe[f"link_{lang}"] or "(not set)"
    await query.message.reply_text(
        f"Current {_LANG_LABELS[lang]} link: {current}\nSend the new {_LANG_LABELS[lang]} URL (or '-' to clear)."
    )


async def try_handle_edit_recipe_link_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    pending = context.user_data.get("awaiting_edit_recipe_link")
    if pending is None:
        return False

    context.user_data.pop("awaiting_edit_recipe_link", None)
    conn = context.bot_data["conn"]
    text = update.message.text.strip()
    new_link = None if text == "-" else text
    recipe_service.set_link_for_language(conn, pending["recipe_id"], pending["language"], new_link)
    await update.message.reply_text("Link updated." if new_link else "Link cleared.")
    await _send_edit_recipe_screen(update.message, context, pending["recipe_id"])
    return True


@owner_only
async def handle_edit_recipe_notes_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    recipe_id = int(query.data.rsplit("_", 1)[1])
    conn = context.bot_data["conn"]
    recipe = recipe_service.get_recipe(conn, recipe_id)
    if recipe is None:
        await query.answer("Recipe not found.")
        return

    context.user_data["awaiting_edit_recipe_notes"] = recipe_id
    await query.answer()
    current = recipe["notes"] or "(empty)"
    await query.message.reply_text(f"Current notes: {current}\nSend the new notes (or '-' to clear).")


async def try_handle_edit_recipe_notes_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    recipe_id = context.user_data.get("awaiting_edit_recipe_notes")
    if recipe_id is None:
        return False

    context.user_data.pop("awaiting_edit_recipe_notes", None)
    conn = context.bot_data["conn"]
    text = update.message.text.strip()
    new_notes = None if text == "-" else text
    recipe_service.update_notes(conn, recipe_id, new_notes)
    await update.message.reply_text("Notes updated." if new_notes else "Notes cleared.")
    await _send_edit_recipe_screen(update.message, context, recipe_id)
    return True


_NUTRITION_STEPS = ("calories", "fat", "protein", "carbs")
_NUTRITION_PROMPTS = {
    "calories": "Calories per 100g? (number)",
    "fat": "Fat per 100g (g)?",
    "protein": "Protein per 100g (g)?",
    "carbs": "Carbs per 100g (g)?",
}


@owner_only
async def handle_edit_recipe_nutrition_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    recipe_id = int(query.data.rsplit("_", 1)[1])
    conn = context.bot_data["conn"]
    if recipe_service.get_recipe(conn, recipe_id) is None:
        await query.answer("Recipe not found.")
        return

    context.user_data["editing_recipe_nutrition"] = {
        "recipe_id": recipe_id,
        "step": "calories",
        "values": {},
    }
    await query.answer()
    await query.message.reply_text(_NUTRITION_PROMPTS["calories"])


async def try_handle_edit_recipe_nutrition_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    pending = context.user_data.get("editing_recipe_nutrition")
    if pending is None:
        return False

    text = update.message.text.strip().replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        await update.message.reply_text("Please send a number.")
        return True

    step = pending["step"]
    pending["values"][step] = number

    next_index = _NUTRITION_STEPS.index(step) + 1
    if next_index < len(_NUTRITION_STEPS):
        pending["step"] = _NUTRITION_STEPS[next_index]
        await update.message.reply_text(_NUTRITION_PROMPTS[pending["step"]])
        return True

    context.user_data.pop("editing_recipe_nutrition", None)
    conn = context.bot_data["conn"]
    values = pending["values"]
    recipe_service.update_nutrition_per_100g(
        conn,
        pending["recipe_id"],
        int(values["calories"]),
        values["protein"],
        values["carbs"],
        values["fat"],
    )
    await update.message.reply_text("Nutrition updated.")
    await _send_edit_recipe_screen(update.message, context, pending["recipe_id"])
    return True


@owner_only
async def handle_edit_recipe_difficulty_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    recipe_id = int(query.data.rsplit("_", 1)[1])
    conn = context.bot_data["conn"]
    if recipe_service.get_recipe(conn, recipe_id) is None:
        await query.answer("Recipe not found.")
        return

    await query.answer()
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"{value}: {label}", callback_data=f"erdiffset_{value}_{recipe_id}")]
            for value, label in recipe_service.DIFFICULTY_LABELS.items()
        ]
    )
    await query.message.reply_text("Pick a difficulty:", reply_markup=keyboard)


@owner_only
async def handle_edit_recipe_difficulty_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    _, value_str, recipe_id_str = query.data.split("_")
    difficulty = int(value_str)
    recipe_id = int(recipe_id_str)
    conn = context.bot_data["conn"]
    if recipe_service.get_recipe(conn, recipe_id) is None:
        await query.answer("Recipe not found.")
        return

    recipe_service.set_difficulty(conn, recipe_id, difficulty)
    await query.answer()
    await query.message.reply_text(f"Difficulty set to {recipe_service.DIFFICULTY_LABELS[difficulty]}.")
    await _send_edit_recipe_screen(query.message, context, recipe_id)


@owner_only
async def handle_edit_recipe_prep_time_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    recipe_id = int(query.data.rsplit("_", 1)[1])
    conn = context.bot_data["conn"]
    recipe = recipe_service.get_recipe(conn, recipe_id)
    if recipe is None:
        await query.answer("Recipe not found.")
        return

    context.user_data["awaiting_edit_recipe_prep_time"] = recipe_id
    await query.answer()
    current = f"{recipe['prep_time_minutes']} min" if recipe["prep_time_minutes"] is not None else "(not set)"
    await query.message.reply_text(
        f"Current prep time: {current}\nSend the prep time in minutes (or '-' to clear)."
    )


async def try_handle_edit_recipe_prep_time_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    recipe_id = context.user_data.get("awaiting_edit_recipe_prep_time")
    if recipe_id is None:
        return False

    context.user_data.pop("awaiting_edit_recipe_prep_time", None)
    conn = context.bot_data["conn"]
    text = update.message.text.strip()
    if text == "-":
        recipe_service.set_prep_time_minutes(conn, recipe_id, None)
        await update.message.reply_text("Prep time cleared.")
    else:
        try:
            minutes = int(text)
        except ValueError:
            await update.message.reply_text("Please send a whole number of minutes, or '-' to clear.")
            return True
        recipe_service.set_prep_time_minutes(conn, recipe_id, minutes)
        await update.message.reply_text("Prep time updated.")

    await _send_edit_recipe_screen(update.message, context, recipe_id)
    return True


@owner_only
async def handle_edit_recipe_cook_time_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    recipe_id = int(query.data.rsplit("_", 1)[1])
    conn = context.bot_data["conn"]
    recipe = recipe_service.get_recipe(conn, recipe_id)
    if recipe is None:
        await query.answer("Recipe not found.")
        return

    context.user_data["awaiting_edit_recipe_cook_time"] = recipe_id
    await query.answer()
    current = f"{recipe['cook_time_minutes']} min" if recipe["cook_time_minutes"] is not None else "(not set)"
    await query.message.reply_text(
        f"Current cook time: {current}\nSend the cook time in minutes (or '-' to clear)."
    )


async def try_handle_edit_recipe_cook_time_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    recipe_id = context.user_data.get("awaiting_edit_recipe_cook_time")
    if recipe_id is None:
        return False

    context.user_data.pop("awaiting_edit_recipe_cook_time", None)
    conn = context.bot_data["conn"]
    text = update.message.text.strip()
    if text == "-":
        recipe_service.set_cook_time_minutes(conn, recipe_id, None)
        await update.message.reply_text("Cook time cleared.")
    else:
        try:
            minutes = int(text)
        except ValueError:
            await update.message.reply_text("Please send a whole number of minutes, or '-' to clear.")
            return True
        recipe_service.set_cook_time_minutes(conn, recipe_id, minutes)
        await update.message.reply_text("Cook time updated.")

    await _send_edit_recipe_screen(update.message, context, recipe_id)
    return True


@owner_only
async def handle_edit_recipe_oven_temp_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    recipe_id = int(query.data.rsplit("_", 1)[1])
    conn = context.bot_data["conn"]
    recipe = recipe_service.get_recipe(conn, recipe_id)
    if recipe is None:
        await query.answer("Recipe not found.")
        return

    context.user_data["awaiting_edit_recipe_oven_temp"] = recipe_id
    await query.answer()
    current = f"{recipe['oven_temperature_c']} °C" if recipe["oven_temperature_c"] is not None else "(not set)"
    await query.message.reply_text(
        f"Current oven temperature: {current}\n"
        "Send the oven temperature in °C (or '-' to clear, e.g. if no oven is needed)."
    )


async def try_handle_edit_recipe_oven_temp_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    recipe_id = context.user_data.get("awaiting_edit_recipe_oven_temp")
    if recipe_id is None:
        return False

    context.user_data.pop("awaiting_edit_recipe_oven_temp", None)
    conn = context.bot_data["conn"]
    text = update.message.text.strip()
    if text == "-":
        recipe_service.set_oven_temperature_c(conn, recipe_id, None)
        await update.message.reply_text("Oven temperature cleared.")
    else:
        try:
            celsius = int(text)
        except ValueError:
            await update.message.reply_text("Please send a whole number of degrees, or '-' to clear.")
            return True
        recipe_service.set_oven_temperature_c(conn, recipe_id, celsius)
        await update.message.reply_text("Oven temperature updated.")

    await _send_edit_recipe_screen(update.message, context, recipe_id)
    return True


@owner_only
async def recipe_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args and context.args[0].isdigit():
        await _send_recipe_details(update, context, int(context.args[0]))
        return

    context.user_data["awaiting_recipe_details"] = True
    await update.message.reply_text("Which recipe ID? Use /recipes to see the IDs.")


async def try_handle_recipe_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not context.user_data.get("awaiting_recipe_details"):
        return False

    context.user_data.pop("awaiting_recipe_details", None)
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text(
            "That doesn't look like a valid recipe ID. Use /recipe_details to try again."
        )
        return True

    await _send_recipe_details(update, context, int(text))
    return True


async def _send_recipe_details(update: Update, context: ContextTypes.DEFAULT_TYPE, recipe_id: int) -> None:
    conn = context.bot_data["conn"]
    recipe = recipe_service.get_recipe(conn, recipe_id)
    if recipe is None:
        await update.message.reply_text(f"No recipe found with id {recipe_id}.")
        return

    # Same fields /edit_recipe shows and Scan fills in (per-language names/links,
    # per-100g nutrition, cooking info) - ingredients/instructions are a separate,
    # rarely-populated legacy field pair, so they're appended only when present
    # rather than gating the whole response on them.
    text = _format_recipe_text(recipe)

    ingredients = json.loads(recipe["ingredients"]) if recipe["ingredients"] else None
    if ingredients and recipe["instructions"]:
        ingredients_text = "\n".join(f"- {item}" for item in ingredients)
        text += f"\n\nIngredients:\n{ingredients_text}\n\nInstructions:\n{recipe['instructions']}"

    buttons = []
    for lang, label in (("link_it", "Open (IT)"), ("link_es", "Open (ES)"), ("link_en", "Open (EN)")):
        link = recipe[lang]
        if link and link.startswith(("http://", "https://")):
            buttons.append(InlineKeyboardButton(label, url=link))

    keyboard = InlineKeyboardMarkup([buttons]) if buttons else None
    await update.message.reply_text(text, reply_markup=keyboard)
