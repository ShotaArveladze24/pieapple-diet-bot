"""/today, /tomorrow and /week: browse the plan."""

from datetime import date, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import meal_service
from i18n import meal_type_label, t


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = context.bot_data["conn"]
    today_date = date.today().isoformat()

    if meal_service.is_day_off(conn, today_date):
        await update.message.reply_text("Today is a day off: no meals planned.")
        return

    meals = meal_service.list_meals_for_date(conn, today_date)

    if not meals:
        await update.message.reply_text(t("no_meals_today"))
        return

    for meal in meals:
        label = meal_type_label(meal["meal_type"])
        text = f"{label}: {meal['dish_name']}"
        if meal["recipe_link"]:
            text += f"\n{meal['recipe_link']}"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(t("recipe_button"), callback_data=f"recipe_{meal['id']}"),
        ]])
        await update.message.reply_text(text, reply_markup=keyboard)


async def tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = context.bot_data["conn"]
    tomorrow_date = (date.today() + timedelta(days=1)).isoformat()

    if meal_service.is_day_off(conn, tomorrow_date):
        await update.message.reply_text("Tomorrow is a day off: no meals planned.")
        return

    meals = meal_service.list_meals_for_date(conn, tomorrow_date)

    if not meals:
        await update.message.reply_text("No meals are scheduled for tomorrow.")
        return

    for meal in meals:
        label = meal_type_label(meal["meal_type"])
        text = f"{label}: {meal['dish_name']}"
        if meal["recipe_link"]:
            text += f"\n{meal['recipe_link']}"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(t("recipe_button"), callback_data=f"recipe_{meal['id']}"),
        ]])
        await update.message.reply_text(text, reply_markup=keyboard)


async def week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = context.bot_data["conn"]
    start_date, end_date = meal_service.week_bounds()
    meals = meal_service.list_meals_for_range(conn, start_date, end_date)

    if not meals:
        await update.message.reply_text(t("no_meals_today"))
        return

    days_off = set(meal_service.list_days_off_in_range(conn, start_date, end_date))
    lines = []
    current_date = None
    for meal in meals:
        if meal["date"] in days_off:
            if meal["date"] != current_date:
                current_date = meal["date"]
                lines.append(f"\n📅 {current_date} - Day off (off-plan)")
            continue
        if meal["date"] != current_date:
            current_date = meal["date"]
            lines.append(f"\n📅 {current_date}")
        label = meal_type_label(meal["meal_type"])
        link = _ensure_recipe_link(conn, meal)
        line = f"  • {label}: {meal['dish_name']}"
        if link:
            line += f" ({link})"
        lines.append(line)

    await update.message.reply_text("\n".join(lines).strip())
