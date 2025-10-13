"""Background tasks scheduler using APScheduler."""

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from telegram.ext import Application

from app.database.connection import get_db
from app.services.children_service import ChildrenService

logger = structlog.get_logger()

# Global scheduler instance
scheduler = None


async def check_starving_children_task(application: Application):
    """Background task to check and kill starving children."""
    logger.info("Running starving children check")

    try:
        with get_db() as db:
            dead_children_info = ChildrenService.check_and_kill_starving_children(db)

            if dead_children_info:
                logger.warning("Children died from starvation", count=len(dead_children_info))

                # Send notifications to parents
                for child, parent1_id, parent2_id in dead_children_info:
                    child_info = ChildrenService.get_child_info(child)
                    message = (
                        f"💀 <b>Смерть ребёнка</b>\n\n"
                        f"{child_info['age_emoji']} {child_info['name']} {child_info['gender_emoji']}\n"
                        f"умер от голода\n\n"
                        f"Не забывай кормить детей каждые 3 дня!"
                    )

                    # Notify parent1
                    try:
                        await application.bot.send_message(chat_id=parent1_id, text=message, parse_mode="HTML")
                        logger.info("Death notification sent", parent_id=parent1_id, child_id=child.id)
                    except Exception as e:
                        logger.warning("Failed to notify parent about child death", parent_id=parent1_id, error=str(e))

                    # Notify parent2
                    try:
                        await application.bot.send_message(chat_id=parent2_id, text=message, parse_mode="HTML")
                        logger.info("Death notification sent", parent_id=parent2_id, child_id=child.id)
                    except Exception as e:
                        logger.warning("Failed to notify parent about child death", parent_id=parent2_id, error=str(e))

        logger.info("Starving children check complete", starved=len(dead_children_info) if dead_children_info else 0)
    except Exception as e:
        logger.error("Error in starving children check", error=str(e), exc_info=True)


def start_scheduler(application: Application):
    """Start the background tasks scheduler."""
    global scheduler

    if scheduler is not None:
        logger.warning("Scheduler already started")
        return

    logger.info("Starting background tasks scheduler")

    scheduler = AsyncIOScheduler()

    # Check starving children every hour
    scheduler.add_job(
        check_starving_children_task,
        trigger=IntervalTrigger(hours=1),
        args=[application],
        id="check_starving_children",
        name="Check starving children",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started successfully")


def stop_scheduler():
    """Stop the background tasks scheduler."""
    global scheduler

    if scheduler is None:
        logger.warning("Scheduler not started")
        return

    logger.info("Stopping scheduler")
    scheduler.shutdown()
    scheduler = None
    logger.info("Scheduler stopped")
