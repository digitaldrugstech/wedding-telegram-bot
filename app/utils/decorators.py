"""Decorators for bot handlers."""

import functools
from datetime import datetime, timedelta
from typing import Callable

from telegram import Update
from telegram.ext import ContextTypes

from app.database.connection import get_db
from app.database.models import Cooldown, User


def require_registered(func: Callable) -> Callable:
    """
    Decorator to require user registration.

    Usage:
        @require_registered
        async def my_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            ...
    """

    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not update.effective_user:
            return

        user_id = update.effective_user.id

        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == user_id).first()

            if not user:
                await update.message.reply_text(
                    "⚠️ Вы не зарегистрированы! Используйте /start для регистрации."
                )
                return

            if user.is_banned:
                await update.message.reply_text("🚫 Вы заблокированы и не можете использовать бота.")
                return

        return await func(update, context, *args, **kwargs)

    return wrapper


def cooldown(action: str, seconds: int) -> Callable:
    """
    Decorator to add cooldown to commands.

    Args:
        action: Cooldown action name (e.g., "job", "casino")
        seconds: Cooldown duration in seconds

    Usage:
        @cooldown("job", 4 * 3600)  # 4 hours
        async def job_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            if not update.effective_user:
                return

            user_id = update.effective_user.id

            with get_db() as db:
                # Check cooldown
                cooldown_entry = (
                    db.query(Cooldown)
                    .filter(Cooldown.user_id == user_id, Cooldown.action == action)
                    .first()
                )

                if cooldown_entry and cooldown_entry.expires_at > datetime.utcnow():
                    remaining = cooldown_entry.expires_at - datetime.utcnow()
                    hours, remainder = divmod(remaining.total_seconds(), 3600)
                    minutes, seconds_remaining = divmod(remainder, 60)

                    time_str = []
                    if hours > 0:
                        time_str.append(f"{int(hours)}ч")
                    if minutes > 0:
                        time_str.append(f"{int(minutes)}м")
                    if seconds_remaining > 0 and not time_str:
                        time_str.append(f"{int(seconds_remaining)}с")

                    await update.message.reply_text(
                        f"⏳ Команда доступна через: {' '.join(time_str)}"
                    )
                    return

            # Execute command
            result = await func(update, context, *args, **kwargs)

            # Set cooldown
            with get_db() as db:
                expires_at = datetime.utcnow() + timedelta(seconds=seconds)

                cooldown_entry = (
                    db.query(Cooldown)
                    .filter(Cooldown.user_id == user_id, Cooldown.action == action)
                    .first()
                )

                if cooldown_entry:
                    cooldown_entry.expires_at = expires_at
                else:
                    cooldown_entry = Cooldown(user_id=user_id, action=action, expires_at=expires_at)
                    db.add(cooldown_entry)

            return result

        return wrapper

    return decorator


def admin_only(func: Callable) -> Callable:
    """
    Decorator to restrict commands to admin only.

    Usage:
        @admin_only
        async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            ...
    """

    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        from app.config import config

        if not update.effective_user:
            return

        if update.effective_user.id != config.admin_user_id:
            await update.message.reply_text("🚫 У вас нет прав для использования этой команды.")
            return

        # Check if in private chat
        if update.effective_chat.type != "private":
            await update.message.reply_text("🚫 Админ команды доступны только в ЛС бота.")
            return

        return await func(update, context, *args, **kwargs)

    return wrapper
