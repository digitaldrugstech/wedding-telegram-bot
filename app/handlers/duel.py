"""Duel command handlers."""

import random
from datetime import datetime, timedelta

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import Cooldown, Duel, User
from app.utils.decorators import button_owner_only, require_registered
from app.utils.formatters import format_diamonds
from app.utils.telegram_helpers import safe_edit_message

logger = structlog.get_logger()

DUEL_COOLDOWN_MINUTES = 30


@require_registered
async def duel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Challenge someone to a duel (/duel @user amount or reply with /duel amount)."""
    user_id = update.effective_user.id
    args = context.args

    # Check if replying to someone
    opponent_id = None
    opponent_username = None

    if update.message.reply_to_message:
        opponent_id = update.message.reply_to_message.from_user.id
        opponent_username = (
            update.message.reply_to_message.from_user.username or update.message.reply_to_message.from_user.first_name
        )

        if len(args) < 1:
            await update.message.reply_text("❌ Укажи ставку\n\nИспользуй: /duel [сумма]")
            return

        try:
            bet_amount = int(args[0])
        except ValueError:
            await update.message.reply_text("❌ Неверная сумма")
            return

    else:
        # Parse @username and amount
        if len(args) < 2:
            await update.message.reply_text(
                "❌ Неверный формат\n\n"
                "Используй:\n"
                "/duel @username сумма\n"
                "или зареплай на сообщение: /duel сумма"
            )
            return

        # Try to find user by username mention
        username_arg = args[0].replace("@", "")
        try:
            bet_amount = int(args[1])
        except ValueError:
            await update.message.reply_text("❌ Неверная сумма")
            return

        # Find opponent by username
        with get_db() as db:
            opponent = db.query(User).filter(User.username == username_arg).first()
            if not opponent:
                await update.message.reply_text("❌ Пользователь не найден")
                return

            opponent_id = opponent.telegram_id
            opponent_username = opponent.username

    # Validate
    if opponent_id == user_id:
        await update.message.reply_text("❌ Нельзя вызвать себя на дуэль")
        return

    if bet_amount <= 0:
        await update.message.reply_text("❌ Ставка должна быть больше 0")
        return

    # Check cooldown
    with get_db() as db:
        cooldown = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "duel").first()

        if cooldown and cooldown.expires_at > datetime.utcnow():
            remaining = cooldown.expires_at - datetime.utcnow()
            minutes = int(remaining.total_seconds() / 60)
            await update.message.reply_text(f"⏰ Можешь вызвать на дуэль через {minutes}м")
            return

        # Check balances
        challenger = db.query(User).filter(User.telegram_id == user_id).first()
        opponent = db.query(User).filter(User.telegram_id == opponent_id).first()

        if not opponent:
            await update.message.reply_text("❌ Оппонент не зарегистрирован")
            return

        if challenger.balance < bet_amount:
            await update.message.reply_text(
                f"❌ Недостаточно алмазов\n\n"
                f"Нужно: {format_diamonds(bet_amount)}\n"
                f"У тебя: {format_diamonds(challenger.balance)}"
            )
            return

        if opponent.balance < bet_amount:
            await update.message.reply_text(f"❌ У оппонента недостаточно алмазов для этой ставки")
            return

        # Check for active duel between these users
        active_duel = (
            db.query(Duel)
            .filter(
                Duel.is_active.is_(True),
                (
                    (Duel.challenger_id == user_id) & (Duel.opponent_id == opponent_id)
                    | (Duel.challenger_id == opponent_id) & (Duel.opponent_id == user_id)
                ),
            )
            .first()
        )

        if active_duel:
            await update.message.reply_text("❌ У тебя уже есть активная дуэль с этим игроком")
            return

        # Create duel
        duel = Duel(
            challenger_id=user_id,
            opponent_id=opponent_id,
            bet_amount=bet_amount,
            is_active=True,
            is_accepted=False,
        )
        db.add(duel)
        db.flush()  # Get duel ID

        duel_id = duel.id

    # Send challenge
    keyboard = [
        [
            InlineKeyboardButton("✅ Принять", callback_data=f"duel:accept:{duel_id}:{opponent_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"duel:decline:{duel_id}:{opponent_id}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    challenger_name = update.effective_user.username or update.effective_user.first_name
    await update.message.reply_text(
        f"⚔️ <b>Вызов на дуэль!</b>\n\n"
        f"{challenger_name} вызывает @{opponent_username} на дуэль\n\n"
        f"Ставка: {format_diamonds(bet_amount)}\n"
        f"Победитель забирает всё\n\n"
        f"@{opponent_username}, принимаешь вызов?",
        reply_markup=reply_markup,
        parse_mode="HTML",
    )


@button_owner_only
async def duel_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Accept duel challenge."""
    query = update.callback_query
    await query.answer()

    duel_id = int(query.data.split(":")[2])
    opponent_id = update.effective_user.id

    with get_db() as db:
        duel = db.query(Duel).filter(Duel.id == duel_id, Duel.is_active.is_(True)).first()

        if not duel:
            await safe_edit_message(query, "❌ Дуэль не найдена или уже завершена")
            return

        if duel.opponent_id != opponent_id:
            await query.answer("⚠️ Эта дуэль не для тебя", show_alert=True)
            return

        # Check balances
        challenger = db.query(User).filter(User.telegram_id == duel.challenger_id).first()
        opponent = db.query(User).filter(User.telegram_id == duel.opponent_id).first()

        if challenger.balance < duel.bet_amount:
            await safe_edit_message(query, "❌ У вызывающего недостаточно алмазов")
            duel.is_active = False
            return

        if opponent.balance < duel.bet_amount:
            await safe_edit_message(query, "❌ У тебя недостаточно алмазов")
            duel.is_active = False
            return

        # Deduct bets
        challenger.balance -= duel.bet_amount
        opponent.balance -= duel.bet_amount

        # 50/50 random winner
        winner_id = random.choice([duel.challenger_id, duel.opponent_id])
        winner = db.query(User).filter(User.telegram_id == winner_id).first()

        # Award prize (both bets)
        prize = duel.bet_amount * 2
        winner.balance += prize

        # Update duel
        duel.is_accepted = True
        duel.is_active = False
        duel.winner_id = winner_id
        duel.completed_at = datetime.utcnow()

        # Set cooldown for both players
        for player_id in [duel.challenger_id, duel.opponent_id]:
            cooldown = db.query(Cooldown).filter(Cooldown.user_id == player_id, Cooldown.action == "duel").first()
            expires_at = datetime.utcnow() + timedelta(minutes=DUEL_COOLDOWN_MINUTES)

            if cooldown:
                cooldown.expires_at = expires_at
            else:
                cooldown = Cooldown(user_id=player_id, action="duel", expires_at=expires_at)
                db.add(cooldown)

        logger.info(
            "Duel completed",
            duel_id=duel_id,
            winner_id=winner_id,
            bet=duel.bet_amount,
        )

        # Announce winner (must stay inside session to access ORM objects)
        winner_name = winner.username or f"ID {winner_id}"
        loser_id = duel.challenger_id if winner_id == duel.opponent_id else duel.opponent_id
        loser = db.query(User).filter(User.telegram_id == loser_id).first()
        loser_name = loser.username or f"ID {loser_id}"

    await safe_edit_message(
        query,
        f"⚔️ <b>Дуэль завершена!</b>\n\n"
        f"Победитель: @{winner_name}\n"
        f"Проигравший: @{loser_name}\n\n"
        f"Выигрыш: {format_diamonds(prize)}",
    )


@button_owner_only
async def duel_decline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Decline duel challenge."""
    query = update.callback_query
    await query.answer()

    duel_id = int(query.data.split(":")[2])

    with get_db() as db:
        duel = db.query(Duel).filter(Duel.id == duel_id).first()

        if not duel:
            await safe_edit_message(query, "❌ Дуэль не найдена")
            return

        duel.is_active = False

    await safe_edit_message(query, "❌ <b>Дуэль отклонена</b>")


def register_duel_handlers(application):
    """Register duel handlers."""
    application.add_handler(CommandHandler("duel", duel_command))
    application.add_handler(CallbackQueryHandler(duel_accept, pattern=r"^duel:accept:"))
    application.add_handler(CallbackQueryHandler(duel_decline, pattern=r"^duel:decline:"))
    logger.info("Duel handlers registered")
