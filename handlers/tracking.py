"""Logging what the user actually ate, and the adherence report."""

from datetime import date

from telegram import Update
from telegram.ext import ContextTypes

import meal_service


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
