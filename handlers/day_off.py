"""/dayoff and /dayon: days where the plan isn't followed (e.g. eating out, cheat day)."""

from datetime import date, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import meal_service
from access_control import owner_only
from date_utils import parse_user_date

_QUICK_PICK_LABELS = ("Today", "Tomorrow", "+2 days", "+3 days")


def _quick_pick_keyboard() -> InlineKeyboardMarkup:
    today = date.today()
    buttons = []
    for offset, label in enumerate(_QUICK_PICK_LABELS):
        day = (today + timedelta(days=offset)).isoformat()
        buttons.append([InlineKeyboardButton(f"{label} ({day})", callback_data=f"dayoffset_{day}")])
    return InlineKeyboardMarkup(buttons)


@owner_only
async def dayoff_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["awaiting_dayoff"] = True
    await update.message.reply_text(
        "Which day do you want to mark as off (off-plan)? Pick one below, or type any "
        "other day (e.g. 'monday', 2026-08-15).",
        reply_markup=_quick_pick_keyboard(),
    )


@owner_only
async def dayon_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = context.bot_data["conn"]
    days_off = meal_service.list_all_days_off(conn)
    if not days_off:
        await update.message.reply_text("No days are currently marked off.")
        return

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(day, callback_data=f"dayonunset_{day}")] for day in days_off]
    )
    await update.message.reply_text(
        "Which day do you want to put back on the plan?", reply_markup=keyboard
    )


async def try_handle_dayoff_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not context.user_data.get("awaiting_dayoff"):
        return False
    context.user_data.pop("awaiting_dayoff", None)

    resolved = parse_user_date(update.message.text)
    if resolved is None:
        await update.message.reply_text("I didn't understand that date.")
        return True

    conn = context.bot_data["conn"]
    meal_service.mark_day_off(conn, resolved)
    await update.message.reply_text(f"{resolved} marked as a day off (off-plan).")
    return True


@owner_only
async def handle_dayoff_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    day = query.data.split("_", 1)[1]
    conn = context.bot_data["conn"]
    meal_service.mark_day_off(conn, day)
    await query.answer()
    await query.edit_message_text(f"{day} marked as a day off (off-plan).")


@owner_only
async def handle_dayon_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    day = query.data.split("_", 1)[1]
    conn = context.bot_data["conn"]
    meal_service.unmark_day_off(conn, day)
    await query.answer()
    await query.edit_message_text(f"{day} put back on the plan.")
