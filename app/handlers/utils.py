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


@require_registered
async def transfer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /transfer command."""
    if not update.effective_user or not update.message:
        return

    sender_id = update.effective_user.id

    # Parse arguments
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "💰 <b>Перевод алмазов</b>\n\n"
            "Использование:\n"
            "/transfer @username [сумма]\n\n"
            "Пример: /transfer @user 100",
            parse_mode="HTML"
        )
        return

    # Parse username and amount
    username = context.args[0].lstrip("@")
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Сумма должна быть числом")
        return

    # Validate amount
    if amount <= 0:
        await update.message.reply_text("❌ Сумма должна быть больше 0")
        return

    with get_db() as db:
        # Get sender
        sender = db.query(User).filter(User.telegram_id == sender_id).first()

        # Check balance
        if sender.balance < amount:
            await update.message.reply_text(
                f"❌ Недостаточно алмазов\n\n"
                f"💰 Твой баланс: {format_diamonds(sender.balance)}"
            )
            return

        # Get recipient
        recipient = db.query(User).filter(User.username == username).first()

        if not recipient:
            await update.message.reply_text(f"❌ Пользователь @{username} не найден")
            return

        # Can't transfer to self
        if sender_id == recipient.telegram_id:
            await update.message.reply_text("❌ Нельзя перевести себе")
            return

        # Execute transfer
        sender.balance -= amount
        recipient.balance += amount

        db.commit()

        await update.message.reply_text(
            f"✅ <b>Перевод выполнен</b>\n\n"
            f"💰 {format_diamonds(amount)} → @{username}\n\n"
            f"💰 Твой баланс: {format_diamonds(sender.balance)}",
            parse_mode="HTML"
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_text = (
        "<b>Команды</b>\n\n"
        "<b>Профиль</b>\n"
        "/start — начать\n"
        "/profile — профиль\n"
        "/balance — баланс\n"
        "/transfer @user [сумма] — перевод\n\n"
        "<b>Работа</b>\n"
        "/work — меню\n"
        "/job — работать\n\n"
        "<b>Брак</b>\n"
        "/propose @username — предложить\n"
        "/marriage — меню\n"
        "/makelove — любовь\n"
        "/date — свидание\n"
        "/cheat @username — измена\n\n"
        "<b>Семья</b>\n"
        "/family — дети\n\n"
        "<b>Другое</b>\n"
        "/house — дом\n"
        "/business — бизнес\n"
        "/casino — казино\n\n"
        "💎 Валюта — алмазы"
    )

    await update.message.reply_text(help_text, parse_mode="HTML")


def register_utils_handlers(application):
    """Register utility handlers."""
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("transfer", transfer_command))
    application.add_handler(CommandHandler("help", help_command))
