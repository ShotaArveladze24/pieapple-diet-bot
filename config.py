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

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")

DATABASE_PATH = os.environ.get("DATABASE_PATH", "data/pieapple.db")

TIMEZONE = os.environ.get("TIMEZONE", "Europe/Rome")
