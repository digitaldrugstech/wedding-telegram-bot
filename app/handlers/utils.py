"""Utility command handlers (balance, help, transfer)."""

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import User
from app.utils.decorators import require_registered


@require_registered
async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /balance command."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()

        if not user:
            return

        await update.message.reply_text(f"💎 Ваш баланс: {user.balance} алмазов")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_text = (
        "🤖 *Wedding Bot - Справка*\n\n"
        "*Основные команды:*\n"
        "/start - Начать работу с ботом\n"
        "/profile - Показать профиль\n"
        "/balance - Показать баланс алмазов\n\n"
        "*Работа:*\n"
        "/work - Меню управления работой\n"
        "/job - Работать (получить зарплату)\n\n"
        "*Брак и семья:*\n"
        "/propose - Предложить брак (ответом на сообщение)\n"
        "/marriage - Меню брака и семьи\n"
        "/family - Меню семьи и детей\n\n"
        "*Экономика:*\n"
        "/house - Меню покупки и продажи дома\n"
        "/business - Меню бизнесов\n"
        "/casino [ставка] - Играть в казино\n\n"
        "*Другое:*\n"
        "/help - Справка по командам\n\n"
        "💎 *Валюта:* Алмазы\n\n"
        "Для навигации используйте кнопки под сообщениями!"
    )

    await update.message.reply_text(help_text, parse_mode="Markdown")


def register_utils_handlers(application):
    """Register utility handlers."""
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("help", help_command))
