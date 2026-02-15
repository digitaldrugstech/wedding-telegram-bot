"""Bounty handler — place bounties on other players."""

import html
from datetime import datetime

import structlog
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import Bounty, User
from app.handlers.quest import update_quest_progress
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds, format_word

logger = structlog.get_logger()

BOUNTY_MIN_AMOUNT = 200
BOUNTY_FEE_RATE = 10  # 10% fee (money sink)
MAX_ACTIVE_BOUNTIES_PER_USER = 3


def get_target_bounties(db, target_id: int) -> int:
    """Get total active bounty amount on a target. Used by rob.py and duel.py."""
    bounties = db.query(Bounty).filter(Bounty.target_id == target_id, Bounty.is_active.is_(True)).all()
    return sum(b.amount for b in bounties)


def collect_bounties(db, target_id: int, collector_id: int) -> int:
    """Collect all bounties on a target. Returns total collected. Used by rob.py and duel.py."""
    bounties = db.query(Bounty).filter(Bounty.target_id == target_id, Bounty.is_active.is_(True)).all()

    total = 0
    now = datetime.utcnow()
    for bounty in bounties:
        bounty.is_active = False
        bounty.collected_by_id = collector_id
        bounty.collected_at = now
        total += bounty.amount

    return total


@require_registered
async def bounty_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /bounty — place a bounty on someone."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    # No args — show help + active bounties
    if not context.args or len(context.args) < 2:
        with get_db() as db:
            # Show user's placed bounties
            my_bounties = db.query(Bounty).filter(Bounty.placer_id == user_id, Bounty.is_active.is_(True)).all()

            text = (
                "🎯 <b>Система наград</b>\n\n"
                "Назначь награду за голову игрока!\n"
                "Любой, кто ограбит или победит цель в дуэли, получит награду.\n\n"
                f"Минимум: {format_diamonds(BOUNTY_MIN_AMOUNT)}\n"
                f"Комиссия: {BOUNTY_FEE_RATE}%\n"
                f"Лимит: {MAX_ACTIVE_BOUNTIES_PER_USER} активных наград\n\n"
            )

            if my_bounties:
                text += "<b>Твои активные награды:</b>\n"
                for b in my_bounties:
                    target = db.query(User).filter(User.telegram_id == b.target_id).first()
                    display = f"@{html.escape(target.username)}" if target and target.username else f"ID {b.target_id}"
                    text += f"🎯 {display} — {format_diamonds(b.amount)}\n"
                text += "\n/bounty cancel — отменить награду\n\n"

            text += "Использование:\n/bounty @username [сумма]"

        await update.message.reply_text(text, parse_mode="HTML")
        return

    # Handle cancel
    if context.args[0].lower() == "cancel":
        await cancel_bounty(update, user_id)
        return

    # Place bounty
    username = context.args[0].lstrip("@")
    try:
        amount = int(context.args[1])
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Укажи сумму\n\n/bounty @username [сумма]")
        return

    if amount < BOUNTY_MIN_AMOUNT:
        await update.message.reply_text(f"❌ Минимальная награда: {format_diamonds(BOUNTY_MIN_AMOUNT)}")
        return

    fee = int(amount * BOUNTY_FEE_RATE / 100)
    total_cost = amount + fee

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            return

        # Check balance
        if user.balance < total_cost:
            await update.message.reply_text(
                f"❌ Недостаточно алмазов\n\n"
                f"Награда: {format_diamonds(amount)}\n"
                f"Комиссия: {format_diamonds(fee)}\n"
                f"Итого: {format_diamonds(total_cost)}\n\n"
                f"💰 У тебя: {format_diamonds(user.balance)}"
            )
            return

        # Find target
        target = db.query(User).filter(User.username == username).first()
        if not target:
            await update.message.reply_text(f"❌ Игрок @{html.escape(username)} не найден")
            return

        if target.telegram_id == user_id:
            await update.message.reply_text("❌ Нельзя назначить награду на себя")
            return

        # Check active bounty limit
        active_count = db.query(Bounty).filter(Bounty.placer_id == user_id, Bounty.is_active.is_(True)).count()
        if active_count >= MAX_ACTIVE_BOUNTIES_PER_USER:
            await update.message.reply_text(
                f"❌ Максимум {MAX_ACTIVE_BOUNTIES_PER_USER} активных наград\n\n/bounty cancel — отменить одну"
            )
            return

        # Deduct cost
        user.balance -= total_cost

        # Create bounty
        bounty = Bounty(
            placer_id=user_id,
            target_id=target.telegram_id,
            amount=amount,
            is_active=True,
        )
        db.add(bounty)

        target_display = f"@{html.escape(target.username)}" if target.username else f"ID {target.telegram_id}"
        balance = user.balance

        # Get total bounty on target (new bounty already in session, no need to add again)
        total_on_target = get_target_bounties(db, target.telegram_id)

    await update.message.reply_text(
        f"🎯 <b>Награда назначена!</b>\n\n"
        f"Цель: {target_display}\n"
        f"Награда: {format_diamonds(amount)}\n"
        f"Комиссия: {format_diamonds(fee)}\n\n"
        f"Общая награда за {target_display}: {format_diamonds(total_on_target)}\n\n"
        f"💰 Баланс: {format_diamonds(balance)}",
        parse_mode="HTML",
    )

    try:
        update_quest_progress(user_id, "bounty")
    except Exception:
        pass

    logger.info("Bounty placed", placer_id=user_id, target=username, amount=amount, fee=fee)


async def cancel_bounty(update: Update, user_id: int):
    """Cancel the user's most recent active bounty (no refund of fee)."""
    with get_db() as db:
        bounty = (
            db.query(Bounty)
            .filter(Bounty.placer_id == user_id, Bounty.is_active.is_(True))
            .order_by(Bounty.created_at.desc())
            .first()
        )

        if not bounty:
            await update.message.reply_text("❌ У тебя нет активных наград")
            return

        # Refund the bounty amount (fee is not refunded — money sink)
        user = db.query(User).filter(User.telegram_id == user_id).first()
        user.balance += bounty.amount
        bounty.is_active = False

        target = db.query(User).filter(User.telegram_id == bounty.target_id).first()
        target_display = f"@{html.escape(target.username)}" if target and target.username else f"ID {bounty.target_id}"
        refund = bounty.amount
        balance = user.balance

    await update.message.reply_text(
        f"✅ <b>Награда отменена</b>\n\n"
        f"Цель: {target_display}\n"
        f"Возврат: {format_diamonds(refund)}\n"
        f"(комиссия не возвращается)\n\n"
        f"💰 Баланс: {format_diamonds(balance)}",
        parse_mode="HTML",
    )

    logger.info("Bounty cancelled", placer_id=user_id, refund=refund)


@require_registered
async def bounties_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /bounties — show all active bounties."""
    if not update.effective_user or not update.message:
        return

    with get_db() as db:
        bounties = db.query(Bounty).filter(Bounty.is_active.is_(True)).all()

        if not bounties:
            await update.message.reply_text("🎯 Нет активных наград\n\n/bounty @user [сумма] — назначить")
            return

        # Aggregate by target
        target_totals = {}
        for b in bounties:
            if b.target_id not in target_totals:
                target = db.query(User).filter(User.telegram_id == b.target_id).first()
                display = f"@{html.escape(target.username)}" if target and target.username else f"ID {b.target_id}"
                target_totals[b.target_id] = {"name": display, "amount": 0, "count": 0}
            target_totals[b.target_id]["amount"] += b.amount
            target_totals[b.target_id]["count"] += 1

        # Sort by total amount descending
        sorted_targets = sorted(target_totals.values(), key=lambda x: x["amount"], reverse=True)

        text = "🎯 <b>Доска разыскиваемых</b>\n\n"
        for i, t in enumerate(sorted_targets[:10], 1):
            text += f"{i}. {t['name']} — {format_diamonds(t['amount'])}"
            if t["count"] > 1:
                text += f" ({format_word(t['count'], 'награда', 'награды', 'наград')})"
            text += "\n"

        text += (
            "\nОграби (/rob) или победи в дуэли (/duel)\n"
            "разыскиваемого, чтобы собрать награду!\n\n"
            "/bounty @user [сумма] — назначить награду"
        )

    await update.message.reply_text(text, parse_mode="HTML")


def register_bounty_handlers(application):
    """Register bounty handlers."""
    application.add_handler(CommandHandler("bounty", bounty_command))
    application.add_handler(CommandHandler("bounties", bounties_command))
    logger.info("Bounty handlers registered")
