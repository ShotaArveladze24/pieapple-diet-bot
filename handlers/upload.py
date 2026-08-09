"""PDF upload is disabled because AI extraction has been removed."""

from telegram import Update
from telegram.ext import ContextTypes

from access_control import owner_only

PDF_DISABLED_MESSAGE = (
    "PDF upload is disabled because AI extraction has been removed. "
    "Use manual commands like /addrecipe, /today, /tomorrow, and /week."
)


@owner_only
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(PDF_DISABLED_MESSAGE)
