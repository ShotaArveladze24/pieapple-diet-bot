"""/today, /tomorrow, /week and /agenda: browse the plan."""

from datetime import date, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import calendar_link
import meal_service
import recipe_service
from i18n import meal_type_label, t

_LANGUAGE_LINK_COLUMNS = (("link_en", "Link EN"), ("link_es", "Link ES"), ("link_it", "Link IT"))


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
        line = f"  • {label}: {meal['dish_name']}"
        if meal["recipe_link"]:
            line += f" ({meal['recipe_link']})"
        lines.append(line)

    await update.message.reply_text("\n".join(lines).strip())


async def agenda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = context.bot_data["conn"]
    start_date = date.today().isoformat()
    end_date = (date.today() + timedelta(days=6)).isoformat()
    meals = meal_service.list_meals_for_range(conn, start_date, end_date)

    if not meals:
        await update.message.reply_text(t("no_meals_today"))
        return

    days_off = set(meal_service.list_days_off_in_range(conn, start_date, end_date))
    max_meals = 10
    current_date = None
    shown = 0
    truncated = False
    for meal in meals:
        if shown >= max_meals:
            truncated = True
            break
        if meal["date"] in days_off:
            if meal["date"] != current_date:
                current_date = meal["date"]
                await update.message.reply_text(f"📅 {current_date} - Day off (off-plan)")
            continue
        if meal["date"] != current_date:
            current_date = meal["date"]
            await update.message.reply_text(f"📅 {current_date}")

        label = meal_type_label(meal["meal_type"])
        text = f"[{meal['id']}] {label}: {meal['dish_name']}"
        if meal["recipe_id"]:
            text += f"\nRecipe ID: {meal['recipe_id']}"

        cal_link = calendar_link.build_meal_reminder_link(meal["meal_type"], meal["date"], meal["dish_name"])
        rows = [[
            InlineKeyboardButton("CAL", url=cal_link),
            InlineKeyboardButton("DEL", callback_data=f"removeconfirm_{meal['id']}"),
            InlineKeyboardButton("SUBS", callback_data=f"replaceask_{meal['id']}"),
        ]]

        link_row = []
        recipe = recipe_service.get_recipe(conn, meal["recipe_id"]) if meal["recipe_id"] else None
        if recipe is not None:
            for column, label in _LANGUAGE_LINK_COLUMNS:
                link = recipe[column]
                if link and link.startswith(("http://", "https://")):
                    link_row.append(InlineKeyboardButton(label, url=link))
        elif meal["recipe_link"] and meal["recipe_link"].startswith(("http://", "https://")):
            link_row.append(InlineKeyboardButton("Link", url=meal["recipe_link"]))
        if link_row:
            rows.append(link_row)

        keyboard = InlineKeyboardMarkup(rows)
        await update.message.reply_text(text, reply_markup=keyboard)
        shown += 1

    if truncated:
        await update.message.reply_text(
            f"Showing the next {max_meals} meals only. Use /week for the full calendar week."
        )
