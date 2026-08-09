"""/today and /week: browse the plan with recipe links."""

from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import claude_client
import meal_service
from i18n import meal_type_label, t


def _ensure_recipe_link(conn, meal) -> str | None:
    if meal["recipe_link"]:
        return meal["recipe_link"]
    link = claude_client.find_recipe_link(meal["dish_name"], "en")
    if link:
        meal_service.update_recipe_link(conn, meal["id"], link)
    return link


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
        link = _ensure_recipe_link(conn, meal)
        label = meal_type_label(meal["meal_type"])
        text = f"{label}: {meal['dish_name']}"
        if link:
            text += f"\n{link}"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(t("recipe_button"), callback_data=f"recipe_{meal['id']}"),
            InlineKeyboardButton(t("substitute_button"), callback_data=f"substitute_{meal['id']}"),
            InlineKeyboardButton(t("nutrition_button"), callback_data=f"nutrition_{meal['id']}"),
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
