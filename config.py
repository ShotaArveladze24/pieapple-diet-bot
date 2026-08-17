"""Configurazione PieappleDietBot."""

import os

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

OWNER_TELEGRAM_ID = int(os.environ["OWNER_TELEGRAM_ID"]) if os.environ.get("OWNER_TELEGRAM_ID") else None

ALLOWED_TELEGRAM_IDS: set[int] = {OWNER_TELEGRAM_ID} if OWNER_TELEGRAM_ID else set()
for _raw_id in os.environ.get("EXTRA_TELEGRAM_IDS", "").split(","):
    _raw_id = _raw_id.strip()
    if _raw_id:
        ALLOWED_TELEGRAM_IDS.add(int(_raw_id))

DATABASE_PATH = os.environ.get("DATABASE_PATH", "data/pieapple.db")

# Where PDF-extraction and recipe-scan requests/responses are exchanged with the
# external Claude Code consumer (see ai_queue/SPEC.md) instead of calling the
# Anthropic API directly - no API key involved.
AI_QUEUE_DIR = os.environ.get("AI_QUEUE_DIR", "data/ai_queue")

# Where /upload_photo saves meal photos locally, one subfolder per Telegram user id -
# kept even if the Telegram message is later deleted.
MEAL_PHOTOS_DIR = os.environ.get("MEAL_PHOTOS_DIR", "data/meal_photos")

TIMEZONE = os.environ.get("TIMEZONE", "Europe/Rome")
