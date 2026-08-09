"""Recipe import from a plain URL sent as a chat message: fetch the page, extract the
recipe with Claude (asking the language if it's unclear), then reuse /addrecipe's
day/meal-type scheduling flow to finalize it."""

import re

from telegram import Update
from telegram.ext import ContextTypes

import claude_client
import url_extractor
from handlers.recipe_library import parse_language

_URL_ONLY_RE = re.compile(r"^https?://\S+$")


def _looks_like_url(text: str) -> bool:
    return bool(_URL_ONLY_RE.match(text.strip()))


async def try_handle_url_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if context.user_data.get("awaiting_url_language"):
        return await _handle_language_reply(update, context)

    text = update.message.text.strip()
    if not _looks_like_url(text):
        return False

    status = await update.message.reply_text("Fetching the page...")
    try:
        page_text = url_extractor.fetch_url_text(text)
    except Exception as exc:
        await status.edit_text(f"Couldn't fetch that URL: {exc}")
        return True

    if not page_text.strip():
        await status.edit_text("Couldn't read any content from that page.")
        return True

    await status.edit_text("Extracting the recipe...")
    try:
        recipe = claude_client.extract_recipe_from_text(page_text)
    except Exception as exc:
        await status.edit_text(f"Couldn't extract a recipe from that page: {exc}")
        return True

    pending = {
        "prefilled": True,
        "dish_name": recipe["dish_name"],
        "ingredients": recipe.get("ingredients"),
        "instructions": recipe.get("instructions"),
        "calories": recipe.get("calories"),
        "macros": recipe.get("macros"),
        "link": text,
    }

    language = recipe.get("language")
    if language not in ("it", "es", "en"):
        context.user_data["awaiting_url_language"] = pending
        await status.edit_text(
            f"Found: {recipe['dish_name']}. What language is this recipe in? (IT/ES/EN)"
        )
        return True

    pending["language"] = language
    pending["step"] = "date"
    context.user_data["new_recipe"] = pending
    await status.edit_text(
        f"Found: {recipe['dish_name']} ({language.upper()}). "
        "Which day should it go on? (e.g. 'today', 'tomorrow', 'monday', or a date like 2026-08-15)"
    )
    return True


async def _handle_language_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    pending = context.user_data.pop("awaiting_url_language")
    language = parse_language(update.message.text)
    if language is None:
        await update.message.reply_text("I didn't understand. Write IT, ES or EN.")
        context.user_data["awaiting_url_language"] = pending
        return True

    pending["language"] = language
    pending["step"] = "date"
    context.user_data["new_recipe"] = pending
    await update.message.reply_text(
        "Which day should it go on? (e.g. 'today', 'tomorrow', 'monday', or a date like 2026-08-15)"
    )
    return True
