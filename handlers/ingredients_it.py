"""/scan_ingredienti_IT: batch-scrapes the Italian ingredient list (with quantities)
for every recipe that has a link_it but no saved Italian ingredients yet.
/all_ingredients_IT: lists every saved Italian ingredient with how many recipes
contain it and the highest recipe ids among them."""

import json

from telegram import Update
from telegram.ext import ContextTypes

import ai_queue_service
import ingredient_service
import recipe_service
from access_control import owner_only
from text_utils import chunk_message


def _enqueue_ingredient_scan_it(chat_id: int, recipe) -> None:
    """Queues a scan_recipe AI request scoped to Italian ingredients only - unlike
    handlers/recipe_library.py's general Scan sweep, this never asks for missing
    links/names/nutrition even if the recipe also happens to be missing those, since
    this command's job is specifically to backfill ingredients."""
    ingredients = json.loads(recipe["ingredients"]) if recipe["ingredients"] else None
    ai_queue_service.enqueue(
        "scan_recipe",
        chat_id=chat_id,
        payload={
            "recipe_id": recipe["id"],
            "name": recipe["name"],
            "ingredients": ingredients,
            "missing_links": [],
            "missing_names": [],
            "needs_nutrition": False,
            "link_it": recipe["link_it"],
            "needs_ingredients_it": True,
        },
    )


@owner_only
async def scan_ingredienti_it(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/scan_ingredienti_IT: batch Scan of Italian ingredients over every recipe with a
    saved Italian link."""
    conn = context.bot_data["conn"]
    candidates = [r for r in recipe_service.list_all_recipes(conn) if r["link_it"]]
    if not candidates:
        await update.message.reply_text("No saved recipes have an Italian link yet.")
        return

    pending = [r for r in candidates if not ingredient_service.has_ingredients_it(conn, r["id"])]
    if not pending:
        await update.message.reply_text(
            f"Checked {len(candidates)} recipe(s) with an Italian link - "
            "all already have saved ingredients."
        )
        return

    for recipe in pending:
        _enqueue_ingredient_scan_it(update.effective_chat.id, recipe)

    await update.message.reply_text(
        f"Queued {len(pending)} of {len(candidates)} recipe(s) for Italian ingredient "
        f"scanning ({len(candidates) - len(pending)} already complete). "
        "I'll message you as each one finishes."
    )


@owner_only
async def all_ingredients_it(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/all_ingredients_IT: every saved Italian ingredient, how many recipes contain
    it, and the highest recipe ids among them."""
    conn = context.bot_data["conn"]
    usage = ingredient_service.list_ingredient_usage_it(conn)
    if not usage:
        await update.message.reply_text("No Italian ingredients saved yet. Run /scan_ingredienti_IT first.")
        return

    lines = [
        f"{item['name']} - {item['count']} recipe(s), top IDs: "
        f"{', '.join(str(i) for i in item['top_recipe_ids'])}"
        for item in usage
    ]
    text = f"Saved Italian ingredients ({len(usage)}):\n\n" + "\n".join(lines)
    for chunk in chunk_message(text):
        await update.message.reply_text(chunk)
