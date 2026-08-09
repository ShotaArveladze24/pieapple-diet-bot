"""Caricamento PDF: estrazione, riepilogo, conferma e sincronizzazione calendario.
Di default il piano viene applicato alla prossima settimana, con la possibilita' di
cambiare la settimana di destinazione prima di confermare."""

import tempfile
from datetime import date, timedelta
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import calendar_service
import claude_client
import meal_service
import recipe_service
from access_control import owner_only
from date_utils import next_monday, parse_week_start, resolve_day_date
from i18n import meal_type_label, t
from pdf_extractor import extract_text

_TELEGRAM_MESSAGE_LIMIT = 3500


def _chunk_text(text: str, limit: int = _TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    lines = text.split("\n")
    chunks = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            if current:
                chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _next_free_date(conn, meal_date: str, meal_type: str) -> str:
    """If a meal is already scheduled for this date/meal-type, pushes forward a week at
    a time until a free slot is found, rather than creating a duplicate."""
    current = date.fromisoformat(meal_date)
    while meal_service.get_meal_by_date_type(conn, current.isoformat(), meal_type) is not None:
        current += timedelta(days=7)
    return current.isoformat()


def _format_summary(plan: dict, week_monday: str) -> tuple[str, list[dict]]:
    language = plan.get("language", "it")
    lines = []
    resolved_meals = []
    for day_index, day in enumerate(plan["days"]):
        meal_date = resolve_day_date(day["day_label"], day_index, week_monday)
        lines.append(f"\n📅 {day['day_label']} ({meal_date})")
        for meal in day["meals"]:
            label = meal_type_label(meal["meal_type"], language)
            lines.append(f"  • {label}: {meal['dish_name']}")
            resolved_meals.append({**meal, "date": meal_date})
    return "\n".join(lines).strip(), resolved_meals


async def _send_pending_plan(message, context: ContextTypes.DEFAULT_TYPE) -> None:
    pending = context.user_data["pending_plan"]
    summary, resolved_meals = _format_summary(pending["raw_plan"], pending["week_start_date"])
    pending["meals"] = resolved_meals

    header = f"Week starting {pending['week_start_date']}:\n{summary}"
    for chunk in _chunk_text(header):
        await message.reply_text(chunk)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("confirm_button", pending["language"]), callback_data="upload_confirm")],
        [InlineKeyboardButton("Change week", callback_data="upload_changeweek")],
        [InlineKeyboardButton("Cancel", callback_data="upload_cancel")],
    ])
    await message.reply_text("Confirm?", reply_markup=keyboard)


async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    document = update.message.document
    status = await update.message.reply_text("Received. Extracting...")

    with tempfile.TemporaryDirectory() as tmp_dir:
        pdf_path = Path(tmp_dir) / document.file_name
        telegram_file = await context.bot.get_file(document.file_id)
        await telegram_file.download_to_drive(str(pdf_path))
        raw_text = extract_text(str(pdf_path))

    if not raw_text.strip():
        await status.edit_text("I couldn't read any text from this PDF.")
        return

    plan = claude_client.extract_plan(raw_text)
    await status.edit_text("Extraction complete.")

    context.user_data["pending_plan"] = {
        "source_filename": document.file_name,
        "language": plan.get("language", "it"),
        "week_start_date": next_monday(),
        "raw_plan": plan,
    }
    await _send_pending_plan(update.message, context)


@owner_only
async def handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    pending = context.user_data.get("pending_plan")
    if not pending:
        await query.answer()
        await query.edit_message_text("No pending plan.")
        return

    conn = context.bot_data["conn"]
    await query.answer()
    await query.edit_message_text("Saving and syncing recipes, this can take a moment...")

    plan_id = meal_service.create_plan(
        conn, pending["source_filename"], pending["language"], pending["week_start_date"]
    )

    shifted_count = 0
    for meal in pending["meals"]:
        target_date = _next_free_date(conn, meal["date"], meal["meal_type"])
        if target_date != meal["date"]:
            shifted_count += 1

        meal_id = meal_service.add_meal(
            conn,
            plan_id,
            target_date,
            meal["meal_type"],
            meal["dish_name"],
            meal.get("description"),
            meal.get("ingredients"),
            meal.get("instructions"),
            meal.get("recipe_link"),
            meal.get("calories"),
            meal.get("macros"),
        )
        recipe_id = None
        try:
            recipe_id = recipe_service.link_meal_to_recipe(
                conn, meal["dish_name"], pending["language"], meal.get("recipe_link")
            )
            meal_service.set_recipe_id(conn, meal_id, recipe_id)
        except Exception as exc:
            await query.message.reply_text(f"Warning: recipe lookup failed for '{meal['dish_name']}': {exc}")

        calendar_link = meal.get("recipe_link")
        if recipe_id:
            recipe = recipe_service.get_recipe(conn, recipe_id)
            if recipe:
                calendar_link = recipe_service.pick_display_link(recipe) or calendar_link
        try:
            event_id = calendar_service.create_event(
                meal["date"], meal["meal_type"], meal["dish_name"], meal.get("description") or "",
                recipe_id=recipe_id, link=calendar_link,
            )
            meal_service.set_calendar_event_id(conn, meal_id, event_id)
        except Exception as exc:
            await query.message.reply_text(f"Warning: Calendar sync failed for '{meal['dish_name']}': {exc}")

    context.user_data.pop("pending_plan", None)
    await query.message.reply_text(t("plan_saved", pending["language"]))


@owner_only
async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    context.user_data.pop("pending_plan", None)
    context.user_data.pop("awaiting_week_change", None)
    await query.answer()
    await query.edit_message_text("Cancelled.")


@owner_only
async def handle_change_week_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not context.user_data.get("pending_plan"):
        await query.answer()
        await query.edit_message_text("No pending plan.")
        return

    context.user_data["awaiting_week_change"] = True
    await query.answer()
    await query.message.reply_text(
        "Which week? (e.g. 'this week', 'next week', or a date like 2026-08-24)"
    )


async def try_handle_week_change(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not context.user_data.get("awaiting_week_change"):
        return False

    context.user_data.pop("awaiting_week_change", None)
    pending = context.user_data.get("pending_plan")
    if not pending:
        await update.message.reply_text("No pending plan.")
        return True

    new_monday = parse_week_start(update.message.text)
    if new_monday is None:
        await update.message.reply_text("I didn't understand that week. Try again.")
        context.user_data["awaiting_week_change"] = True
        return True

    pending["week_start_date"] = new_monday
    await _send_pending_plan(update.message, context)
    return True
