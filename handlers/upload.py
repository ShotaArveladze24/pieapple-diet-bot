"""PDF upload is disabled unless AI extraction is configured."""

import logging
import tempfile
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

import claude_client
import pdf_extractor
from access_control import owner_only
from config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

PDF_DISABLED_MESSAGE = (
    "PDF upload is disabled because AI extraction has been removed. "
    "Use manual commands like /addrecipe, /today, /tomorrow, and /week."
)

INVALID_PLAN_MESSAGE = (
    "The PDF was read, but the extracted plan was incomplete or invalid. "
    "Please try a different file or use manual commands like /addrecipe."
)


def _normalize_days(plan: dict) -> list[dict]:
    if not isinstance(plan, dict):
        raise ValueError("Invalid plan structure")

    days = plan.get("days")
    if isinstance(days, dict):
        days = [days]
    if isinstance(days, list):
        return days

    if isinstance(plan.get("day"), dict):
        return [plan["day"]]

    raise ValueError("The extracted plan is missing the required 'days' array.")


def _format_summary(plan: dict) -> str:
    days = _normalize_days(plan)
    lines: list[str] = []

    for day_index, day in enumerate(days, start=1):
        day_label = day.get("day_label") or day.get("label") or f"Day {day_index}"
        lines.append(f"{day_label}")

        meals = day.get("meals") or []
        if isinstance(meals, dict):
            meals = [meals]
        if not isinstance(meals, list):
            raise ValueError("Invalid meal list for day")

        for meal in meals:
            meal_type = meal.get("meal_type", "meal")
            dish_name = meal.get("dish_name", "(unknown dish)")
            lines.append(f"  • {meal_type}: {dish_name}")

        lines.append("")

    return "\n".join(lines).strip()


@owner_only
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not ANTHROPIC_API_KEY:
        await update.message.reply_text(PDF_DISABLED_MESSAGE)
        return

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

        pdf_text = pdf_extractor.extract_text(str(temp_file))
        if not pdf_text.strip():
            raise ValueError("Extracted PDF text is empty")

        plan = claude_client.extract_plan(pdf_text)
        summary = _format_summary(plan)
        await update.message.reply_text(
            "PDF extracted successfully. Here is the parsed plan summary:\n\n" + summary
        )
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


