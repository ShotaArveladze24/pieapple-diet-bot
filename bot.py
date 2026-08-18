"""Entry point PieappleDietBot: registra gli handler e avvia il polling."""

import asyncio
import logging

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import ALLOWED_TELEGRAM_IDS, OWNER_TELEGRAM_ID, TELEGRAM_BOT_TOKEN
from db import get_connection, init_db
from handlers import (
    ai_consumer,
    clear,
    day_off,
    ingredients_it,
    meal_photo,
    nutrition,
    onboarding,
    plan_query,
    recipe_detail,
    recipe_library,
    remove,
    replace_recipe,
    reschedule,
    substitution,
    text_router,
    tracking,
    upload,
)

AI_QUEUE_POLL_INTERVAL_SECONDS = 60

logger = logging.getLogger(__name__)

owner_filter = filters.User(user_id=list(ALLOWED_TELEGRAM_IDS)) if ALLOWED_TELEGRAM_IDS else filters.ALL


async def on_startup(application: Application) -> None:
    """Confirms the first connection to Telegram succeeded."""
    me = await application.bot.get_me()
    logger.info("Connected to Telegram as @%s - PieappleDietBot is polling for updates.", me.username)


async def poll_ai_queue(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Consumes any AI queue responses written by the external consumer since the last
    run (see ai_queue/SPEC.md). Runs every AI_QUEUE_POLL_INTERVAL_SECONDS."""
    try:
        await ai_consumer.poll(context.application)
    except Exception:
        logger.exception("AI queue poll failed")


def build_application() -> Application:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(on_startup).build()

    conn = get_connection()
    init_db(conn)
    application.bot_data["conn"] = conn

    application.job_queue.run_repeating(
        poll_ai_queue, interval=AI_QUEUE_POLL_INTERVAL_SECONDS, first=15, name="ai_queue_poll"
    )

    application.add_handler(CommandHandler("start", onboarding.start))
    application.add_handler(CommandHandler("help", onboarding.help_command, filters=owner_filter))
    application.add_handler(CommandHandler("today", plan_query.today, filters=owner_filter))
    application.add_handler(CommandHandler("tomorrow", plan_query.tomorrow, filters=owner_filter))
    application.add_handler(CommandHandler("week", plan_query.week, filters=owner_filter))
    application.add_handler(CommandHandler("agenda", plan_query.agenda, filters=owner_filter))
    application.add_handler(CommandHandler("report", tracking.report, filters=owner_filter))
    application.add_handler(CommandHandler("recipes", recipe_library.list_recipes, filters=owner_filter))
    application.add_handler(
        CommandHandler("recipe_details", recipe_library.recipe_details, filters=owner_filter)
    )
    application.add_handler(CommandHandler("addrecipe", recipe_library.add_recipe_start, filters=owner_filter))
    application.add_handler(
        CommandHandler("clean_titles", recipe_library.clean_titles, filters=owner_filter)
    )
    application.add_handler(CommandHandler("add_link", recipe_library.add_link_start, filters=owner_filter))
    application.add_handler(
        CommandHandler("edit_recipe", recipe_library.edit_recipe_start, filters=owner_filter)
    )
    application.add_handler(CommandHandler("scan", recipe_library.scan_recipe, filters=owner_filter))
    application.add_handler(CommandHandler("scan_week", recipe_library.scan_week, filters=owner_filter))
    application.add_handler(CommandHandler("scan_all", recipe_library.scan_all, filters=owner_filter))
    application.add_handler(
        CommandHandler("scan_ingredienti_IT", ingredients_it.scan_ingredienti_it, filters=owner_filter)
    )
    application.add_handler(
        CommandHandler("all_ingredients_IT", ingredients_it.all_ingredients_it, filters=owner_filter)
    )
    application.add_handler(CommandHandler("language", onboarding.language_start, filters=owner_filter))
    application.add_handler(
        CommandHandler("replace_recipe", replace_recipe.replace_recipe_start, filters=owner_filter)
    )
    application.add_handler(
        CommandHandler("reschedule", reschedule.reschedule_start, filters=owner_filter)
    )
    application.add_handler(CommandHandler("remove", remove.remove_start, filters=owner_filter))
    application.add_handler(CommandHandler("dayoff", day_off.dayoff_start, filters=owner_filter))
    application.add_handler(CommandHandler("dayon", day_off.dayon_start, filters=owner_filter))
    application.add_handler(CommandHandler("clear_past", clear.clear_past_start, filters=owner_filter))
    application.add_handler(CommandHandler("clear_future", clear.clear_future_start, filters=owner_filter))
    application.add_handler(
        CommandHandler("upload_photo", meal_photo.upload_photo_start, filters=owner_filter)
    )

    application.add_handler(
        MessageHandler(filters.Document.PDF & owner_filter, upload.handle_pdf)
    )
    application.add_handler(MessageHandler(filters.PHOTO & owner_filter, meal_photo.handle_photo))
    application.add_handler(MessageHandler(filters.LOCATION & owner_filter, meal_photo.handle_location))

    application.add_handler(CallbackQueryHandler(recipe_detail.handle_recipe, pattern=r"^recipe_\d+$"))
    application.add_handler(
        CallbackQueryHandler(plan_query.handle_agenda_slot, pattern=r"^agendaslot_\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(plan_query.handle_agenda_empty, pattern=r"^agendaempty$")
    )
    application.add_handler(
        CallbackQueryHandler(substitution.handle_substitute_request, pattern=r"^substitute_\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(substitution.handle_substitute_confirm, pattern=r"^subconfirm_\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(substitution.handle_substitute_cancel, pattern=r"^subcancel_\d+$")
    )
    application.add_handler(CallbackQueryHandler(nutrition.handle_nutrition, pattern=r"^nutrition_\d+$"))
    application.add_handler(
        CallbackQueryHandler(recipe_library.handle_edit_recipe_scan, pattern=r"^erscan_\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(recipe_library.handle_edit_recipe_name, pattern=r"^ername_(it|es|en)_\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(recipe_library.handle_edit_recipe_link, pattern=r"^erlink_(it|es|en)_\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(recipe_library.handle_edit_recipe_nutrition_start, pattern=r"^ernutrition_\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(recipe_library.handle_edit_recipe_difficulty_start, pattern=r"^erdiff_\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(recipe_library.handle_edit_recipe_difficulty_set, pattern=r"^erdiffset_[0-4]_\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(recipe_library.handle_edit_recipe_prep_time_start, pattern=r"^erprep_\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(recipe_library.handle_edit_recipe_cook_time_start, pattern=r"^ercook_\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(recipe_library.handle_edit_recipe_oven_temp_start, pattern=r"^eroven_\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(recipe_library.handle_edit_recipe_notes_start, pattern=r"^ernotes_\d+$")
    )
    application.add_handler(CallbackQueryHandler(clear.handle_clear_confirm, pattern=r"^clear_confirm$"))
    application.add_handler(CallbackQueryHandler(clear.handle_clear_cancel, pattern=r"^clear_cancel$"))
    application.add_handler(
        CallbackQueryHandler(meal_photo.handle_skip_location, pattern=r"^mealphotoskip_\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(day_off.handle_dayoff_pick, pattern=r"^dayoffset_\d{4}-\d{2}-\d{2}$")
    )
    application.add_handler(
        CallbackQueryHandler(day_off.handle_dayon_pick, pattern=r"^dayonunset_\d{4}-\d{2}-\d{2}$")
    )
    application.add_handler(
        CallbackQueryHandler(remove.handle_remove_confirm, pattern=r"^removeconfirm_\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(remove.handle_remove_cancel, pattern=r"^removecancel_\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(replace_recipe.handle_replace_ask, pattern=r"^replaceask_\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(replace_recipe.handle_replace_pick, pattern=r"^replacepick_\d+_\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(replace_recipe.handle_replace_cancel, pattern=r"^replacecancel_\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(onboarding.handle_set_language, pattern=r"^setlang_(en|it|es)$")
    )
    application.add_handler(
        CallbackQueryHandler(tracking.handle_adherence_response, pattern=r"^adherence_(yes|no)_\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(tracking.handle_adherence_rating, pattern=r"^adherate_(skip|[1-9]|10)_\d+$")
    )

    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & owner_filter, text_router.route_free_text)
    )

    application.add_error_handler(error_handler)

    return application


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled error while processing update", exc_info=context.error)
    if OWNER_TELEGRAM_ID is None:
        return
    try:
        await context.bot.send_message(
            chat_id=OWNER_TELEGRAM_ID, text=f"An error occurred: {context.error}"
        )
    except Exception:
        logger.exception("Could not notify the user about the error")


def main() -> None:
    # Root level is WARNING so third-party libraries (httpx, telegram.ext, apscheduler, ...)
    # stay quiet during normal operation - no per-request/poll noise. Our own logger is
    # bumped back up to INFO so it can still announce the first successful connection;
    # errors and fatals from any logger always pass through regardless of level.
    logging.basicConfig(
        level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logger.setLevel(logging.INFO)
    # Python 3.14 removed asyncio.get_event_loop()'s implicit loop creation, which
    # python-telegram-bot 21.x's run_polling() still relies on. Setting a loop explicitly
    # keeps that call working without needing to patch the library.
    asyncio.set_event_loop(asyncio.new_event_loop())
    application = build_application()
    application.run_polling()


if __name__ == "__main__":
    main()
