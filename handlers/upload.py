"""PDF upload is disabled unless AI extraction is configured."""

import asyncio
import logging
import tempfile
from datetime import date, timedelta
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

import claude_client
import meal_service
import pdf_extractor
import recipe_service
from access_control import owner_only
from config import ANTHROPIC_API_KEY
from date_utils import next_monday, resolve_day_date

_VALID_MEAL_TYPES = ("breakfast", "lunch", "dinner")

logger = logging.getLogger(__name__)

TELEGRAM_MESSAGE_LIMIT = 4096

PDF_DISABLED_MESSAGE = (
    "PDF upload is disabled because AI extraction has been removed. "
    "Use manual commands like /addrecipe, /today, /tomorrow, and /week."
)

INVALID_PLAN_MESSAGE = (
    "The PDF was read, but the extracted plan was incomplete or invalid. "
    "Please try a different file or use manual commands like /addrecipe."
)


def _normalize_days(plan: dict) -> list[dict]:
    """Validates and normalizes the plan's day/meal structure up front, so a malformed
    plan fails before anything is written to the DB rather than partway through."""
    if not isinstance(plan, dict):
        raise ValueError("Invalid plan structure")

    days = plan.get("days")
    if isinstance(days, dict):
        days = [days]
    if not isinstance(days, list):
        if isinstance(plan.get("day"), dict):
            days = [plan["day"]]
        else:
            raise ValueError("The extracted plan is missing the required 'days' array.")

    normalized: list[dict] = []
    for day in days:
        if not isinstance(day, dict):
            raise ValueError("Invalid day structure")

        meals = day.get("meals") or []
        if isinstance(meals, dict):
            meals = [meals]
        if not isinstance(meals, list):
            raise ValueError("Invalid meal list for day")

        normalized.append({**day, "meals": meals})

    return normalized


def _next_free_date(conn, meal_date: str, meal_type: str) -> str:
    """If a meal is already scheduled for this date/meal-type, pushes forward a week at
    a time until a free slot is found, rather than creating a duplicate."""
    current = date.fromisoformat(meal_date)
    while meal_service.get_meal_by_date_type(conn, current.isoformat(), meal_type) is not None:
        current += timedelta(days=7)
    return current.isoformat()


def _save_plan(conn, plan: dict, source_filename: str) -> tuple[list[str], str]:
    """Resolves each day's meals to real dates, stores them in the DB, and returns
    (summary_lines, week_start_date)."""
    days = _normalize_days(plan)
    language = plan.get("language", "it")
    week_monday = next_monday()
    plan_id = meal_service.create_plan(conn, source_filename, language, week_monday)

    lines: list[str] = []
    for day_index, day in enumerate(days):
        day_label = day.get("day_label") or day.get("label") or f"Day {day_index + 1}"
        meal_date = resolve_day_date(day_label, day_index, week_monday)
        lines.append(f"📅 {day_label} ({meal_date})")

        for meal in day["meals"]:
            meal_type = meal.get("meal_type")
            dish_name = meal.get("dish_name", "(unknown dish)")
            if meal_type not in _VALID_MEAL_TYPES:
                lines.append(f"  • skipped '{dish_name}': invalid meal type '{meal_type}'")
                continue

            target_date = _next_free_date(conn, meal_date, meal_type)
            meal_id = meal_service.add_meal(
                conn,
                plan_id=plan_id,
                meal_date=target_date,
                meal_type=meal_type,
                dish_name=dish_name,
                description=meal.get("description"),
                ingredients=meal.get("ingredients"),
                instructions=meal.get("instructions"),
                recipe_link=meal.get("recipe_link"),
                calories=meal.get("calories"),
                macros=meal.get("macros"),
            )
            recipe_id, _ = recipe_service.get_or_create_recipe(conn, dish_name)
            if meal.get("recipe_link"):
                recipe_service.set_link_for_language(conn, recipe_id, language, meal["recipe_link"])
            meal_service.set_recipe_id(conn, meal_id, recipe_id)

            note = f" (moved to {target_date}, slot was taken)" if target_date != meal_date else ""
            lines.append(f"  • {meal_type}: {dish_name}{note}")

        lines.append("")

    return lines, week_monday


def _chunk_message(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    chunks: list[str] = []
    current = ""

    for line in text.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            if current:
                chunks.append(current)
                current = ""
            while len(line) > limit:
                chunks.append(line[:limit])
                line = line[limit:]
            current = line
        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks


@owner_only
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not ANTHROPIC_API_KEY:
        await update.message.reply_text(PDF_DISABLED_MESSAGE)
        return

    document = update.message.document if update.message else None
    if document is None:
        await update.message.reply_text("No PDF document was attached.")
        return

    await update.message.reply_text("PDF received, extracting your plan... this may take a moment.")

    temp_file: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fp:
            temp_file = Path(fp.name)
            file = await document.get_file()
            await file.download_to_drive(custom_path=str(temp_file))

        pdf_text = await asyncio.to_thread(pdf_extractor.extract_text, str(temp_file))
        if not pdf_text.strip():
            raise ValueError("Extracted PDF text is empty")

        plan = await asyncio.to_thread(claude_client.extract_plan, pdf_text)
        conn = context.bot_data["conn"]
        summary_lines, week_start = _save_plan(conn, plan, document.file_name or "upload.pdf")

        message = f"Plan saved for week starting {week_start}:\n\n" + "\n".join(summary_lines).strip()
        for chunk in _chunk_message(message):
            await update.message.reply_text(chunk)
    except ValueError as exc:
        logger.exception("Invalid PDF plan payload", exc_info=exc)
        await update.message.reply_text(INVALID_PLAN_MESSAGE)
    except Exception as exc:
        logger.exception("PDF upload failed", exc_info=exc)
        await update.message.reply_text(
            "An error occurred while processing the PDF. "
            "Please try again or use manual commands like /addrecipe."
        )
    finally:
        if temp_file is not None and temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                logger.exception("Could not delete temporary PDF file")


