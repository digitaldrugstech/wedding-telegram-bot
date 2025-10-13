"""Bot initialization and setup."""

import html
import json
import traceback

import structlog
from telegram import Update
from telegram.ext import Application, ContextTypes

from app.config import config
from app.handlers.admin import register_admin_handlers
from app.handlers.business import register_business_handlers
from app.handlers.casino import register_casino_handlers
from app.handlers.children import register_children_handlers
from app.handlers.house import register_house_handlers
from app.handlers.marriage import register_marriage_handlers
from app.handlers.menu import register_menu_handlers
from app.handlers.start import register_start_handlers
from app.handlers.utils import register_utils_handlers
from app.handlers.work import register_work_handlers

logger = structlog.get_logger()


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors and notify admin."""
    logger.error("Exception while handling an update", exc_info=context.error)

    # Get traceback
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    # Build error message for admin
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f"🔴 <b>Exception occurred</b>\n\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False)[:500])}</pre>\n\n"
        f"<pre>error = {html.escape(str(context.error)[:500])}</pre>\n\n"
        f"<pre>{html.escape(tb_string[-1000:])}</pre>"
    )

    # Send to admin
    try:
        await context.bot.send_message(chat_id=config.admin_user_id, text=message, parse_mode="HTML")
    except Exception as e:
        logger.error("Failed to send error message to admin", error=str(e))

    # Send user-friendly message
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ <b>Ошибка</b>\n\nПроизошла ошибка при обработке команды\n\nПопробуй ещё раз или обратись к @haffk",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error("Failed to send error message to user", error=str(e))


def create_bot() -> Application:
    """Create and configure bot application."""
    logger.info("Initializing bot", bot_token_set=bool(config.telegram_bot_token))

    # Create application
    application = Application.builder().token(config.telegram_bot_token).build()

    # Register handlers
    register_start_handlers(application)
    register_utils_handlers(application)
    register_menu_handlers(application)
    register_work_handlers(application)
    register_marriage_handlers(application)
    register_children_handlers(application)
    register_house_handlers(application)
    register_business_handlers(application)
    register_casino_handlers(application)
    register_admin_handlers(application)

    # Register error handler
    application.add_error_handler(error_handler)

    logger.info("Bot handlers registered")

    return application


async def post_init(application: Application):
    """Post-initialization hook."""
    logger.info("Bot initialized successfully")


async def post_shutdown(application: Application):
    """Post-shutdown hook."""
    logger.info("Bot shutdown complete")
