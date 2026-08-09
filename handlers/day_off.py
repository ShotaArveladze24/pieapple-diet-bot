"""/dayoff and /dayon: days where the plan isn't followed (e.g. eating out, cheat day)."""

from telegram import Update
from telegram.ext import ContextTypes

import meal_service
from access_control import owner_only
from date_utils import parse_user_date


@owner_only
async def dayoff_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["awaiting_dayoff"] = "off"
    await update.message.reply_text(
        "Which day do you want to mark as off (off-plan)? "
        "(e.g. 'today', 'tomorrow', 'monday', 2026-08-15)"
    )


@owner_only
async def dayon_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["awaiting_dayoff"] = "on"
    await update.message.reply_text(
        "Which day do you want to put back on the plan? (e.g. 'today', 'tomorrow', 'monday', 2026-08-15)"
    )


async def try_handle_dayoff_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    mode = context.user_data.get("awaiting_dayoff")
    if mode is None:
        return False
    context.user_data.pop("awaiting_dayoff", None)

    resolved = parse_user_date(update.message.text)
    if resolved is None:
        await update.message.reply_text("I didn't understand that date.")
        return True

    conn = context.bot_data["conn"]

    if mode == "off":
        meal_service.mark_day_off(conn, resolved)
        await update.message.reply_text(f"{resolved} marked as a day off (off-plan).")
    else:
        meal_service.unmark_day_off(conn, resolved)
        await update.message.reply_text(f"{resolved} put back on the plan.")

    return True
