"""Coinflip command handler — simple 50/50 bet with house edge."""

import random
from datetime import datetime, timedelta

import structlog
from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import CasinoGame, Cooldown, User
from app.handlers.quest import update_quest_progress
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds
from app.utils.keyboards import casino_after_game_keyboard

logger = structlog.get_logger()

COINFLIP_COOLDOWN_SECONDS = 15
COINFLIP_MIN_BET = 10
COINFLIP_MAX_BET = 2000
WIN_MULTIPLIER = 1.9  # 50% chance * 1.9 = 0.95 EV → 5% house edge
VIP_COINFLIP_MAX_BET = 4000  # Premium users get higher limit


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

    # VIP players get higher max bet
    from app.handlers.premium import is_vip

    effective_max = VIP_COINFLIP_MAX_BET if is_vip(user_id) else COINFLIP_MAX_BET
    if bet < COINFLIP_MIN_BET or bet > effective_max:
        await update.message.reply_text(
            f"❌ Ставка: {format_diamonds(COINFLIP_MIN_BET)} - {format_diamonds(effective_max)}"
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
            # Lucky charm bonus (+5%)
            from app.handlers.premium import has_active_boost

            if has_active_boost(user_id, "lucky_charm", db=db):
                payout += int(payout * 0.10)
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

    await update.message.reply_text(
        text, parse_mode="HTML", reply_markup=casino_after_game_keyboard("coinflip", user_id, bet=bet)
    )

    try:
        update_quest_progress(user_id, "casino")
    except Exception:
        pass

    logger.info("Coinflip", user_id=user_id, bet=bet, win=win, payout=payout)


def _play_coinflip(user_id: int, bet: int):
    """Core coinflip logic. Returns (text, bet) or (error_text, None)."""
    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user or user.is_banned:
            return "Доступ запрещён", None

        # VIP max bet check
        from app.handlers.premium import is_vip

        effective_max = VIP_COINFLIP_MAX_BET if is_vip(user_id, db=db) else COINFLIP_MAX_BET
        if bet > effective_max:
            return f"❌ Макс. ставка: {format_diamonds(effective_max)}", None

        if user.balance < bet:
            return (
                f"❌ Недостаточно алмазов\n\nНужно: {format_diamonds(bet)}\nУ тебя: {format_diamonds(user.balance)}",
                None,
            )

        cooldown = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "coinflip").first()
        if cooldown and cooldown.expires_at > datetime.utcnow():
            remaining = cooldown.expires_at - datetime.utcnow()
            return f"⏰ Следующий бросок через {int(remaining.total_seconds())}с", None

        # Deduct bet
        user.balance -= bet

        # Flip
        win = random.random() < 0.5

        if win:
            payout = int(bet * WIN_MULTIPLIER)
            from app.handlers.premium import has_active_boost

            if has_active_boost(user_id, "lucky_charm", db=db):
                payout += int(payout * 0.10)
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

    try:
        update_quest_progress(user_id, "casino")
    except Exception:
        pass

    logger.info("Coinflip", user_id=user_id, bet=bet, win=win, payout=payout)
    return text, bet


async def coinflip_bet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle coinflip bet from button — cbet:coinflip:{amount}:{user_id}."""
    query = update.callback_query
    if not update.effective_user:
        return

    parts = query.data.split(":")
    if len(parts) != 4:
        return

    amount_str = parts[2]
    owner_id = int(parts[3])

    if update.effective_user.id != owner_id:
        await query.answer("Эта кнопка не для тебя", show_alert=True)
        return

    user_id = update.effective_user.id

    # Parse bet amount
    if amount_str == "all":
        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == user_id).first()
            if not user:
                await query.answer("Доступ запрещён", show_alert=True)
                return
            from app.handlers.premium import is_vip

            effective_max = VIP_COINFLIP_MAX_BET if is_vip(user_id, db=db) else COINFLIP_MAX_BET
            bet = min(user.balance, effective_max)
            if bet < COINFLIP_MIN_BET:
                await query.answer(f"Недостаточно алмазов (мин. {COINFLIP_MIN_BET})", show_alert=True)
                return
    else:
        try:
            bet = int(amount_str)
        except ValueError:
            return

    if bet < COINFLIP_MIN_BET or bet > COINFLIP_MAX_BET:
        await query.answer(f"Ставка: {COINFLIP_MIN_BET}-{COINFLIP_MAX_BET}", show_alert=True)
        return

    text, actual_bet = _play_coinflip(user_id, bet)
    if actual_bet is None:
        # Error — show as alert
        await query.answer(text, show_alert=True)
        return

    await query.answer()

    # Send result as new message (can't edit into a game result well)
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=casino_after_game_keyboard("coinflip", user_id, bet=actual_bet),
    )


def register_coinflip_handlers(application):
    """Register coinflip handlers."""
    application.add_handler(CommandHandler(["coinflip", "cf"], coinflip_command))
    application.add_handler(CallbackQueryHandler(coinflip_bet_callback, pattern=r"^cbet:coinflip:"))
    logger.info("Coinflip handlers registered")
