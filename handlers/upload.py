"""PDF upload: extracts text locally, then queues an extract_plan AI request instead
of calling Claude directly (see ai_queue/SPEC.md). handlers/ai_consumer.py applies the
result via save_extracted_plan() once the response comes back."""

import asyncio
import logging
import tempfile
from datetime import date, timedelta
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

import ai_queue_service
import meal_service
import pdf_extractor
import recipe_service
from access_control import owner_only
from date_utils import next_monday, resolve_day_date

_VALID_MEAL_TYPES = ("breakfast", "lunch", "dinner")

logger = logging.getLogger(__name__)

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
        elif plan.get("dish_name"):
            # Single-recipe extractions sometimes put the meal fields directly on the
            # top-level plan instead of nesting them under days/meals.
            days = [{"day_label": "Day 1", "meals": [plan]}]
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


def save_extracted_plan(conn, plan: dict, source_filename: str) -> tuple[list[str], str]:
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


@owner_only
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    document = update.message.document if update.message else None
    if document is None:
        await update.message.reply_text("No PDF document was attached.")
        return

    temp_file: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fp:
            temp_file = Path(fp.name)
            file = await document.get_file()
            await file.download_to_drive(custom_path=str(temp_file))

        pdf_text = await asyncio.to_thread(pdf_extractor.extract_text, str(temp_file))
        if not pdf_text.strip():
            raise ValueError("Extracted PDF text is empty")
    except ValueError:
        logger.exception("Empty PDF text extraction")
        await update.message.reply_text(INVALID_PLAN_MESSAGE)
        return
    except Exception:
        logger.exception("PDF read failed")
        await update.message.reply_text(
            "An error occurred while reading the PDF. "
            "Please try again or use manual commands like /addrecipe."
        )
        return
    finally:
        if temp_file is not None and temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                logger.exception("Could not delete temporary PDF file")

    ai_queue_service.enqueue(
        "extract_plan",
        chat_id=update.effective_chat.id,
        payload={"pdf_text": pdf_text, "source_filename": document.file_name or "upload.pdf"},
    )
    await update.message.reply_text(
        "PDF received and queued for extraction - I'll message you with the parsed plan "
        "once it comes back (usually within a few minutes)."
    )


