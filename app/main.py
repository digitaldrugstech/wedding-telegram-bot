"""Main entry point for the Wedding Telegram Bot."""

import asyncio
import logging
import sys

import structlog
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from app.bot import create_bot, post_init, post_shutdown
from app.config import config
from app.database.connection import init_db

# Configure structlog
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

# Setup standard logging
logging.basicConfig(
    format="%(message)s",
    stream=sys.stdout,
    level=getattr(logging, config.log_level.upper(), logging.INFO),
)

logger = structlog.get_logger()


async def main():
    """Main function."""
    try:
        # Validate configuration
        config.validate()
        logger.info("Configuration validated")

        # Initialize database
        logger.info("Initializing database")
        init_db()
        logger.info("Database initialized")

        # Create bot
        logger.info("Creating bot application")
        application = create_bot()

        # Initialize bot
        await post_init(application)

        # Start bot
        logger.info("Starting bot")
        await application.initialize()
        await application.start()
        await application.updater.start_polling(allowed_updates=["message", "callback_query"])
        logger.info("Bot started successfully")

        # Keep running
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down")
    except Exception as e:
        logger.error("Fatal error", error=str(e), exc_info=True)
        sys.exit(1)
    finally:
        if "application" in locals():
            logger.info("Stopping bot")
            await application.updater.stop()
            await application.stop()
            await application.shutdown()
            await post_shutdown(application)


if __name__ == "__main__":
    asyncio.run(main())
