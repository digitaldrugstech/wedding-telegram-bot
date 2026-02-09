"""Mining command handlers."""

import random
from datetime import datetime, timedelta

import structlog
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import Cooldown, User
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds

logger = structlog.get_logger()

MINE_COOLDOWN_HOURS = 2
MINE_MIN_REWARD = 5
MINE_MAX_REWARD = 25
RARE_CHANCE = 5  # 5% chance
RARE_MULTIPLIER = 3
COLLAPSE_CHANCE = 10  # 10% chance


@require_registered
async def mine_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mine diamonds (/mine)."""
    user_id = update.effective_user.id

    with get_db() as db:
        # Check cooldown
        cooldown = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "mine").first()

        if cooldown and cooldown.expires_at > datetime.utcnow():
            remaining = cooldown.expires_at - datetime.utcnow()
            hours, remainder = divmod(remaining.total_seconds(), 3600)
            minutes = remainder // 60

            time_str = []
            if hours > 0:
                time_str.append(f"{int(hours)}ч")
            if minutes > 0:
                time_str.append(f"{int(minutes)}м")

            await update.message.reply_text(f"⏰ Можешь майнить через {' '.join(time_str)}")
            return

        # Single roll for mutually exclusive events
        roll = random.randint(1, 100)
        is_collapse = roll <= COLLAPSE_CHANCE
        is_rare = not is_collapse and roll <= COLLAPSE_CHANCE + RARE_CHANCE

        if is_collapse:
            # Cave collapse - no reward
            text = "💥 <b>Обвал!</b>\n\n" "Шахта обрушилась, ты еле выбрался\n" "Ничего не добыл"
            reward = 0

        elif is_rare:
            # Rare gem found
            base_reward = random.randint(MINE_MIN_REWARD, MINE_MAX_REWARD)
            reward = base_reward * RARE_MULTIPLIER

            text = (
                f"💎 <b>Редкий камень!</b>\n\n"
                f"Ты нашёл редкий кристалл\n"
                f"Награда: {format_diamonds(reward)}\n\n"
                f"⭐ Награда x{RARE_MULTIPLIER}"
            )

        else:
            # Normal mining
            reward = random.randint(MINE_MIN_REWARD, MINE_MAX_REWARD)
            text = f"⛏️ <b>Майнинг</b>\n\nТы добыл {format_diamonds(reward)}"

        # Update balance
        user = db.query(User).filter(User.telegram_id == user_id).first()
        user.balance += reward

        # Set cooldown
        expires_at = datetime.utcnow() + timedelta(hours=MINE_COOLDOWN_HOURS)

        if cooldown:
            cooldown.expires_at = expires_at
        else:
            cooldown = Cooldown(user_id=user_id, action="mine", expires_at=expires_at)
            db.add(cooldown)

        logger.info("Mining completed", user_id=user_id, reward=reward, is_rare=is_rare, is_collapse=is_collapse)

    await update.message.reply_text(text, parse_mode="HTML")


def register_mine_handlers(application):
    """Register mine handlers."""
    application.add_handler(CommandHandler("mine", mine_command))
    logger.info("Mine handlers registered")
