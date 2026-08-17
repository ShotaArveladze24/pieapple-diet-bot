"""/upload_photo: logs a photo of a meal about to be eaten. The photo is downloaded
locally right away (data/meal_photos/<telegram_user_id>/...) so it survives even if the
Telegram message is later deleted, tagged with when it was sent and - if the user
shares one - a Telegram location. State machine in context.user_data["awaiting_meal_photo"],
the same "awaiting_*" pending-step pattern used by every other multi-step flow in this bot
(see handlers/recipe_library.py's add_link_start/try_handle_add_link)."""

import logging
import uuid
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import meal_photo_service
from access_control import owner_only
from config import MEAL_PHOTOS_DIR

logger = logging.getLogger(__name__)


def _skip_keyboard(photo_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Skip", callback_data=f"mealphotoskip_{photo_id}")]])


@owner_only
async def upload_photo_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["awaiting_meal_photo"] = {"step": "photo"}
    await update.message.reply_text("Send the photo now.")


@owner_only
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pending = context.user_data.get("awaiting_meal_photo")
    if not pending or pending.get("step") != "photo":
        await update.message.reply_text("Send /upload_photo first if you want to log a meal photo.")
        return

    user_id = update.effective_user.id
    # python-telegram-bot always JPEG-encodes `message.photo` uploads, so a hardcoded
    # extension is safe here (unlike Document uploads, which keep their original format).
    filename = f"{int(update.message.date.timestamp())}_{uuid.uuid4().hex[:8]}.jpg"
    photo_path = Path(MEAL_PHOTOS_DIR) / str(user_id) / filename

    try:
        photo_path.parent.mkdir(parents=True, exist_ok=True)
        file = await update.message.photo[-1].get_file()
        await file.download_to_drive(custom_path=str(photo_path))
    except Exception:
        logger.exception("Could not download meal photo")
        await update.message.reply_text("Could not save that photo - please try sending it again.")
        return

    conn = context.bot_data["conn"]
    taken_at = update.message.date.strftime("%Y-%m-%d %H:%M:%S")
    photo_id = meal_photo_service.add_photo(conn, user_id, str(photo_path), taken_at)

    context.user_data["awaiting_meal_photo"] = {"step": "location", "photo_id": photo_id}
    await update.message.reply_text(
        "Photo saved. Share your location now (Attach > Location) so I can save where "
        "this was taken, or tap Skip.",
        reply_markup=_skip_keyboard(photo_id),
    )


@owner_only
async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pending = context.user_data.get("awaiting_meal_photo")
    if not pending or pending.get("step") != "location":
        await update.message.reply_text("No meal photo is waiting for a location right now.")
        return

    location = update.message.location
    conn = context.bot_data["conn"]
    meal_photo_service.set_location(conn, pending["photo_id"], location.latitude, location.longitude)
    context.user_data.pop("awaiting_meal_photo", None)

    maps_link = f"https://maps.google.com/?q={location.latitude},{location.longitude}"
    await update.message.reply_text(f"Location saved: {maps_link}")


@owner_only
async def handle_skip_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    photo_id = int(query.data.rsplit("_", 1)[1])

    pending = context.user_data.get("awaiting_meal_photo")
    if not pending or pending.get("step") != "location" or pending.get("photo_id") != photo_id:
        # A Skip button from an earlier /upload_photo run, tapped after a newer one has
        # already started - the current pending state belongs to a different photo now.
        await query.answer()
        return

    context.user_data.pop("awaiting_meal_photo", None)
    await query.answer()
    await query.message.reply_text("Saved without location.")
