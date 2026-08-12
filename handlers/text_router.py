"""Routes free-text messages to whichever pending flow is active: link editing,
manual recipe add, add-link, rename, replace, URL import, or logging an eaten meal."""

from telegram import Update
from telegram.ext import ContextTypes

from handlers import day_off, recipe_library, replace_recipe, reschedule, tracking, upload, url_import


async def route_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await day_off.try_handle_dayoff_step(update, context):
        return
    if await recipe_library.try_handle_add_link(update, context):
        return
    if await recipe_library.try_handle_recipe_details(update, context):
        return
    if await recipe_library.try_handle_edit_recipe_id(update, context):
        return
    if await recipe_library.try_handle_edit_recipe_name_text(update, context):
        return
    if await recipe_library.try_handle_edit_recipe_link_text(update, context):
        return
    if await recipe_library.try_handle_edit_recipe_nutrition_text(update, context):
        return
    if await recipe_library.try_handle_edit_recipe_prep_time_text(update, context):
        return
    if await recipe_library.try_handle_edit_recipe_cook_time_text(update, context):
        return
    if await recipe_library.try_handle_edit_recipe_oven_temp_text(update, context):
        return
    if await recipe_library.try_handle_edit_recipe_notes_text(update, context):
        return
    if await recipe_library.try_handle_new_recipe_step(update, context):
        return
    if await replace_recipe.try_handle_replace_step(update, context):
        return
    if await reschedule.try_handle_reschedule_step(update, context):
        return
    if await url_import.try_handle_url_import(update, context):
        return
    await tracking.handle_eaten_text(update, context)
