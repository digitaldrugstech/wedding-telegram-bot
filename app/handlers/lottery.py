"""Lottery command handlers."""

import random
from datetime import datetime

import structlog
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import Lottery, LotteryTicket, User
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds

logger = structlog.get_logger()

TICKET_PRICE = 100
WINNER_SHARE = 0.70  # 70% goes to winner, 30% is house cut (money sink)
MAX_TICKETS_PER_USER = 10


def get_or_create_active_lottery(db):
    """Get active lottery or create a new one."""
    lottery = db.query(Lottery).filter(Lottery.is_active.is_(True)).first()
    if not lottery:
        lottery = Lottery(jackpot=0, is_active=True)
        db.add(lottery)
        db.flush()
    return lottery


@require_registered
async def lottery_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show lottery info (/lottery)."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        lottery = get_or_create_active_lottery(db)
        lottery_id = lottery.id
        jackpot = lottery.jackpot
        total_tickets = len(lottery.tickets)
        user_tickets = (
            db.query(LotteryTicket)
            .filter(LotteryTicket.lottery_id == lottery_id, LotteryTicket.user_id == user_id)
            .count()
        )

    text = (
        "🎟 <b>Лотерея</b>\n\n"
        f"💰 Джекпот: {format_diamonds(jackpot)}\n"
        f"🎫 Билетов куплено: {total_tickets}\n"
        f"🎫 Твоих билетов: {user_tickets}/{MAX_TICKETS_PER_USER}\n\n"
        f"Цена билета: {format_diamonds(TICKET_PRICE)}\n"
        f"Приз: {int(WINNER_SHARE * 100)}% от джекпота\n\n"
        f"/buyticket — купить билет\n"
        f"/buyticket [кол-во] — купить несколько"
    )

    await update.message.reply_text(text, parse_mode="HTML")


@require_registered
async def buyticket_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buy lottery ticket(s) (/buyticket [count])."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    # Parse count
    count = 1
    if context.args:
        try:
            count = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Количество должно быть числом")
            return

    if count < 1:
        await update.message.reply_text("❌ Минимум 1 билет")
        return

    total_cost = TICKET_PRICE * count

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()

        if user.balance < total_cost:
            await update.message.reply_text(
                f"❌ Недостаточно алмазов\n\n"
                f"Нужно: {format_diamonds(total_cost)} ({count}x{format_diamonds(TICKET_PRICE)})\n"
                f"У тебя: {format_diamonds(user.balance)}"
            )
            return

        lottery = get_or_create_active_lottery(db)

        # Check ticket limit
        user_tickets = (
            db.query(LotteryTicket)
            .filter(LotteryTicket.lottery_id == lottery.id, LotteryTicket.user_id == user_id)
            .count()
        )

        if user_tickets + count > MAX_TICKETS_PER_USER:
            remaining = MAX_TICKETS_PER_USER - user_tickets
            await update.message.reply_text(
                f"❌ Лимит билетов: {MAX_TICKETS_PER_USER}\n\n"
                f"У тебя: {user_tickets}\n"
                f"Можно купить ещё: {remaining}"
            )
            return

        # Deduct payment
        user.balance -= total_cost

        # Add to jackpot
        lottery.jackpot += total_cost

        # Create tickets
        for _ in range(count):
            ticket = LotteryTicket(lottery_id=lottery.id, user_id=user_id)
            db.add(ticket)

        jackpot = lottery.jackpot
        total_user_tickets = user_tickets + count
        balance = user.balance

    text = (
        f"🎟 <b>Билет{'ы' if count > 1 else ''} куплен{'ы' if count > 1 else ''}!</b>\n\n"
        f"Куплено: {count} шт.\n"
        f"Потрачено: {format_diamonds(total_cost)}\n"
        f"Твоих билетов: {total_user_tickets}/{MAX_TICKETS_PER_USER}\n\n"
        f"💰 Джекпот: {format_diamonds(jackpot)}\n"
        f"💰 Баланс: {format_diamonds(balance)}"
    )

    await update.message.reply_text(text, parse_mode="HTML")
    logger.info("Lottery tickets bought", user_id=user_id, count=count, total_cost=total_cost, jackpot=jackpot)


async def draw_lottery(context: ContextTypes.DEFAULT_TYPE):
    """Draw lottery winner (called by scheduler)."""
    with get_db() as db:
        lottery = db.query(Lottery).filter(Lottery.is_active.is_(True)).first()

        if not lottery or not lottery.tickets:
            logger.info("Lottery draw skipped — no active lottery or no tickets")
            return

        if len(lottery.tickets) < 2:
            logger.info("Lottery draw skipped — not enough participants")
            return

        # Pick random ticket
        winning_ticket = random.choice(lottery.tickets)
        winner_id = winning_ticket.user_id

        # Calculate prize
        prize = int(lottery.jackpot * WINNER_SHARE)

        # Award prize
        winner = db.query(User).filter(User.telegram_id == winner_id).first()
        winner.balance += prize

        # Close lottery
        lottery.is_active = False
        lottery.ended_at = datetime.utcnow()
        lottery.winner_id = winner_id

        total_tickets = len(lottery.tickets)
        winner_username = winner.username or f"User{winner.telegram_id}"
        jackpot = lottery.jackpot

    # Announce in chat
    from app.constants import PRODUCTION_CHAT_ID

    text = (
        "🎉 <b>Розыгрыш лотереи!</b>\n\n"
        f"🏆 Победитель: @{winner_username}\n"
        f"💰 Приз: {format_diamonds(prize)}\n"
        f"🎫 Всего билетов: {total_tickets}\n"
        f"💰 Джекпот был: {format_diamonds(jackpot)}\n\n"
        f"🎟 Новая лотерея уже началась! /lottery"
    )

    try:
        await context.bot.send_message(chat_id=PRODUCTION_CHAT_ID, text=text, parse_mode="HTML")
    except Exception as e:
        logger.error("Failed to announce lottery", error=str(e))

    # Also notify winner privately
    try:
        await context.bot.send_message(
            chat_id=winner_id,
            text=f"🎉 <b>Ты выиграл лотерею!</b>\n\n💰 Приз: {format_diamonds(prize)}",
            parse_mode="HTML",
        )
    except Exception:
        pass

    logger.info("Lottery drawn", winner_id=winner_id, prize=prize, jackpot=jackpot, tickets=total_tickets)


def register_lottery_handlers(application):
    """Register lottery handlers."""
    application.add_handler(CommandHandler("lottery", lottery_command))
    application.add_handler(CommandHandler("buyticket", buyticket_command))
    logger.info("Lottery handlers registered")
