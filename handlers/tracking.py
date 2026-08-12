"""Logging what the user actually ate, and the adherence report."""

from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import meal_service
from access_control import owner_only
from i18n import meal_type_label


async def handle_eaten_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = context.bot_data["conn"]
    today_date = date.today().isoformat()
    if meal_service.is_day_off(conn, today_date):
        return

    today_meals = meal_service.list_meals_for_date(conn, today_date)
    if not today_meals:
        return

    await update.message.reply_text(
        "Free-text meal logging is disabled because AI integration has been removed. "
        "Use /replace_recipe or /addrecipe to update your plan."
    )


async def report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = context.bot_data["conn"]
    start_date, end_date = meal_service.week_bounds()
    stats = meal_service.week_adherence_report(conn, start_date, end_date)

    text = (
        f"Plan adherence ({start_date} - {end_date}):\n"
        f"Total meals: {stats['total']}\n"
        f"As planned: {stats['on_plan']}\n"
        f"Different from plan: {stats['different']}\n"
        f"Skipped: {stats['skipped']}\n"
        f"Not logged: {stats['unlogged']}\n"
        f"Days off: {stats['days_off']}"
    )
    await update.message.reply_text(text)

    await _prompt_unlogged_meals(update, context, conn, start_date, end_date)


async def _prompt_unlogged_meals(
    update: Update, context: ContextTypes.DEFAULT_TYPE, conn, start_date: str, end_date: str
) -> None:
    """Sends one Yes/No prompt per already-happened meal in the reported week that
    hasn't been logged yet, so adherence can be recorded with a tap instead of typing
    (free-text logging was disabled along with the AI integration)."""
    today_str = date.today().isoformat()
    days_off = set(meal_service.list_days_off_in_range(conn, start_date, end_date))
    logged_ids = meal_service.list_logged_meal_ids(conn, start_date, end_date)
    meals = meal_service.list_meals_for_range(conn, start_date, min(end_date, today_str))

    pending = [m for m in meals if m["date"] not in days_off and m["id"] not in logged_ids]
    if not pending:
        return

    await update.message.reply_text("Did you stick to the plan for these meals?")
    for meal in pending:
        label = meal_type_label(meal["meal_type"])
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Yes", callback_data=f"adherence_yes_{meal['id']}"),
                    InlineKeyboardButton("No", callback_data=f"adherence_no_{meal['id']}"),
                ]
            ]
        )
        await update.message.reply_text(
            f"{meal['date']} - {label}: {meal['dish_name']}", reply_markup=keyboard
        )


@owner_only
async def handle_adherence_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    _, answer, meal_id_str = query.data.split("_")
    meal_id = int(meal_id_str)
    conn = context.bot_data["conn"]
    meal = meal_service.get_meal(conn, meal_id)

    await query.answer()
    if meal is None:
        await query.edit_message_text("This meal no longer exists.")
        return

    status = "eaten_as_planned" if answer == "yes" else "eaten_different"
    meal_service.log_consumption(conn, meal_id, status)
    result_label = "stuck to the plan" if answer == "yes" else "did not stick to the plan"
    label = meal_type_label(meal["meal_type"])
    await query.edit_message_text(f"{meal['date']} - {label}: {meal['dish_name']}\nMarked: {result_label}.")
