"""Referral system handlers — viral growth mechanics."""

import html
from datetime import datetime

import structlog
from sqlalchemy import desc, func
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.constants import (
    REFERRAL_ACTIVE_DAYS_REQUIRED,
    REFERRAL_INVITEE_REWARD,
    REFERRAL_INVITER_REWARD,
)
from app.database.connection import get_db
from app.database.models import Referral, User
from app.utils.decorators import button_owner_only, require_registered
from app.utils.formatters import format_diamonds, format_word
from app.utils.telegram_helpers import safe_edit_message

logger = structlog.get_logger()

BOT_USERNAME = None  # Set dynamically on first use


def get_referral_link(user_id: int, bot_username: str = None) -> str:
    """Generate a referral deep link for a user."""
    global BOT_USERNAME
    if bot_username:
        BOT_USERNAME = bot_username
    username = BOT_USERNAME or "prdx_wedding_bot"
    return f"https://t.me/{username}?start=ref_{user_id}"


def process_referral_registration(referrer_id: int, referred_id: int) -> bool:
    """
    Process a referral when a new user registers via deep link.

    Returns True if referral was recorded, False if invalid.
    Anti-abuse: can't refer yourself, can't be referred twice.
    """
    if referrer_id == referred_id:
        return False

    with get_db() as db:
        # Check referrer exists
        referrer = db.query(User).filter(User.telegram_id == referrer_id).first()
        if not referrer:
            return False

        # Check if referred user already has a referral
        existing = db.query(Referral).filter(Referral.referred_id == referred_id).first()
        if existing:
            return False

        # Create referral record
        referral = Referral(
            referrer_id=referrer_id,
            referred_id=referred_id,
        )
        db.add(referral)

    logger.info("Referral recorded", referrer_id=referrer_id, referred_id=referred_id)
    return True


def track_referral_activity(user_id: int):
    """
    Track daily activity for a referred user.
    Called from @require_registered on each command.
    When active_days reaches REFERRAL_ACTIVE_DAYS_REQUIRED, grant rewards.
    """
    today_str = datetime.utcnow().strftime("%Y-%m-%d")

    with get_db() as db:
        referral = db.query(Referral).filter(Referral.referred_id == user_id).first()

        if not referral or referral.reward_given:
            return

        # Already tracked today
        if referral.last_active_date == today_str:
            return

        # Increment active days
        referral.last_active_date = today_str
        referral.active_days += 1

        logger.info(
            "Referral activity tracked",
            referred_id=user_id,
            referrer_id=referral.referrer_id,
            active_days=referral.active_days,
        )

        # Check if threshold reached
        reward_reached = False
        referrer_id = referral.referrer_id
        referred_id = referral.referred_id

        if referral.active_days >= REFERRAL_ACTIVE_DAYS_REQUIRED:
            referral.reward_given = True
            referral.reward_given_at = datetime.utcnow()

            # Grant reward to inviter
            referrer = db.query(User).filter(User.telegram_id == referral.referrer_id).first()
            if referrer:
                referrer.balance += REFERRAL_INVITER_REWARD

            # Count completed referrals in the same session (no nested get_db)
            total_refs = (
                db.query(Referral)
                .filter(Referral.referrer_id == referrer_id, Referral.reward_given.is_(True))
                .count()
            )

            reward_reached = True

            logger.info(
                "Referral reward granted",
                referrer_id=referrer_id,
                referred_id=referred_id,
                inviter_reward=REFERRAL_INVITER_REWARD,
            )

    # Award achievement outside DB session to avoid nested get_db()
    if reward_reached:
        try:
            from app.handlers.social import check_and_award_achievement

            if total_refs >= 1:
                check_and_award_achievement(referrer_id, "recruiter")
            if total_refs >= 10:
                check_and_award_achievement(referrer_id, "influencer")
        except Exception:
            pass


@require_registered
async def invite_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /invite command — show personal referral link."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    link = get_referral_link(user_id, bot_username=context.bot.username)

    with get_db() as db:
        # Count referrals
        total_refs = db.query(Referral).filter(Referral.referrer_id == user_id).count()
        completed_refs = (
            db.query(Referral)
            .filter(Referral.referrer_id == user_id, Referral.reward_given.is_(True))
            .count()
        )
        pending_refs = total_refs - completed_refs

    text = (
        f"📨 <b>Пригласи друзей!</b>\n\n"
        f"Твоя ссылка:\n"
        f"<code>{link}</code>\n\n"
        f"<b>Награды:</b>\n"
        f"👤 Друг регистрируется → он получает {format_diamonds(REFERRAL_INVITEE_REWARD)}\n"
        f"🎯 Друг играет {format_word(REFERRAL_ACTIVE_DAYS_REQUIRED, 'день', 'дня', 'дней')} → ты получаешь {format_diamonds(REFERRAL_INVITER_REWARD)}\n\n"
        f"<b>Твоя статистика:</b>\n"
        f"✅ Завершённые: {completed_refs}\n"
        f"⏳ В процессе: {pending_refs}\n"
        f"💰 Заработано: {format_diamonds(completed_refs * REFERRAL_INVITER_REWARD)}\n\n"
        f"💡 Отправь ссылку друзьям или в чат!"
    )

    # Share button
    share_text = (
        f"Заходи в Wedding Bot — семейная жизнь на сервере! "
        f"Женись, работай, играй в казино. "
        f"Тебе дадут {REFERRAL_INVITEE_REWARD} алмазов при старте!\n{link}"
    )
    keyboard = [
        [
            InlineKeyboardButton(
                "📤 Поделиться",
                switch_inline_query=share_text,
            )
        ],
        [InlineKeyboardButton("📊 Топ рефералов", callback_data=f"ref:top:{user_id}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)


@require_registered
async def myrefs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /myrefs command — show list of referrals and their status."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        referrals = (
            db.query(Referral)
            .filter(Referral.referrer_id == user_id)
            .order_by(desc(Referral.referred_at))
            .limit(20)
            .all()
        )

        if not referrals:
            link = get_referral_link(user_id)
            await update.message.reply_text(
                "📨 <b>Мои рефералы</b>\n\n"
                "У тебя пока нет рефералов\n\n"
                f"Отправь ссылку друзьям:\n<code>{link}</code>",
                parse_mode="HTML",
            )
            return

        text = "📨 <b>Мои рефералы</b>\n\n"
        for ref in referrals:
            referred_user = db.query(User).filter(User.telegram_id == ref.referred_id).first()
            name = f"@{html.escape(referred_user.username)}" if referred_user and referred_user.username else f"ID {ref.referred_id}"

            if ref.reward_given:
                status = f"✅ Готово (+{format_diamonds(REFERRAL_INVITER_REWARD)})"
            else:
                days_left = REFERRAL_ACTIVE_DAYS_REQUIRED - ref.active_days
                status = f"⏳ {ref.active_days}/{REFERRAL_ACTIVE_DAYS_REQUIRED} дней (осталось {days_left})"

            text += f"• {name} — {status}\n"

    await update.message.reply_text(text, parse_mode="HTML")


@button_owner_only
async def ref_top_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle referral top leaderboard callback."""
    query = update.callback_query
    await query.answer()

    if not update.effective_user:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        # Top inviters by completed referrals
        top_referrers = (
            db.query(
                Referral.referrer_id,
                func.count(Referral.id).label("ref_count"),
            )
            .filter(Referral.reward_given.is_(True))
            .group_by(Referral.referrer_id)
            .order_by(desc("ref_count"))
            .limit(10)
            .all()
        )

        text = "📊 <b>Топ рефералов</b>\n\n"

        if not top_referrers:
            text += "Пока пусто — стань первым!\n\n/invite — получить ссылку"
        else:
            for i, (referrer_id, ref_count) in enumerate(top_referrers, 1):
                referrer = db.query(User).filter(User.telegram_id == referrer_id).first()
                name = f"@{html.escape(referrer.username)}" if referrer and referrer.username else f"ID {referrer_id}"
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                earned = ref_count * REFERRAL_INVITER_REWARD
                text += f"{medal} {name} — {format_word(ref_count, 'реферал', 'реферала', 'рефералов')} ({format_diamonds(earned)})\n"

        # Show current user's rank
        user_refs = (
            db.query(Referral)
            .filter(Referral.referrer_id == user_id, Referral.reward_given.is_(True))
            .count()
        )
        text += f"\n\nТвои рефералы: {user_refs}"

    keyboard = [[InlineKeyboardButton("📨 Моя ссылка", callback_data=f"ref:mylink:{user_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await safe_edit_message(query, text, reply_markup=reply_markup)


@button_owner_only
async def ref_mylink_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's referral link inline."""
    query = update.callback_query
    await query.answer()

    if not update.effective_user:
        return

    user_id = update.effective_user.id
    link = get_referral_link(user_id)

    with get_db() as db:
        total_refs = db.query(Referral).filter(Referral.referrer_id == user_id).count()
        completed_refs = (
            db.query(Referral)
            .filter(Referral.referrer_id == user_id, Referral.reward_given.is_(True))
            .count()
        )

    text = (
        f"📨 <b>Твоя ссылка</b>\n\n"
        f"<code>{link}</code>\n\n"
        f"✅ Завершённые: {completed_refs}\n"
        f"📊 Всего: {total_refs}\n"
        f"💰 Заработано: {format_diamonds(completed_refs * REFERRAL_INVITER_REWARD)}"
    )

    keyboard = [[InlineKeyboardButton("📊 Топ рефералов", callback_data=f"ref:top:{user_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await safe_edit_message(query, text, reply_markup=reply_markup)


def register_referral_handlers(application):
    """Register referral handlers."""
    application.add_handler(CommandHandler("invite", invite_command))
    application.add_handler(CommandHandler("myrefs", myrefs_command))
    application.add_handler(CallbackQueryHandler(ref_top_callback, pattern=r"^ref:top:"))
    application.add_handler(CallbackQueryHandler(ref_mylink_callback, pattern=r"^ref:mylink:"))
    logger.info("Referral handlers registered")
