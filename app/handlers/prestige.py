"""Prestige system — ultimate money sink."""

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import User
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds
from app.utils.telegram_helpers import safe_edit_message

logger = structlog.get_logger()

PRESTIGE_COST = 50000  # Minimum balance to prestige
MAX_PRESTIGE = 10
PRESTIGE_BONUS_PER_LEVEL = 5  # +5% income per prestige level

PRESTIGE_STARS = {
    0: "",
    1: "⭐",
    2: "⭐⭐",
    3: "⭐⭐⭐",
    4: "🌟",
    5: "🌟🌟",
    6: "🌟🌟🌟",
    7: "💫",
    8: "💫💫",
    9: "💫💫💫",
    10: "✨🏆✨",
}


def get_prestige_display(level: int) -> str:
    """Get display string for prestige level."""
    return PRESTIGE_STARS.get(level, f"P{level}")


@require_registered
async def prestige_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /prestige command."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        current_prestige = user.prestige_level or 0
        balance = user.balance

    if current_prestige >= MAX_PRESTIGE:
        await update.message.reply_text(
            f"✨🏆✨ <b>Максимальный престиж!</b>\n\n"
            f"Уровень: {current_prestige}/{MAX_PRESTIGE}\n"
            f"Бонус к доходу: +{current_prestige * PRESTIGE_BONUS_PER_LEVEL}%\n\n"
            f"Ты достиг вершины!",
            parse_mode="HTML",
        )
        return

    next_level = current_prestige + 1
    next_bonus = next_level * PRESTIGE_BONUS_PER_LEVEL
    current_bonus = current_prestige * PRESTIGE_BONUS_PER_LEVEL

    text = (
        f"🔄 <b>Престиж</b>\n\n"
        f"Текущий: {get_prestige_display(current_prestige)} ({current_prestige}/{MAX_PRESTIGE})\n"
        f"Бонус к доходу: +{current_bonus}%\n\n"
        f"<b>Следующий уровень:</b>\n"
        f"{get_prestige_display(next_level)} → +{next_bonus}% к доходу\n\n"
        f"💰 Стоимость: {format_diamonds(PRESTIGE_COST)}\n"
        f"⚠️ Баланс обнулится!\n\n"
        f"Твой баланс: {format_diamonds(balance)}"
    )

    if balance >= PRESTIGE_COST:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Повысить престиж", callback_data=f"prestige:confirm:{user_id}"),
                    InlineKeyboardButton("❌ Отмена", callback_data=f"prestige:cancel:{user_id}"),
                ]
            ]
        )
    else:
        keyboard = None
        text += f"\n\n❌ Нужно минимум {format_diamonds(PRESTIGE_COST)}"

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)


async def prestige_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle prestige confirmation."""
    query = update.callback_query
    if not query or not update.effective_user:
        return

    parts = query.data.split(":")
    if len(parts) != 3:
        return

    action = parts[1]
    owner_id = int(parts[2])
    user_id = update.effective_user.id

    if user_id != owner_id:
        await query.answer("⚠️ Эта кнопка не для тебя", show_alert=True)
        return

    await query.answer()

    if action == "cancel":
        await safe_edit_message(query, "❌ Престиж отменён")
        return

    if action == "confirm":
        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == user_id).first()
            current_prestige = user.prestige_level or 0

            if current_prestige >= MAX_PRESTIGE:
                await safe_edit_message(query, "❌ Уже максимальный престиж")
                return

            if user.balance < PRESTIGE_COST:
                await safe_edit_message(
                    query,
                    f"❌ Недостаточно алмазов\n\nНужно: {format_diamonds(PRESTIGE_COST)}\n"
                    f"У тебя: {format_diamonds(user.balance)}",
                )
                return

            # Apply prestige
            old_balance = user.balance
            user.balance = 0
            user.prestige_level = current_prestige + 1
            new_prestige = user.prestige_level
            new_bonus = new_prestige * PRESTIGE_BONUS_PER_LEVEL

        text = (
            f"🔄 <b>ПРЕСТИЖ!</b>\n\n"
            f"{get_prestige_display(new_prestige)} Уровень {new_prestige}/{MAX_PRESTIGE}\n\n"
            f"Потрачено: {format_diamonds(old_balance)} (весь баланс)\n"
            f"Бонус к доходу: <b>+{new_bonus}%</b>\n\n"
            f"Все заработки теперь увеличены на {new_bonus}%!"
        )

        await safe_edit_message(query, text)
        logger.info("Prestige up", user_id=user_id, new_level=new_prestige, old_balance=old_balance)


def register_prestige_handlers(application):
    """Register prestige handlers."""
    application.add_handler(CommandHandler("prestige", prestige_command))
    application.add_handler(CallbackQueryHandler(prestige_callback, pattern=r"^prestige:"))
    logger.info("Prestige handlers registered")
