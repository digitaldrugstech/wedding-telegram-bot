"""Bot initialization and setup."""

import html
import json
import traceback

import structlog
from telegram import Update
from telegram.ext import Application, ContextTypes

from app.config import config
from app.handlers.admin import register_admin_handlers
from app.handlers.blackjack import register_blackjack_handlers
from app.handlers.bounty import register_bounty_handlers
from app.handlers.business import register_business_handlers
from app.handlers.casino import register_casino_handlers
from app.handlers.children import register_children_handlers
from app.handlers.clanwar import register_clanwar_handlers
from app.handlers.coinflip import register_coinflip_handlers
from app.handlers.crate import register_crate_handlers
from app.handlers.daily import register_daily_handlers
from app.handlers.duel import register_duel_handlers
from app.handlers.economy import register_economy_handlers
from app.handlers.feedback import register_feedback_handlers
from app.handlers.fishing import register_fishing_handlers
from app.handlers.gang import register_gang_handlers
from app.handlers.giftbox import register_giftbox_handlers
from app.handlers.growth import register_growth_handlers
from app.handlers.heist import register_heist_handlers
from app.handlers.house import register_house_handlers
from app.handlers.insurance import register_insurance_handlers
from app.handlers.kidnap import register_kidnap_handlers
from app.handlers.lottery import register_lottery_handlers
from app.handlers.market import register_market_handlers
from app.handlers.marriage import register_marriage_handlers
from app.handlers.menu import register_menu_handlers
from app.handlers.mine import register_mine_handlers
from app.handlers.pet import register_pet_handlers
from app.handlers.premium import register_premium_handlers
from app.handlers.prestige import register_prestige_handlers
from app.handlers.quest import initialize_quests, register_quest_handlers
from app.handlers.raid import register_raid_handlers
from app.handlers.referral import register_referral_handlers
from app.handlers.rob import register_rob_handlers
from app.handlers.roulette import register_roulette_handlers
from app.handlers.scratch import register_scratch_handlers
from app.handlers.shop import register_shop_handlers
from app.handlers.social import register_social_handlers
from app.handlers.start import register_start_handlers
from app.handlers.toto import register_toto_handlers
from app.handlers.utils import register_utils_handlers
from app.handlers.wheel import register_wheel_handlers
from app.handlers.work import register_work_handlers

logger = structlog.get_logger()


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors and notify admin."""
    # Silently ignore flood control — handled by safe_edit_message retry
    from telegram.error import RetryAfter

    if isinstance(context.error, RetryAfter):
        logger.warning("Flood control", retry_after=context.error.retry_after)
        return

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
                "❌ <b>Ошибка</b>\n\nПроизошла ошибка при обработке команды\n\nПопробуй ещё раз или напиши /bug_report",
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
    register_daily_handlers(application)
    register_lottery_handlers(application)
    register_social_handlers(application)
    register_quest_handlers(application)
    register_pet_handlers(application)
    register_duel_handlers(application)
    register_mine_handlers(application)
    register_wheel_handlers(application)
    register_scratch_handlers(application)
    register_blackjack_handlers(application)
    register_shop_handlers(application)
    register_giftbox_handlers(application)
    register_prestige_handlers(application)
    register_coinflip_handlers(application)
    register_rob_handlers(application)
    register_insurance_handlers(application)
    register_bounty_handlers(application)
    register_gang_handlers(application)
    register_raid_handlers(application)
    register_clanwar_handlers(application)
    register_roulette_handlers(application)
    register_crate_handlers(application)
    register_referral_handlers(application)
    register_economy_handlers(application)
    register_premium_handlers(application)
    register_heist_handlers(application)
    register_fishing_handlers(application)
    register_kidnap_handlers(application)
    register_toto_handlers(application)
    register_market_handlers(application)
    register_feedback_handlers(application)
    register_growth_handlers(application)
    register_admin_handlers(application)

    # Register error handler
    application.add_error_handler(error_handler)

    # Initialize quest templates (once at startup)
    initialize_quests()

    logger.info("Bot handlers registered")

    return application


async def post_init(application: Application):
    """Post-initialization hook."""
    logger.info("Bot initialized successfully")


async def post_shutdown(application: Application):
    """Post-shutdown hook — refund in-memory bets before exit."""
    # Refund active roulette rounds
    try:
        from app.handlers.roulette import _refund_all as rr_refund
        from app.handlers.roulette import active_rounds as rr_rounds

        for chat_id, rnd in list(rr_rounds.items()):
            rr_refund(rnd)
            logger.info("Refunded roulette round on shutdown", chat_id=chat_id, players=len(rnd["players"]))
        rr_rounds.clear()
    except Exception as e:
        logger.error("Failed to refund roulette rounds", error=str(e))

    # Refund active heist entries
    try:
        from app.handlers.heist import _refund_all as heist_refund
        from app.handlers.heist import active_heists

        for chat_id, h in list(active_heists.items()):
            heist_refund(h)
            logger.info("Refunded heist on shutdown", chat_id=chat_id, players=len(h["players"]))
        active_heists.clear()
    except Exception as e:
        logger.error("Failed to refund heists", error=str(e))

    # Refund active toto round
    try:
        from app.handlers.toto import refund_active_toto

        refund_active_toto()
        logger.info("Refunded toto bets on shutdown")
    except Exception as e:
        logger.error("Failed to refund toto", error=str(e))

    # Clear stale raids (no fees to refund, just cleanup)
    try:
        from app.handlers.raid import active_raids

        if active_raids:
            logger.info("Clearing active raids on shutdown", count=len(active_raids))
            active_raids.clear()
    except Exception as e:
        logger.error("Failed to clear raids", error=str(e))

    logger.info("Bot shutdown complete")
