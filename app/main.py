"""Main entry point for the Wedding Telegram Bot."""

import asyncio
import logging
import sys

import structlog
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from app.__version__ import __version__  # noqa: E402
from app.bot import create_bot, post_init, post_shutdown  # noqa: E402
from app.config import config  # noqa: E402
from app.constants import DEBUG_CHAT_ID  # noqa: E402
from app.database.connection import init_db  # noqa: E402

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
        await application.updater.start_polling(
            allowed_updates=["message", "callback_query"], drop_pending_updates=True
        )
        logger.info("Bot started successfully")

        # Send debug message to chat with changelog (optional, may fail if no access)
        try:
            # Read changelog for current version
            changelog_text = ""
            try:
                import os

                changelog_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "CHANGELOG.md")
                with open(changelog_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    in_current_version = False
                    for line in lines:
                        if line.startswith(f"## [{__version__}]"):
                            in_current_version = True
                            continue
                        elif in_current_version and line.startswith("## ["):
                            break
                        elif in_current_version:
                            changelog_text += line
            except Exception as e:
                logger.warning("Failed to read changelog", error=str(e))
                changelog_text = ""

            message = f"🤖 Wedding Bot started\n📦 Version: {__version__}"
            if changelog_text.strip():
                message += f"\n\n{changelog_text.strip()}"

            try:
                await application.bot.send_message(chat_id=DEBUG_CHAT_ID, text=message)
                logger.info("Debug message sent to chat", chat_id=DEBUG_CHAT_ID)
            except Exception as send_error:
                # Bot may not have access to debug chat (e.g., in production)
                logger.debug(
                    "Could not send debug message (bot may not have access)",
                    chat_id=DEBUG_CHAT_ID,
                    error=str(send_error),
                )
        except Exception as e:
            logger.debug("Debug message routine failed", error=str(e))

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
