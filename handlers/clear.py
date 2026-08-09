"""/clear_past and /clear_future: bulk-remove recipes by date, with confirmation."""

from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import meal_service
from access_control import owner_only


async def _start_clear(update: Update, context: ContextTypes.DEFAULT_TYPE, scope: str, meals) -> None:
    label = "past" if scope == "past" else "future"
    if not meals:
        await update.message.reply_text(f"No recipes on {label} days.")
        return

    context.user_data["pending_clear"] = {"meal_ids": [meal["id"] for meal in meals]}
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Confirm", callback_data="clear_confirm"),
        InlineKeyboardButton("Cancel", callback_data="clear_cancel"),
    ]])
    await update.message.reply_text(
        f"About to delete {len(meals)} meals on {label} days. Confirm?",
        reply_markup=keyboard,
    )


@owner_only
async def clear_past_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = context.bot_data["conn"]
    meals = meal_service.list_meals_before(conn, date.today().isoformat())
    await _start_clear(update, context, "past", meals)


@owner_only
async def clear_future_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = context.bot_data["conn"]
    meals = meal_service.list_meals_after(conn, date.today().isoformat())
    await _start_clear(update, context, "future", meals)


@owner_only
async def handle_clear_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    pending = context.user_data.pop("pending_clear", None)
    if not pending:
        await query.answer()
        await query.edit_message_text("No pending deletion.")
        return

    conn = context.bot_data["conn"]
    deleted = 0
    for meal_id in pending["meal_ids"]:
        meal = meal_service.get_meal(conn, meal_id)
        if meal is None:
            continue
        meal_service.delete_meal(conn, meal_id)
        deleted += 1

    await query.answer()
    text = f"Deleted {deleted} meals."
    await query.edit_message_text(text)


@owner_only
async def handle_clear_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    context.user_data.pop("pending_clear", None)
    await query.answer()
    await query.edit_message_text("Cancelled.")
