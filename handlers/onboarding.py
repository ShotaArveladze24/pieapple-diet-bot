"""/start and /help commands. /start is not filtered so the owner can discover
their Telegram user id during initial setup. On first use, /start also asks which
language Claude-generated recipe content (substitutions, details, nutrition) should use;
the fixed bot UI text itself always stays English."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import settings_service
from access_control import owner_only
from config import ALLOWED_TELEGRAM_IDS

LANGUAGE_NAMES = {"en": "English", "it": "Italiano", "es": "Espanol"}

HELP_TEXT = (
    "Available commands:\n"
    "/today - today's meals\n"
    "/tomorrow - tomorrow's meals\n"
    "/week - this week's plan\n"
    "/agenda - the next 7 days' plan, with Calendar/Remove/Link/Replace buttons per meal\n"
    "/recipes - list saved recipes, with link editing\n"
    "/recipe_details <id> - ingredients, quantities, instructions and nutrition for a recipe\n"
    "/add_link <id> <it|es|en> - add or overwrite a recipe's link for a language\n"
    "/edit_recipe_name <id> - rename a recipe\n"
    "/replace_recipe - swap an existing library recipe into a date/meal slot\n"
    "/reschedule - move a planned meal to a different day\n"
    "/remove <id> - delete a scheduled meal (id shown in /agenda)\n"
    "/addrecipe - add a recipe manually\n"
    "/dayoff - mark a day as off-plan\n"
    "/dayon - put a day back on the plan\n"
    "/clear_past - delete past days' recipes\n"
    "/clear_future - delete future days' recipes\n"
    "/language - change the recipe content language (EN/IT/ES)\n"
    "/report - adherence to the plan this week\n\n"
    "Use /addrecipe to add meals manually.\n"
    "Just write what you ate to log it."
)


def _language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("English", callback_data="setlang_en"),
        InlineKeyboardButton("Italiano", callback_data="setlang_it"),
        InlineKeyboardButton("Espanol", callback_data="setlang_es"),
    ]])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not ALLOWED_TELEGRAM_IDS:
        await update.message.reply_text(
            f"Your Telegram user id is {user_id}.\n"
            "Set it as OWNER_TELEGRAM_ID in the .env file and restart the bot."
        )
        return
    if user_id not in ALLOWED_TELEGRAM_IDS:
        await update.message.reply_text("This bot is private.")
        return

    conn = context.bot_data["conn"]
    if settings_service.get_content_language(conn) is None:
        await update.message.reply_text(
            "Hi! I'm PieappleDietBot.\n\n"
            "Which language should I use for recipe content (substitutions, recipe "
            "details, nutrition)? The bot's own messages will stay in English.",
            reply_markup=_language_keyboard(),
        )
        return

    await update.message.reply_text("Hi! I'm PieappleDietBot.\n\n" + HELP_TEXT)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT)


@owner_only
async def language_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Which language should I use for recipe content?", reply_markup=_language_keyboard()
    )


@owner_only
async def handle_set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    language = query.data.split("_", 1)[1]
    conn = context.bot_data["conn"]
    settings_service.set_content_language(conn, language)
    await query.answer()
    await query.edit_message_text(f"Recipe content language set to {LANGUAGE_NAMES[language]}.\n\n" + HELP_TEXT)
