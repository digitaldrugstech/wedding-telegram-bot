"""Utility command handlers (balance, help, transfer)."""

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import User
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds


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

        await update.message.reply_text(f"💰 {format_diamonds(user.balance)}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_text = (
        "<b>Команды</b>\n\n"
        "<b>Профиль</b>\n"
        "/start — начать\n"
        "/profile — профиль\n"
        "/balance — баланс\n\n"
        "<b>Работа</b>\n"
        "/work — меню\n"
        "/job — работать\n\n"
        "<b>Брак</b>\n"
        "/propose @username — предложить\n"
        "/marriage — меню\n"
        "/makelove — любовь\n"
        "/date — свидание\n"
        "/cheat @username — измена\n\n"
        "💎 Валюта — алмазы"
    )

    await update.message.reply_text(help_text, parse_mode="HTML")


def register_utils_handlers(application):
    """Register utility handlers."""
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("help", help_command))
