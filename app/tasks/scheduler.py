"""Background tasks scheduler using APScheduler."""

import random
from datetime import datetime

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from telegram.ext import Application

from app.config import config
from app.constants import (
    AUCTION_ITEMS,
    STOCK_MAX_PRICE,
    STOCK_MIN_PRICE,
    STOCK_PRICE_CHANGE_PERCENTAGE,
    TAX_RATE,
    TAX_THRESHOLD,
)
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


async def process_investments_task(application: Application):
    """Process completed investments."""
    logger.info("Processing completed investments")

    try:
        from app.database.models import Investment, User
        from app.utils.formatters import format_diamonds

        with get_db() as db:
            # Find completed investments
            completed = (
                db.query(Investment)
                .filter(Investment.is_completed.is_(False), Investment.completes_at <= datetime.utcnow())
                .all()
            )

            for investment in completed:
                user = db.query(User).filter(User.telegram_id == investment.user_id).first()
                if not user:
                    continue

                # Calculate return
                return_amount = int(investment.amount * (1 + investment.return_percentage / 100))
                profit = return_amount - investment.amount

                user.balance += return_amount
                investment.is_completed = True

                # Notify user
                emoji = "📈" if profit > 0 else "📉" if profit < 0 else "📊"
                result_text = (
                    f"прибыль: +{format_diamonds(profit)}"
                    if profit > 0
                    else f"убыток: {format_diamonds(profit)}" if profit < 0 else "без изменений"
                )

                message = (
                    f"{emoji} <b>Инвестиция завершена</b>\n\n"
                    f"Вложено: {format_diamonds(investment.amount)}\n"
                    f"Доходность: {investment.return_percentage:+d}%\n"
                    f"Результат: {result_text}\n\n"
                    f"Получено: {format_diamonds(return_amount)}\n"
                    f"Баланс: {format_diamonds(user.balance)}"
                )

                try:
                    await application.bot.send_message(chat_id=investment.user_id, text=message, parse_mode="HTML")
                    logger.info(
                        "Investment completed",
                        user_id=investment.user_id,
                        amount=investment.amount,
                        return_percentage=investment.return_percentage,
                    )
                except Exception as e:
                    logger.warning("Failed to notify user about investment", user_id=investment.user_id, error=str(e))

            if completed:
                logger.info("Investments processed", count=len(completed))

    except Exception as e:
        logger.error("Error in investment processing task", error=str(e), exc_info=True)


async def update_stock_prices_task(application: Application):
    """Update stock prices hourly."""
    logger.info("Updating stock prices")

    try:
        from app.database.models import Stock

        with get_db() as db:
            stocks = db.query(Stock).all()

            for stock in stocks:
                # Random price change
                change_percent = random.uniform(-STOCK_PRICE_CHANGE_PERCENTAGE, STOCK_PRICE_CHANGE_PERCENTAGE)
                new_price = int(stock.price * (1 + change_percent / 100))

                # Clamp to min/max
                new_price = max(STOCK_MIN_PRICE, min(STOCK_MAX_PRICE, new_price))

                stock.price = new_price
                stock.last_updated = datetime.utcnow()

            logger.info("Stock prices updated", count=len(stocks))

    except Exception as e:
        logger.error("Error in stock price update task", error=str(e), exc_info=True)


async def close_auctions_task(application: Application):
    """Close expired auctions."""
    logger.info("Checking for expired auctions")

    try:
        from app.database.models import Auction, User
        from app.utils.formatters import format_diamonds

        with get_db() as db:
            # Find expired auctions
            expired = db.query(Auction).filter(Auction.is_active.is_(True), Auction.ends_at <= datetime.utcnow()).all()

            for auction in expired:
                auction.is_active = False

                if auction.current_winner_id:
                    # Winner gets the item
                    item_data = AUCTION_ITEMS[auction.item]

                    winner_message = (
                        f"🎉 <b>Ты выиграл аукцион!</b>\n\n"
                        f"{item_data['emoji']} {item_data['name']}\n"
                        f"Твоя ставка: {format_diamonds(auction.current_price)}\n\n"
                        f"Эффект действует {item_data['effect_days']} дней"
                    )

                    try:
                        await application.bot.send_message(
                            chat_id=auction.current_winner_id, text=winner_message, parse_mode="HTML"
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to notify auction winner", user_id=auction.current_winner_id, error=str(e)
                        )

                    # Notify creator
                    creator_message = (
                        f"🔨 <b>Аукцион завершен</b>\n\n"
                        f"{item_data['emoji']} {item_data['name']}\n"
                        f"Продано за {format_diamonds(auction.current_price)}"
                    )

                    creator = db.query(User).filter(User.telegram_id == auction.creator_id).first()
                    if creator:
                        creator.balance += auction.current_price

                    try:
                        await application.bot.send_message(
                            chat_id=auction.creator_id, text=creator_message, parse_mode="HTML"
                        )
                    except Exception as e:
                        logger.warning("Failed to notify auction creator", user_id=auction.creator_id, error=str(e))

                    logger.info(
                        "Auction closed with winner",
                        auction_id=auction.id,
                        winner_id=auction.current_winner_id,
                        price=auction.current_price,
                    )
                else:
                    # No bids, notify creator
                    try:
                        await application.bot.send_message(
                            chat_id=auction.creator_id,
                            text="🔨 Аукцион завершен без ставок",
                            parse_mode="HTML",
                        )
                    except Exception as e:
                        logger.warning("Failed to notify auction creator", user_id=auction.creator_id, error=str(e))

                    logger.info("Auction closed without bids", auction_id=auction.id)

            if expired:
                logger.info("Auctions closed", count=len(expired))

    except Exception as e:
        logger.error("Error in auction closing task", error=str(e), exc_info=True)


async def collect_taxes_task(application: Application):
    """Weekly tax collection."""
    logger.info("Collecting weekly taxes")

    try:
        from app.database.models import TaxPayment, User
        from app.utils.formatters import format_diamonds

        with get_db() as db:
            users = db.query(User).filter(User.balance > TAX_THRESHOLD).all()

            total_collected = 0

            for user in users:
                taxable_amount = user.balance - TAX_THRESHOLD
                tax_amount = int(taxable_amount * TAX_RATE)

                if tax_amount > 0:
                    user.balance -= tax_amount
                    total_collected += tax_amount

                    # Record tax payment
                    tax_payment = TaxPayment(
                        user_id=user.telegram_id,
                        amount=tax_amount,
                        balance_at_time=user.balance + tax_amount,
                    )
                    db.add(tax_payment)

                    # Notify user
                    message = (
                        f"🏛 <b>Налоговый сбор</b>\n\n"
                        f"Списано: {format_diamonds(tax_amount)}\n"
                        f"Ставка: {int(TAX_RATE * 100)}%\n\n"
                        f"Баланс: {format_diamonds(user.balance)}"
                    )

                    try:
                        await application.bot.send_message(chat_id=user.telegram_id, text=message, parse_mode="HTML")
                    except Exception as e:
                        logger.warning("Failed to notify user about tax", user_id=user.telegram_id, error=str(e))

            logger.info("Tax collection completed", users_taxed=len(users), total_collected=total_collected)

    except Exception as e:
        logger.error("Error in tax collection task", error=str(e), exc_info=True)


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

    # Process investments every hour
    scheduler.add_job(
        process_investments_task,
        trigger=IntervalTrigger(hours=1),
        args=[application],
        id="process_investments",
        name="Process completed investments",
        replace_existing=True,
    )

    # Update stock prices every hour
    scheduler.add_job(
        update_stock_prices_task,
        trigger=IntervalTrigger(hours=1),
        args=[application],
        id="update_stock_prices",
        name="Update stock prices",
        replace_existing=True,
    )

    # Close expired auctions every 15 minutes
    scheduler.add_job(
        close_auctions_task,
        trigger=IntervalTrigger(minutes=15),
        args=[application],
        id="close_auctions",
        name="Close expired auctions",
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
