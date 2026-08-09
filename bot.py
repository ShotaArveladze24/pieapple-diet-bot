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
    clear,
    day_off,
    nutrition,
    onboarding,
    plan_query,
    recipe_detail,
    recipe_library,
    replace_recipe,
    substitution,
    text_router,
    tracking,
    upload,
)

logger = logging.getLogger(__name__)

owner_filter = filters.User(user_id=list(ALLOWED_TELEGRAM_IDS)) if ALLOWED_TELEGRAM_IDS else filters.ALL


def build_application() -> Application:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conn = get_connection()
    init_db(conn)
    application.bot_data["conn"] = conn

    application.add_handler(CommandHandler("start", onboarding.start))
    application.add_handler(CommandHandler("help", onboarding.help_command, filters=owner_filter))
    application.add_handler(CommandHandler("today", plan_query.today, filters=owner_filter))
    application.add_handler(CommandHandler("tomorrow", plan_query.tomorrow, filters=owner_filter))
    application.add_handler(CommandHandler("week", plan_query.week, filters=owner_filter))
    application.add_handler(CommandHandler("report", tracking.report, filters=owner_filter))
    application.add_handler(CommandHandler("recipes", recipe_library.list_recipes, filters=owner_filter))
    application.add_handler(
        CommandHandler("recipe_details", recipe_library.recipe_details, filters=owner_filter)
    )
    application.add_handler(CommandHandler("addrecipe", recipe_library.add_recipe_start, filters=owner_filter))
    application.add_handler(CommandHandler("add_link", recipe_library.add_link_start, filters=owner_filter))
    application.add_handler(
        CommandHandler("edit_recipe_name", recipe_library.edit_recipe_name_start, filters=owner_filter)
    )
    application.add_handler(CommandHandler("language", onboarding.language_start, filters=owner_filter))
    application.add_handler(
        CommandHandler("replace_recipe", replace_recipe.replace_recipe_start, filters=owner_filter)
    )
    application.add_handler(CommandHandler("dayoff", day_off.dayoff_start, filters=owner_filter))
    application.add_handler(CommandHandler("dayon", day_off.dayon_start, filters=owner_filter))
    application.add_handler(CommandHandler("clear_past", clear.clear_past_start, filters=owner_filter))
    application.add_handler(CommandHandler("clear_future", clear.clear_future_start, filters=owner_filter))

    application.add_handler(
        MessageHandler(filters.Document.PDF & owner_filter, upload.handle_pdf)
    )

    application.add_handler(CallbackQueryHandler(recipe_detail.handle_recipe, pattern=r"^recipe_\d+$"))
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
        CallbackQueryHandler(recipe_library.handle_edit_link_request, pattern=r"^editlink_\d+$")
    )
    application.add_handler(CallbackQueryHandler(clear.handle_clear_confirm, pattern=r"^clear_confirm$"))
    application.add_handler(CallbackQueryHandler(clear.handle_clear_cancel, pattern=r"^clear_cancel$"))
    application.add_handler(
        CallbackQueryHandler(onboarding.handle_set_language, pattern=r"^setlang_(en|it|es)$")
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
    # Python 3.14 removed asyncio.get_event_loop()'s implicit loop creation, which
    # python-telegram-bot 21.x's run_polling() still relies on. Setting a loop explicitly
    # keeps that call working without needing to patch the library.
    asyncio.set_event_loop(asyncio.new_event_loop())
    application = build_application()
    application.run_polling()


if __name__ == "__main__":
    main()
