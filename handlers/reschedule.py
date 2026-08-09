"""/reschedule: move a planned meal to a different (today or future) date."""

from datetime import date

from telegram import Update
from telegram.ext import ContextTypes

import meal_service
from access_control import owner_only
from date_utils import parse_user_date
from handlers.recipe_library import parse_meal_type
from i18n import meal_type_label


@owner_only
async def reschedule_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["awaiting_reschedule"] = {"step": "source_date"}
    await update.message.reply_text(
        "Which day is the meal you want to reschedule currently on? "
        "(e.g. 'today', 'tomorrow', 'monday', 2026-08-15)"
    )


async def try_handle_reschedule_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    pending = context.user_data.get("awaiting_reschedule")
    if pending is None:
        return False

    text = update.message.text.strip()
    step = pending["step"]
    conn = context.bot_data["conn"]

    if step == "source_date":
        resolved = parse_user_date(text)
        if resolved is None:
            await update.message.reply_text("I didn't understand that date. Try again.")
            return True
        pending["source_date"] = resolved
        pending["step"] = "meal_type"
        await update.message.reply_text("Breakfast, lunch or dinner?")
        return True

    if step == "meal_type":
        meal_type = parse_meal_type(text)
        if meal_type is None:
            await update.message.reply_text("I didn't understand. Write: breakfast, lunch or dinner.")
            return True
        meal = meal_service.get_meal_by_date_type(conn, pending["source_date"], meal_type)
        if meal is None:
            context.user_data.pop("awaiting_reschedule", None)
            label = meal_type_label(meal_type)
            await update.message.reply_text(f"No {label.lower()} scheduled on {pending['source_date']}.")
            return True
        pending["meal_id"] = meal["id"]
        pending["meal_type"] = meal_type
        pending["step"] = "target_date"
        await update.message.reply_text("Move it to which day?")
        return True

    if step == "target_date":
        resolved = parse_user_date(text)
        if resolved is None:
            await update.message.reply_text("I didn't understand that date. Try again.")
            return True
        if resolved < date.today().isoformat():
            await update.message.reply_text("Pick today or a day in the future.")
            return True
        if resolved == pending["source_date"]:
            await update.message.reply_text("That's the same day it's already on. Pick a different day.")
            return True

        context.user_data.pop("awaiting_reschedule", None)
        outcome = meal_service.reschedule_meal(conn, pending["meal_id"], resolved)
        label = meal_type_label(pending["meal_type"])
        if outcome == "swapped":
            await update.message.reply_text(
                f"{label} swapped between {pending['source_date']} and {resolved} "
                "(there was already a meal in that slot)."
            )
        else:
            await update.message.reply_text(f"{label} moved from {pending['source_date']} to {resolved}.")
        return True

    context.user_data.pop("awaiting_reschedule", None)
    return False
