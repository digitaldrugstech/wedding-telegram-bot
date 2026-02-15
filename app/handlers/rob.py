"""Rob command handler — steal diamonds with risk."""

import html
import random
from datetime import datetime, timedelta

import structlog
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import Cooldown, User
from app.handlers.bounty import collect_bounties
from app.handlers.insurance import has_active_insurance
from app.handlers.quest import update_quest_progress
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds

logger = structlog.get_logger()

ROB_COOLDOWN_HOURS = 4
ROB_SUCCESS_CHANCE = 0.40  # 40% success
ROB_MIN_STEAL_PERCENT = 5
ROB_MAX_STEAL_PERCENT = 15
ROB_FINE_MULTIPLIER = 1.5  # Fine = 150% of what you'd steal (net negative EV)
ROB_MIN_TARGET_BALANCE = 100


@require_registered
async def rob_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /rob (reply to someone's message)."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    # Must reply to someone
    if not update.message.reply_to_message or not update.message.reply_to_message.from_user:
        await update.message.reply_text("❌ Реплайни на сообщение того, кого хочешь ограбить")
        return

    target_id = update.message.reply_to_message.from_user.id
    target_name = html.escape(
        update.message.reply_to_message.from_user.username
        or update.message.reply_to_message.from_user.first_name
        or f"User{target_id}"
    )

    # Can't rob yourself
    if target_id == user_id:
        await update.message.reply_text("❌ Нельзя ограбить себя")
        return

    # Can't rob a bot
    if update.message.reply_to_message.from_user.is_bot:
        await update.message.reply_text("❌ Нельзя ограбить бота")
        return

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        target = db.query(User).filter(User.telegram_id == target_id).first()

        if not target:
            await update.message.reply_text("❌ Этот игрок не зарегистрирован")
            return

        # Check cooldown
        cooldown = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "rob").first()
        if cooldown and cooldown.expires_at > datetime.utcnow():
            remaining = cooldown.expires_at - datetime.utcnow()
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            time_parts = []
            if hours > 0:
                time_parts.append(f"{hours}ч")
            if minutes > 0:
                time_parts.append(f"{minutes}м")
            await update.message.reply_text(f"⏰ Следующее ограбление через {' '.join(time_parts)}")
            return

        # Target must have enough
        if target.balance < ROB_MIN_TARGET_BALANCE:
            await update.message.reply_text(
                f"❌ У @{target_name} слишком мало алмазов\n\nМинимум у жертвы: {format_diamonds(ROB_MIN_TARGET_BALANCE)}"
            )
            return

        # Check premium shield
        from app.handlers.premium import has_active_boost

        if has_active_boost(target_id, "shield", db=db):
            await update.message.reply_text("🛡 У этого игрока есть премиум-щит\n\nОграбление невозможно")
            return

        # Check insurance
        if has_active_insurance(db, target_id):
            await update.message.reply_text("🛡 У этого игрока есть страховка\n\nОграбление невозможно")
            return

        # Calculate steal amount
        steal_percent = random.randint(ROB_MIN_STEAL_PERCENT, ROB_MAX_STEAL_PERCENT)
        steal_amount = max(1, int(target.balance * steal_percent / 100))

        # Roll for success
        success = random.random() < ROB_SUCCESS_CHANCE

        bounty_collected = 0
        fine = 0

        if success:
            # Steal from target
            target.balance -= steal_amount
            user.balance += steal_amount

            # Collect bounties on target
            bounty_collected = collect_bounties(db, target_id, user_id)
            if bounty_collected > 0:
                user.balance += bounty_collected

            result_balance = user.balance
        else:
            # Pay fine
            fine = int(steal_amount * ROB_FINE_MULTIPLIER)
            fine = min(fine, user.balance)  # Can't go negative
            user.balance -= fine
            result_balance = user.balance

        # Set cooldown
        expires_at = datetime.utcnow() + timedelta(hours=ROB_COOLDOWN_HOURS)
        if cooldown:
            cooldown.expires_at = expires_at
        else:
            db.add(Cooldown(user_id=user_id, action="rob", expires_at=expires_at))

    # Build message
    if success:
        text = (
            f"🔫 <b>Ограбление!</b>\n\n"
            f"Ты ограбил @{target_name}!\n"
            f"💰 Украдено: {format_diamonds(steal_amount)}\n"
        )
        if bounty_collected > 0:
            text += f"🎯 Награда собрана: {format_diamonds(bounty_collected)}\n"
        text += f"\nБаланс: {format_diamonds(result_balance)}"
    else:
        text = (
            f"🚨 <b>Провал!</b>\n\n"
            f"Тебя поймали при попытке ограбить @{target_name}!\n"
            f"💸 Штраф: {format_diamonds(fine)}\n\n"
            f"Баланс: {format_diamonds(result_balance)}"
        )

    await update.message.reply_text(text, parse_mode="HTML")

    # Notify victim with shield nudge
    if success:
        try:
            from app.handlers.premium import build_premium_nudge

            shield_nudge = build_premium_nudge("robbed", target_id)
            victim_text = f"🚨 <b>Тебя ограбили!</b>\n\n" f"💸 Украдено: {format_diamonds(steal_amount)}{shield_nudge}"
            await context.bot.send_message(chat_id=target_id, text=victim_text, parse_mode="HTML")
        except Exception:
            pass

    if success:
        try:
            update_quest_progress(user_id, "rob")
        except Exception:
            pass

    logger.info("Rob attempt", user_id=user_id, target_id=target_id, success=success, amount=steal_amount)


def register_rob_handlers(application):
    """Register rob handlers."""
    application.add_handler(CommandHandler("rob", rob_command))
    logger.info("Rob handlers registered")
