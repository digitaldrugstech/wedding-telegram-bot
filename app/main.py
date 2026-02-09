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
from app.tasks.scheduler import start_scheduler, stop_scheduler  # noqa: E402

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

        # Start background tasks scheduler
        logger.info("Starting background tasks scheduler")
        start_scheduler(application)

        # Start bot
        logger.info("Starting bot")
        await application.initialize()
        await application.start()
        await application.updater.start_polling(
            allowed_updates=["message", "callback_query"], drop_pending_updates=True
        )
        logger.info("Bot started successfully")

        # Send update announcement to production chat
        try:
            import os

            announce_chat_id = int(os.getenv("ANNOUNCE_CHAT_ID", "-1003086018945"))

            update_text = (
                f"\U0001f389 <b>Wedding Bot v{__version__}</b>\n\n"
                "\U0001f0cf <b>\u041d\u043e\u0432\u044b\u0435 \u0438\u0433\u0440\u044b:</b>\n"
                "\u2022 /blackjack [\u0441\u0442\u0430\u0432\u043a\u0430] \u2014 \u0411\u043b\u044d\u043a\u0434\u0436\u0435\u043a (x2.5 \u0437\u0430 21)\n"
                "\u2022 /bj [\u0441\u0442\u0430\u0432\u043a\u0430] \u2014 \u043a\u043e\u0440\u043e\u0442\u043a\u0430\u044f \u043a\u043e\u043c\u0430\u043d\u0434\u0430\n"
                "\u2022 /scratch [\u0441\u0442\u0430\u0432\u043a\u0430] \u2014 \u0421\u043a\u0440\u0435\u0442\u0447-\u043a\u0430\u0440\u0442\u0430 (x5 \u0437\u0430 3 \u0430\u043b\u043c\u0430\u0437\u0430)\n\n"
                "\u2696\ufe0f <b>\u0411\u0430\u043b\u0430\u043d\u0441:</b>\n"
                "\u2022 \u0411\u0438\u0437\u043d\u0435\u0441\u044b: \u043e\u043a\u0443\u043f\u0430\u0435\u043c\u043e\u0441\u0442\u044c 6-8 \u043d\u0435\u0434\u0435\u043b\u044c\n"
                "\u2022 \u041a\u043e\u0440\u043c\u043b\u0435\u043d\u0438\u0435 \u0434\u0435\u0442\u0435\u0439: 200\U0001f48e / 3 \u0434\u043d\u044f\n"
                "\u2022 \u041a\u043e\u043b\u0435\u0441\u043e \u0444\u043e\u0440\u0442\u0443\u043d\u044b: \u043f\u0435\u0440\u0435\u0431\u0430\u043b\u0430\u043d\u0441\n\n"
                "\U0001f41b <b>\u0418\u0441\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043e:</b>\n"
                "\u2022 HTML-\u0438\u043d\u044a\u0435\u043a\u0446\u0438\u044f \u0432 \u0438\u043c\u0435\u043d\u0430\u0445 \u0434\u0435\u0442\u0435\u0439\n"
                "\u2022 \u0421\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430 \u0430\u0434\u043c\u0438\u043d\u043a\u0438\n"
                "\u2022 \u041e\u043f\u0442\u0438\u043c\u0438\u0437\u0430\u0446\u0438\u044f \u043a\u0432\u0435\u0441\u0442\u043e\u0432\n\n"
                "\U0001f4ac \u041d\u0430\u0448\u0451\u043b \u0431\u0430\u0433? \u041f\u0438\u0448\u0438 /bug_report"
            )

            try:
                msg = await application.bot.send_message(chat_id=announce_chat_id, text=update_text, parse_mode="HTML")
                # Pin the announcement
                try:
                    await application.bot.pin_chat_message(
                        chat_id=announce_chat_id, message_id=msg.message_id, disable_notification=True
                    )
                    logger.info("Update announcement pinned", chat_id=announce_chat_id)
                except Exception as pin_err:
                    logger.warning("Could not pin announcement", error=str(pin_err))
                logger.info("Update announcement sent", chat_id=announce_chat_id)
            except Exception as send_err:
                logger.debug("Could not send announcement", chat_id=announce_chat_id, error=str(send_err))

            # Also send to debug chat
            try:
                await application.bot.send_message(
                    chat_id=DEBUG_CHAT_ID,
                    text=f"\U0001f916 Bot started v{__version__}",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        except Exception as e:
            logger.debug("Announcement routine failed", error=str(e))

        # Keep running
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down")
    except Exception as e:
        logger.error("Fatal error", error=str(e), exc_info=True)
        sys.exit(1)
    finally:
        # Stop scheduler
        try:
            stop_scheduler()
        except Exception as e:
            logger.error("Error stopping scheduler", error=str(e))

        if "application" in locals():
            logger.info("Stopping bot")
            await application.updater.stop()
            await application.stop()
            await application.shutdown()
            await post_shutdown(application)


if __name__ == "__main__":
    asyncio.run(main())
