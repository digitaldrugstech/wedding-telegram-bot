"""Background tasks scheduler using APScheduler."""

from datetime import datetime

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from telegram.ext import Application

from app.config import config
from app.database.connection import get_db
from app.services.business_service import BusinessService
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


async def process_working_children_task(application: Application):
    """Process automatic work for all working children (every 4 hours)."""
    logger.info("Running working children payouts")

    try:
        with get_db() as db:
            results = ChildrenService.process_all_working_children(db)

            if results:
                logger.info("Working children processed", count=len(results))

                # Notify parents about earnings
                from app.utils.formatters import format_diamonds

                # Group by parent
                parent_earnings = {}
                for child_id, parent_id, earnings in results:
                    if parent_id not in parent_earnings:
                        parent_earnings[parent_id] = 0
                    parent_earnings[parent_id] += earnings

                # Send notifications
                for parent_id, total_earnings in parent_earnings.items():
                    message = f"💼 <b>Дети заработали</b>\n\n" f"Твои дети принесли: {format_diamonds(total_earnings)}"

                    try:
                        await application.bot.send_message(chat_id=parent_id, text=message, parse_mode="HTML")
                        logger.info("Child work notification sent", parent_id=parent_id, earnings=total_earnings)
                    except Exception as e:
                        logger.warning(
                            "Failed to notify parent about child earnings", parent_id=parent_id, error=str(e)
                        )

            logger.info("Working children task complete", processed=len(results))
    except Exception as e:
        logger.error("Error in working children task", error=str(e), exc_info=True)


async def business_payout_task(application: Application):
    """Weekly business payout task - runs every Friday at configured time."""
    logger.info("Running weekly business payouts")

    try:
        with get_db() as db:
            payout_count, total_paid = BusinessService.payout_all_businesses(db)

            logger.info(
                "Business payouts completed",
                businesses_paid=payout_count,
                total_diamonds=total_paid,
            )

            # Notify all users who received payouts
            if payout_count > 0:
                # Get unique users with businesses
                from app.database.models import Business, User

                business_users = db.query(Business.user_id).distinct().all()

                for (user_id,) in business_users:
                    user = db.query(User).filter(User.telegram_id == user_id).first()
                    if not user:
                        continue

                    user_businesses = BusinessService.get_user_businesses(db, user_id)
                    user_total = sum(b["weekly_payout"] for b in user_businesses)

                    if user_total > 0:
                        from app.utils.formatters import format_diamonds

                        message = (
                            f"💼 <b>Еженедельный доход!</b>\n\n"
                            f"Твои бизнесы принесли:\n"
                            f"💰 +{format_diamonds(user_total)}\n\n"
                            f"📊 Баланс: {format_diamonds(user.balance)}"
                        )

                        try:
                            await application.bot.send_message(chat_id=user_id, text=message, parse_mode="HTML")
                            logger.info("Business payout notification sent", user_id=user_id, amount=user_total)
                        except Exception as e:
                            logger.warning("Failed to notify user about business payout", user_id=user_id, error=str(e))

    except Exception as e:
        logger.error("Error in business payout task", error=str(e), exc_info=True)


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

    # Process working children every 4 hours
    scheduler.add_job(
        process_working_children_task,
        trigger=IntervalTrigger(hours=4),
        args=[application],
        id="process_working_children",
        name="Process working children payouts",
        replace_existing=True,
    )

    # Weekly business payouts (default: Friday at 18:00)
    scheduler.add_job(
        business_payout_task,
        trigger=CronTrigger(
            day_of_week=config.business_payout_day,
            hour=config.business_payout_hour,
            minute=config.business_payout_minute,
        ),
        args=[application],
        id="business_payout",
        name="Weekly business payouts",
        replace_existing=True,
    )

    # Weekly tax collection (Sunday at 20:00)
    scheduler.add_job(
        collect_taxes_task,
        trigger=CronTrigger(day_of_week=6, hour=20, minute=0),
        args=[application],
        id="collect_taxes",
        name="Weekly tax collection",
        replace_existing=True,
    )

    # Weekly lottery draw (Saturday at 21:00 Moscow / 18:00 UTC)
    from app.handlers.lottery import draw_lottery

    scheduler.add_job(
        draw_lottery,
        trigger=CronTrigger(day_of_week=5, hour=18, minute=0),
        args=[application],
        id="lottery_draw",
        name="Weekly lottery draw",
        replace_existing=True,
    )

    # Clean up stale heists and roulette rounds every 5 minutes
    scheduler.add_job(
        cleanup_stale_games_task,
        trigger=IntervalTrigger(minutes=5),
        args=[application],
        id="cleanup_stale_games",
        name="Cleanup stale heists/roulette",
        replace_existing=True,
    )

    # Clean up expired cooldowns every 6 hours
    scheduler.add_job(
        cleanup_expired_cooldowns_task,
        trigger=IntervalTrigger(hours=6),
        args=[application],
        id="cleanup_cooldowns",
        name="Cleanup expired cooldowns",
        replace_existing=True,
    )

    logger.info(
        "Scheduler started successfully",
        business_payout_schedule=f"Day {config.business_payout_day} at {config.business_payout_hour}:{config.business_payout_minute:02d}",
    )

    scheduler.start()


async def collect_taxes_task(application: Application):
    """Weekly tax collection — 5% on balance above 50k."""
    logger.info("Running weekly tax collection")

    try:
        from app.constants import TAX_RATE, TAX_THRESHOLD
        from app.database.models import TaxPayment, User
        from app.utils.formatters import format_diamonds

        with get_db() as db:
            rich_users = db.query(User).filter(User.balance > TAX_THRESHOLD).all()

            total_collected = 0
            taxed_count = 0

            for user in rich_users:
                taxable = user.balance - TAX_THRESHOLD
                tax = int(taxable * TAX_RATE)

                if tax <= 0:
                    continue

                user.balance -= tax
                total_collected += tax
                taxed_count += 1

                db.add(TaxPayment(user_id=user.telegram_id, amount=tax))

                try:
                    await application.bot.send_message(
                        chat_id=user.telegram_id,
                        text=(
                            f"🏛 <b>Налоговая служба</b>\n\n"
                            f"Еженедельный налог:\n"
                            f"💸 -{format_diamonds(tax)}\n\n"
                            f"💰 Баланс: {format_diamonds(user.balance)}"
                        ),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.warning("Failed to notify user about tax", user_id=user.telegram_id, error=str(e))

            logger.info("Tax collection complete", taxed=taxed_count, total=total_collected)
    except Exception as e:
        logger.error("Error in tax collection task", error=str(e), exc_info=True)


async def cleanup_stale_games_task(application: Application):
    """Clean up expired heists and roulette rounds, refunding players."""
    try:
        from app.handlers.heist import HEIST_JOIN_TIMEOUT_SECONDS, _refund_all as heist_refund, active_heists
        from app.handlers.roulette import RR_JOIN_TIMEOUT_SECONDS, _refund_all as rr_refund, active_rounds

        now = datetime.utcnow()
        stale_heist_chats = []
        stale_rr_chats = []

        for chat_id, heist in list(active_heists.items()):
            elapsed = (now - heist["created_at"]).total_seconds()
            if elapsed > HEIST_JOIN_TIMEOUT_SECONDS + 60:  # +60s grace period
                stale_heist_chats.append(chat_id)

        for chat_id in stale_heist_chats:
            heist = active_heists.pop(chat_id, None)
            if heist:
                heist_refund(heist)
                logger.info("Stale heist cleaned up", chat_id=chat_id, players=len(heist["players"]))

        for chat_id, rnd in list(active_rounds.items()):
            elapsed = (now - rnd["created_at"]).total_seconds()
            if elapsed > RR_JOIN_TIMEOUT_SECONDS + 60:
                stale_rr_chats.append(chat_id)

        for chat_id in stale_rr_chats:
            rnd = active_rounds.pop(chat_id, None)
            if rnd:
                rr_refund(rnd)
                logger.info("Stale roulette round cleaned up", chat_id=chat_id, players=len(rnd["players"]))

        total = len(stale_heist_chats) + len(stale_rr_chats)
        if total > 0:
            logger.info("Stale games cleanup done", heists=len(stale_heist_chats), roulette=len(stale_rr_chats))
    except Exception as e:
        logger.error("Error in stale games cleanup", error=str(e), exc_info=True)


async def cleanup_expired_cooldowns_task(application: Application):
    """Clean up expired cooldowns to prevent database bloat."""
    logger.info("Cleaning up expired cooldowns")

    try:
        from app.database.models import Cooldown

        with get_db() as db:
            deleted = db.query(Cooldown).filter(Cooldown.expires_at < datetime.utcnow()).delete()
            logger.info("Expired cooldowns cleaned up", deleted=deleted)
    except Exception as e:
        logger.error("Error in cooldown cleanup task", error=str(e), exc_info=True)


def stop_scheduler():
    """Stop the background tasks scheduler."""
    global scheduler

    if scheduler is None:
        logger.warning("Scheduler not started")
        return

    logger.info("Stopping scheduler")
    try:
        scheduler.shutdown()
    except Exception as e:
        logger.error("Error shutting down scheduler", error=str(e))
    finally:
        scheduler = None
    logger.info("Scheduler stopped")
