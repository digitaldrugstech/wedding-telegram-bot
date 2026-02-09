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
                "\U0001f381 <b>\u041d\u043e\u0432\u043e\u0435:</b>\n"
                "\u2022 /daily \u2014 \u0435\u0436\u0435\u0434\u043d\u0435\u0432\u043d\u044b\u0439 \u0431\u043e\u043d\u0443\u0441 (\u0441\u0435\u0440\u0438\u044f \u0434\u043d\u0435\u0439 = \u0431\u043e\u043b\u044c\u0448\u0435 \u043d\u0430\u0433\u0440\u0430\u0434\u0430)\n"
                "\u2022 /lottery \u2014 \u043b\u043e\u0442\u0435\u0440\u0435\u044f \u0441 \u0434\u0436\u0435\u043a\u043f\u043e\u0442\u043e\u043c (\u0440\u043e\u0437\u044b\u0433\u0440\u044b\u0448 \u043a\u0430\u0436\u0434\u0443\u044e \u0441\u0443\u0431\u0431\u043e\u0442\u0443)\n"
                "\u2022 /friendgift \u2014 \u043f\u043e\u0434\u0430\u0440\u043e\u043a \u0434\u0440\u0443\u0433\u0443 (\u0431\u0435\u0437 \u043a\u043e\u043c\u0438\u0441\u0441\u0438\u0438)\n\n"
                "\U0001f41b <b>\u0418\u0441\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043e:</b>\n"
                "\u2022 \u041f\u0438\u0442\u043e\u043c\u0446\u044b \u043a\u043e\u0440\u0440\u0435\u043a\u0442\u043d\u043e \u043f\u043e\u043a\u0430\u0437\u044b\u0432\u0430\u044e\u0442 \u0441\u0442\u0430\u0442\u044b\n"
                "\u2022 18 \u043f\u0440\u043e\u0444\u0435\u0441\u0441\u0438\u0439 \u0432 \u043c\u0435\u043d\u044e\n"
                "\u2022 \u041a\u043e\u0440\u0440\u0435\u043a\u0442\u043d\u044b\u0435 \u043c\u043d\u043e\u0436\u0438\u0442\u0435\u043b\u0438 \u043a\u0430\u0437\u0438\u043d\u043e\n\n"
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
