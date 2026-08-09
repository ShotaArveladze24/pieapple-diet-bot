"""Recipe import from a plain URL sent as a chat message."""

import re

from telegram import Update
from telegram.ext import ContextTypes

_URL_ONLY_RE = re.compile(r"^https?://\S+$")


def _looks_like_url(text: str) -> bool:
    return bool(_URL_ONLY_RE.match(text.strip()))


async def try_handle_url_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    text = update.message.text.strip()
    if not _looks_like_url(text):
        return False

    await update.message.reply_text(
        "URL recipe import is disabled because AI extraction has been removed. Use /addrecipe instead."
    )
    return True
