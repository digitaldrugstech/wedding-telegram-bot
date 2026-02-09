"""Coinflip command handler — simple 50/50 bet with house edge."""

import random
from datetime import datetime, timedelta

import structlog
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import CasinoGame, Cooldown, User
from app.handlers.quest import update_quest_progress
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds
from app.utils.keyboards import casino_after_game_keyboard

logger = structlog.get_logger()

COINFLIP_COOLDOWN_SECONDS = 15
COINFLIP_MIN_BET = 10
COINFLIP_MAX_BET = 5000
WIN_MULTIPLIER = 1.9  # 50% chance * 1.9 = 0.95 EV → 5% house edge


@require_registered
async def coinflip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /coinflip [bet] or /cf [bet]."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text(
            "🪙 <b>Монетка</b>\n\n"
            f"/coinflip [ставка] — орёл или решка\n"
            f"/cf [ставка] — короткая команда\n\n"
            f"Лимиты: {format_diamonds(COINFLIP_MIN_BET)} - {format_diamonds(COINFLIP_MAX_BET)}\n"
            f"Выигрыш: x{WIN_MULTIPLIER}\n"
            f"Шанс: 50/50",
            parse_mode="HTML",
        )
        return

    try:
        bet = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Ставка должна быть числом")
        return

    if bet < COINFLIP_MIN_BET or bet > COINFLIP_MAX_BET:
        await update.message.reply_text(
            f"❌ Ставка: {format_diamonds(COINFLIP_MIN_BET)} - {format_diamonds(COINFLIP_MAX_BET)}"
        )
        return

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()

        if user.balance < bet:
            await update.message.reply_text(
                f"❌ Недостаточно алмазов\n\nНужно: {format_diamonds(bet)}\nУ тебя: {format_diamonds(user.balance)}"
            )
            return

        cooldown = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "coinflip").first()
        if cooldown and cooldown.expires_at > datetime.utcnow():
            remaining = cooldown.expires_at - datetime.utcnow()
            await update.message.reply_text(f"⏰ Следующий бросок через {int(remaining.total_seconds())}с")
            return

        # Deduct bet
        user.balance -= bet

        # Flip
        win = random.random() < 0.5

        if win:
            payout = int(bet * WIN_MULTIPLIER)
            # Lucky charm bonus (+15%)
            from app.handlers.premium import has_active_boost

            if has_active_boost(user_id, "lucky_charm", db=db):
                payout += int(payout * 0.15)
            user.balance += payout
            result_type = "win"
        else:
            payout = 0
            result_type = "loss"

        # Set cooldown
        expires_at = datetime.utcnow() + timedelta(seconds=COINFLIP_COOLDOWN_SECONDS)
        if cooldown:
            cooldown.expires_at = expires_at
        else:
            db.add(Cooldown(user_id=user_id, action="coinflip", expires_at=expires_at))

        # Record game
        db.add(CasinoGame(user_id=user_id, bet_amount=bet, result=result_type, payout=payout))

        balance = user.balance

    # Build message
    side = "🦅 Орёл" if win else "🪙 Решка"

    if win:
        profit = payout - bet
        text = (
            f"🪙 <b>Монетка</b>\n\n"
            f"{side}!\n\n"
            f"🎉 Выигрыш: {format_diamonds(payout)} (+{format_diamonds(profit)})\n"
            f"💰 Баланс: {format_diamonds(balance)}"
        )
    else:
        # Lucky charm nudge on loss (throttled)
        from app.handlers.premium import build_premium_nudge, has_active_boost as _cf_has_boost

        nudge = ""
        if not _cf_has_boost(user_id, "lucky_charm"):
            nudge = build_premium_nudge("casino_loss", user_id)
        text = (
            f"🪙 <b>Монетка</b>\n\n"
            f"{side}!\n\n"
            f"💸 Проигрыш: {format_diamonds(bet)}\n"
            f"💰 Баланс: {format_diamonds(balance)}{nudge}"
        )

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=casino_after_game_keyboard("coinflip", user_id))

    try:
        update_quest_progress(user_id, "casino")
    except Exception:
        pass

    logger.info("Coinflip", user_id=user_id, bet=bet, win=win, payout=payout)


def register_coinflip_handlers(application):
    """Register coinflip handlers."""
    application.add_handler(CommandHandler(["coinflip", "cf"], coinflip_command))
    logger.info("Coinflip handlers registered")
