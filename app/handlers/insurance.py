"""Insurance command handler — weekly protection from robbery."""

from datetime import datetime, timedelta

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import Insurance, User
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds, format_word
from app.utils.telegram_helpers import delete_command_and_reply, safe_edit_message

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


def _insurance_status_text(db, user_id: int):
    """Build insurance status text and whether user can buy. Returns (text, can_buy)."""
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
        return text, False
    else:
        if insurance:
            insurance.is_active = False

        text = (
            "🛡 <b>Страховка</b>\n\n"
            f"Стоимость: {format_diamonds(INSURANCE_COST)} / неделя\n\n"
            "Что даёт:\n"
            "• Защита от ограблений (/rob)\n"
            "• Действует 7 дней"
        )
        return text, True


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

    with get_db() as db:
        text, can_buy = _insurance_status_text(db, user_id)

    keyboard = None
    if can_buy:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        f"🛡 Купить ({format_diamonds(INSURANCE_COST)})", callback_data=f"insurance:buy:{user_id}"
                    )
                ]
            ]
        )

    reply = await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
    await delete_command_and_reply(update, reply, context, delay=90)


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
        f"Действует {format_word(INSURANCE_DURATION_DAYS, 'день', 'дня', 'дней')}\n"
        f"Истекает: {expires_at.strftime('%d.%m.%Y %H:%M')} UTC\n\n"
        "Теперь тебя нельзя ограбить\n\n"
        f"💰 Потрачено: {format_diamonds(INSURANCE_COST)}\n"
        f"💰 Баланс: {format_diamonds(balance)}",
        parse_mode="HTML",
    )

    logger.info("Insurance purchased", user_id=user_id, expires_at=expires_at.isoformat())


async def insurance_buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle insurance buy button — insurance:buy:{user_id}."""
    query = update.callback_query
    if not query or not update.effective_user:
        return

    parts = query.data.split(":")
    if len(parts) != 3:
        return

    owner_id = int(parts[2])
    user_id = update.effective_user.id

    if user_id != owner_id:
        await query.answer("Эта кнопка не для тебя", show_alert=True)
        return

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user or user.is_banned:
            await query.answer("Доступ запрещён", show_alert=True)
            return

        existing = db.query(Insurance).filter(Insurance.user_id == user_id).first()
        if existing and existing.is_active and existing.expires_at > datetime.utcnow():
            await query.answer("У тебя уже есть страховка", show_alert=True)
            return

        if user.balance < INSURANCE_COST:
            await query.answer(f"Недостаточно алмазов (нужно {INSURANCE_COST})", show_alert=True)
            return

        user.balance -= INSURANCE_COST
        expires_at = datetime.utcnow() + timedelta(days=INSURANCE_DURATION_DAYS)

        if existing:
            existing.is_active = True
            existing.purchased_at = datetime.utcnow()
            existing.expires_at = expires_at
        else:
            db.add(Insurance(user_id=user_id, is_active=True, expires_at=expires_at))

        balance = user.balance

    await query.answer()
    await safe_edit_message(
        query,
        "🛡 <b>Страховка куплена!</b>\n\n"
        f"Действует {format_word(INSURANCE_DURATION_DAYS, 'день', 'дня', 'дней')}\n"
        f"Истекает: {expires_at.strftime('%d.%m.%Y %H:%M')} UTC\n\n"
        "Теперь тебя нельзя ограбить\n\n"
        f"💰 Баланс: {format_diamonds(balance)}",
    )

    logger.info("Insurance purchased via button", user_id=user_id, expires_at=expires_at.isoformat())


def register_insurance_handlers(application):
    """Register insurance handlers."""
    application.add_handler(CommandHandler("insurance", insurance_command))
    application.add_handler(CallbackQueryHandler(insurance_buy_callback, pattern=r"^insurance:buy:"))
    logger.info("Insurance handlers registered")
