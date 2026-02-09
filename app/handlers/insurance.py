"""Insurance command handler — weekly protection from robbery."""

from datetime import datetime, timedelta

import structlog
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import Insurance, User
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds

logger = structlog.get_logger()

INSURANCE_COST = 500
INSURANCE_DURATION_DAYS = 7


def has_active_insurance(db, user_id: int) -> bool:
    """Check if user has active insurance."""
    insurance = db.query(Insurance).filter(Insurance.user_id == user_id, Insurance.is_active.is_(True)).first()
    if not insurance:
        return False
    if insurance.expires_at <= datetime.utcnow():
        insurance.is_active = False
        return False
    return True


@require_registered
async def insurance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /insurance command."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    args = context.args

    if args and args[0].lower() == "buy":
        await buy_insurance(update, user_id)
        return

    # Show insurance status
    with get_db() as db:
        insurance = db.query(Insurance).filter(Insurance.user_id == user_id, Insurance.is_active.is_(True)).first()

        if insurance and insurance.expires_at > datetime.utcnow():
            remaining = insurance.expires_at - datetime.utcnow()
            days = remaining.days
            hours = int((remaining.total_seconds() % 86400) // 3600)

            time_parts = []
            if days > 0:
                time_parts.append(f"{days}д")
            if hours > 0:
                time_parts.append(f"{hours}ч")

            text = (
                "🛡 <b>Страховка активна</b>\n\n"
                f"Осталось: {' '.join(time_parts)}\n"
                f"Истекает: {insurance.expires_at.strftime('%d.%m.%Y %H:%M')} UTC\n\n"
                "Защита от /rob"
            )
        else:
            if insurance:
                insurance.is_active = False

            text = (
                "🛡 <b>Страховка</b>\n\n"
                f"Стоимость: {format_diamonds(INSURANCE_COST)} / неделя\n\n"
                "Что даёт:\n"
                "• Защита от ограблений (/rob)\n"
                "• Действует 7 дней\n\n"
                "/insurance buy — купить страховку"
            )

    await update.message.reply_text(text, parse_mode="HTML")


async def buy_insurance(update: Update, user_id: int):
    """Buy insurance."""
    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            return

        # Check if already insured (unique constraint: one record per user)
        existing = db.query(Insurance).filter(Insurance.user_id == user_id).first()
        if existing and existing.is_active and existing.expires_at > datetime.utcnow():
            remaining = existing.expires_at - datetime.utcnow()
            await update.message.reply_text(
                f"❌ У тебя уже есть страховка (ещё {remaining.days}д)\n\n" "Дождись окончания текущей"
            )
            return

        # Check balance
        if user.balance < INSURANCE_COST:
            await update.message.reply_text(
                f"❌ Недостаточно алмазов\n\n"
                f"Нужно: {format_diamonds(INSURANCE_COST)}\n"
                f"У тебя: {format_diamonds(user.balance)}"
            )
            return

        # Buy insurance — update existing or create new (unique constraint on user_id)
        user.balance -= INSURANCE_COST
        expires_at = datetime.utcnow() + timedelta(days=INSURANCE_DURATION_DAYS)

        if existing:
            existing.is_active = True
            existing.purchased_at = datetime.utcnow()
            existing.expires_at = expires_at
        else:
            db.add(Insurance(user_id=user_id, is_active=True, expires_at=expires_at))

        balance = user.balance

    await update.message.reply_text(
        "🛡 <b>Страховка куплена!</b>\n\n"
        f"Действует {INSURANCE_DURATION_DAYS} дней\n"
        f"Истекает: {expires_at.strftime('%d.%m.%Y %H:%M')} UTC\n\n"
        "Теперь тебя нельзя ограбить\n\n"
        f"💰 Потрачено: {format_diamonds(INSURANCE_COST)}\n"
        f"💰 Баланс: {format_diamonds(balance)}",
        parse_mode="HTML",
    )

    logger.info("Insurance purchased", user_id=user_id, expires_at=expires_at.isoformat())


def register_insurance_handlers(application):
    """Register insurance handlers."""
    application.add_handler(CommandHandler("insurance", insurance_command))
    logger.info("Insurance handlers registered")
