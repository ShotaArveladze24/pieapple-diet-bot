"""Logging what the user actually ate, and the adherence report."""

from datetime import date

from telegram import Update
from telegram.ext import ContextTypes

import claude_client
import meal_service


async def handle_eaten_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = context.bot_data["conn"]
    today_date = date.today().isoformat()
    if meal_service.is_day_off(conn, today_date):
        return

    today_meals = meal_service.list_meals_for_date(conn, today_date)
    if not today_meals:
        return

    candidates = [
        {"id": m["id"], "meal_type": m["meal_type"], "dish_name": m["dish_name"]} for m in today_meals
    ]
    result = claude_client.match_eaten_meal(update.message.text, candidates)
    meal_id = result.get("matched_meal_id")
    if meal_id is None:
        return

    meal_service.log_consumption(conn, meal_id, result["status"], result.get("note"))
    meal = meal_service.get_meal(conn, meal_id)

    if result["status"] == "eaten_as_planned":
        await update.message.reply_text(f"Logged: {meal['dish_name']} as planned. ✅")
    elif result["status"] == "skipped":
        await update.message.reply_text(f"Logged: {meal['dish_name']} skipped. ⚠️")
    else:
        await update.message.reply_text(
            f"Logged as off-plan (planned meal was {meal['dish_name']}). ⚠️"
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
