"""Wheel of Fortune command handlers."""

import asyncio
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

WHEEL_COST = 50
WHEEL_COOLDOWN_HOURS = 1

# Prize pool with weights (EV=44, cost=50, house edge=12%)
PRIZES = [
    (0, 40),  # 0 diamonds (40% chance)
    (25, 20),  # 25 diamonds (20% chance)
    (50, 15),  # 50 diamonds (15% chance)
    (75, 10),  # 75 diamonds (10% chance)
    (100, 7),  # 100 diamonds (7% chance)
    (150, 4),  # 150 diamonds (4% chance)
    (200, 3),  # 200 diamonds (3% chance)
    (500, 1),  # JACKPOT x10 (1% chance)
]


def get_random_prize():
    """Get random prize based on weights."""
    prizes, weights = zip(*PRIZES)
    return random.choices(prizes, weights=weights)[0]


@require_registered
async def wheel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Spin the wheel of fortune (/wheel)."""
    user_id = update.effective_user.id

    # Phase 1: Check balance and cooldown, deduct cost
    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()

        # Check balance
        if user.balance < WHEEL_COST:
            await update.message.reply_text(
                f"❌ Недостаточно алмазов\n\n"
                f"Нужно: {format_diamonds(WHEEL_COST)}\n"
                f"У тебя: {format_diamonds(user.balance)}"
            )
            return

        # Check cooldown
        cooldown = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "wheel").first()

        if cooldown and cooldown.expires_at > datetime.utcnow():
            remaining = cooldown.expires_at - datetime.utcnow()
            hours, remainder = divmod(remaining.total_seconds(), 3600)
            minutes = remainder // 60

            time_str = []
            if hours > 0:
                time_str.append(f"{int(hours)}ч")
            if minutes > 0:
                time_str.append(f"{int(minutes)}м")

            await update.message.reply_text(f"⏰ Можешь крутить колесо через {' '.join(time_str)}")
            return

        # Deduct cost and set cooldown
        user.balance -= WHEEL_COST

        expires_at = datetime.utcnow() + timedelta(hours=WHEEL_COOLDOWN_HOURS)
        if cooldown:
            cooldown.expires_at = expires_at
        else:
            cooldown = Cooldown(user_id=user_id, action="wheel", expires_at=expires_at)
            db.add(cooldown)

    # Phase 2: Animation (DB session released)
    prize = get_random_prize()

    msg = await update.message.reply_text("🎰 <b>Колесо Фортуны</b>\n\nКручу... 🎡", parse_mode="HTML")

    frames = [
        "🎰 <b>Колесо Фортуны</b>\n\nКручу... 🎡",
        "🎰 <b>Колесо Фортуны</b>\n\nКручу... 🎪",
        "🎰 <b>Колесо Фортуны</b>\n\nКручу... 🎭",
        "🎰 <b>Колесо Фортуны</b>\n\nКручу... 🎨",
        "🎰 <b>Колесо Фортуны</b>\n\nКручу... 🎡",
    ]

    for frame in frames:
        await asyncio.sleep(0.5)
        try:
            await msg.edit_text(frame, parse_mode="HTML")
        except Exception:
            pass

    await asyncio.sleep(0.5)

    # Phase 3: Award prize
    is_jackpot = prize == 500

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()

        # Apply lucky charm bonus to winnings
        lucky_bonus = 0
        if prize > 0:
            from app.handlers.premium import has_active_boost

            if has_active_boost(user_id, "lucky_charm"):
                lucky_bonus = int(prize * 0.15)
                prize += lucky_bonus

        if is_jackpot:
            actual_prize = WHEEL_COST * 10
            if lucky_bonus > 0:
                actual_prize += int(WHEEL_COST * 10 * 0.15)
            user.balance += actual_prize

            lucky_text = f"\n🍀 Талисман удачи: +{format_diamonds(int(WHEEL_COST * 10 * 0.15))}" if lucky_bonus > 0 else ""
            result_text = (
                f"🎰 <b>ДЖЕКПОТ!</b> 🎉🎉🎉\n\n"
                f"Невероятная удача!\n"
                f"Выигрыш: {format_diamonds(actual_prize)}{lucky_text}\n\n"
                f"⭐ Множитель x10"
            )

        elif prize == 0:
            # Lucky charm nudge on loss (throttled)
            from app.handlers.premium import build_premium_nudge, has_active_boost as _wh_boost

            nudge = ""
            if not _wh_boost(user_id, "lucky_charm"):
                nudge = build_premium_nudge("casino_loss", user_id)
            result_text = (
                f"🎰 <b>Колесо Фортуны</b>\n\n"
                f"Неудача...\n"
                f"Ты ничего не выиграл\n\n"
                f"Потрачено: {format_diamonds(WHEEL_COST)}{nudge}"
            )

        else:
            user.balance += prize
            net_win = prize - WHEEL_COST
            lucky_text = f"\n🍀 Талисман удачи: +{format_diamonds(lucky_bonus)}" if lucky_bonus > 0 else ""

            if net_win > 0:
                result_text = (
                    f"🎰 <b>Победа!</b>\n\n"
                    f"Выигрыш: {format_diamonds(prize)}{lucky_text}\n"
                    f"Чистая прибыль: {format_diamonds(net_win)}"
                )
            elif net_win == 0:
                result_text = (
                    f"🎰 <b>Колесо Фортуны</b>\n\n" f"Выигрыш: {format_diamonds(prize)}{lucky_text}\n" f"Ты вернул свои алмазы"
                )
            else:
                result_text = (
                    f"🎰 <b>Колесо Фортуны</b>\n\n"
                    f"Выигрыш: {format_diamonds(prize)}{lucky_text}\n"
                    f"Потеря: {format_diamonds(abs(net_win))}"
                )

    try:
        await msg.edit_text(result_text, parse_mode="HTML")
    except Exception:
        await update.message.reply_text(result_text, parse_mode="HTML")

    logger.info("Wheel spun", user_id=user_id, prize=prize, is_jackpot=is_jackpot)


def register_wheel_handlers(application):
    """Register wheel handlers."""
    application.add_handler(CommandHandler("wheel", wheel_command))
    logger.info("Wheel handlers registered")
