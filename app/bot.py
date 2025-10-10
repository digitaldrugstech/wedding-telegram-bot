"""Bot initialization and setup."""

import structlog
from telegram.ext import Application

from app.config import config
from app.handlers.start import register_start_handlers
from app.handlers.utils import register_utils_handlers

logger = structlog.get_logger()


def create_bot() -> Application:
    """Create and configure bot application."""
    logger.info("Initializing bot", bot_token_set=bool(config.telegram_bot_token))

    # Create application
    application = Application.builder().token(config.telegram_bot_token).build()

    # Register handlers
    register_start_handlers(application)
    register_utils_handlers(application)

    logger.info("Bot handlers registered")

    return application


async def post_init(application: Application):
    """Post-initialization hook."""
    logger.info("Bot initialized successfully")


async def post_shutdown(application: Application):
    """Post-shutdown hook."""
    logger.info("Bot shutdown complete")
