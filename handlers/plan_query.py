"""/today, /tomorrow, /week and /agenda: browse the plan."""

from datetime import date, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import calendar_link
import meal_service
import recipe_service
from access_control import owner_only
from handlers import recipe_library
from i18n import meal_type_label, t

_AGENDA_SLOTS = (("breakfast", "BRE"), ("lunch", "LUN"), ("dinner", "DIN"))


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
    """/agenda: a 7-day calendar view, one message per day with a BRE/LUN/DIN button
    row. Telegram buttons can't actually be disabled or recolored, so a filled slot
    (recipe assigned) is marked with ✅ and opens that meal's full recipe details -
    same as /recipe_details - plus Calendar/Delete/Substitute actions; an empty slot
    (▫️) just answers "no meal planned" when tapped."""
    conn = context.bot_data["conn"]
    start_date = date.today()
    end_date = start_date + timedelta(days=6)
    meals = meal_service.list_meals_for_range(conn, start_date.isoformat(), end_date.isoformat())
    days_off = set(meal_service.list_days_off_in_range(conn, start_date.isoformat(), end_date.isoformat()))
    meals_by_slot = {(meal["date"], meal["meal_type"]): meal for meal in meals}

    for offset in range(7):
        day = (start_date + timedelta(days=offset)).isoformat()
        if day in days_off:
            await update.message.reply_text(f"📅 {day} - Day off (off-plan)")
            continue

        buttons = []
        for meal_type, abbrev in _AGENDA_SLOTS:
            meal = meals_by_slot.get((day, meal_type))
            if meal is not None and meal["recipe_id"] is not None:
                buttons.append(InlineKeyboardButton(f"✅ {abbrev}", callback_data=f"agendaslot_{meal['id']}"))
            else:
                buttons.append(InlineKeyboardButton(f"▫️ {abbrev}", callback_data="agendaempty"))

        await update.message.reply_text(f"📅 {day}", reply_markup=InlineKeyboardMarkup([buttons]))


@owner_only
async def handle_agenda_slot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    meal_id = int(query.data.rsplit("_", 1)[1])
    conn = context.bot_data["conn"]
    meal = meal_service.get_meal(conn, meal_id)
    recipe = recipe_service.get_recipe(conn, meal["recipe_id"]) if meal and meal["recipe_id"] else None
    if recipe is None:
        await query.answer("No meal planned for this slot.")
        return

    await query.answer()
    text, link_buttons = recipe_library.build_recipe_details_text(recipe)

    cal_link = calendar_link.build_meal_reminder_link(meal["meal_type"], meal["date"], meal["dish_name"])
    rows = [[
        InlineKeyboardButton("CAL", url=cal_link),
        InlineKeyboardButton("DEL", callback_data=f"removeconfirm_{meal['id']}"),
        InlineKeyboardButton("SUBS", callback_data=f"replaceask_{meal['id']}"),
    ]]
    if link_buttons:
        rows.append(link_buttons)

    await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(rows))


@owner_only
async def handle_agenda_empty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer("No meal planned for this slot.", show_alert=True)
