"""Decorator to restrict callback queries to authorized users only.

CallbackQueryHandler doesn't support the filters parameter like CommandHandler/MessageHandler,
so the check has to be applied explicitly on every callback handler."""

import functools

from telegram import Update
from telegram.ext import ContextTypes

from config import ALLOWED_TELEGRAM_IDS


def owner_only(handler):
    @functools.wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if ALLOWED_TELEGRAM_IDS and update.effective_user.id not in ALLOWED_TELEGRAM_IDS:
            if update.callback_query:
                await update.callback_query.answer()
            return
        await handler(update, context)

    return wrapper
