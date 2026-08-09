"""/remove <id>: delete a single already-scheduled meal, with confirmation.
The id is the meal id shown in /agenda."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import meal_service
from access_control import owner_only
from i18n import meal_type_label


@owner_only
async def remove_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /remove <id>. Use /agenda to see the ids.")
        return

    meal_id = int(context.args[0])
    conn = context.bot_data["conn"]
    meal = meal_service.get_meal(conn, meal_id)
    if meal is None:
        await update.message.reply_text(f"No scheduled meal found with id {meal_id}.")
        return

    label = meal_type_label(meal["meal_type"])
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Confirm", callback_data=f"removeconfirm_{meal_id}"),
        InlineKeyboardButton("Cancel", callback_data=f"removecancel_{meal_id}"),
    ]])
    await update.message.reply_text(
        f"Remove {label} on {meal['date']}: {meal['dish_name']}?",
        reply_markup=keyboard,
    )


@owner_only
async def handle_remove_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    meal_id = int(query.data.split("_", 1)[1])
    conn = context.bot_data["conn"]
    meal = meal_service.get_meal(conn, meal_id)

    await query.answer()
    if meal is None:
        await query.edit_message_text("Already removed.")
        return

    meal_service.delete_meal(conn, meal_id)
    label = meal_type_label(meal["meal_type"])
    await query.edit_message_text(f"Removed {label} on {meal['date']}: {meal['dish_name']}.")


@owner_only
async def handle_remove_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Cancelled.")
