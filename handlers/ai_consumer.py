"""Consumes AI queue responses written by the external Claude Code consumer (see
ai_queue/SPEC.md and deploy/pieapple-ai-consumer.timer) and applies them: extract_plan
results are saved the same way upload.py used to save a direct Claude response;
scan_recipe results are applied via recipe_library.apply_scan_result(). Runs on a
job_queue timer in bot.py, every 5 minutes - the same cadence the consumer itself polls
at, so a round trip normally completes within about 10 minutes."""

import logging

from telegram.ext import Application

import ai_queue_service
from handlers import recipe_library, upload
from text_utils import chunk_message

logger = logging.getLogger(__name__)


async def _handle_extract_plan(app: Application, request: dict, response: dict) -> None:
    chat_id = request["chat_id"]
    if response.get("error"):
        await app.bot.send_message(chat_id, f"PDF extraction failed: {response['error']}")
        return

    conn = app.bot_data["conn"]
    try:
        summary_lines, week_start = upload.save_extracted_plan(
            conn, response["result"], request["payload"]["source_filename"]
        )
    except ValueError:
        logger.exception("Invalid PDF plan payload from AI queue response %s", request["id"])
        await app.bot.send_message(chat_id, upload.INVALID_PLAN_MESSAGE)
        return
    except Exception:
        logger.exception("Failed to save extracted plan from AI queue response %s", request["id"])
        await app.bot.send_message(chat_id, "An error occurred while saving the extracted plan.")
        return

    message = f"Plan saved for week starting {week_start}:\n\n" + "\n".join(summary_lines).strip()
    for chunk in chunk_message(message):
        await app.bot.send_message(chat_id, chunk)


async def _handle_scan_recipe(app: Application, request: dict, response: dict) -> None:
    chat_id = request["chat_id"]
    recipe_id = request["payload"]["recipe_id"]
    name = request["payload"]["name"]

    if response.get("error"):
        await app.bot.send_message(chat_id, f"Scan failed for '{name}' (#{recipe_id}): {response['error']}")
        return

    conn = app.bot_data["conn"]
    summary = recipe_library.apply_scan_result(conn, recipe_id, response.get("result") or {})
    parts = []
    if summary["links"]:
        parts.append(f"{summary['links']} link(s)")
    if summary["names"]:
        parts.append(f"{summary['names']} translation(s)")
    if summary["nutrition"]:
        parts.append("nutrition")
    detail = ", ".join(parts) if parts else "nothing new"
    await app.bot.send_message(chat_id, f"Scan finished for '{name}' (#{recipe_id}): {detail} added.")


async def poll(app: Application) -> None:
    """Consumes every AI queue response currently waiting. Called from a job_queue
    timer in bot.py."""
    await ai_queue_service.poll_and_dispatch(
        {
            "extract_plan": lambda request, response: _handle_extract_plan(app, request, response),
            "scan_recipe": lambda request, response: _handle_scan_recipe(app, request, response),
        }
    )
