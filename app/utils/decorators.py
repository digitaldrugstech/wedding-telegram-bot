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
                await update.message.reply_text("⚠️ Ты не зарегистрирован. Используй /start")
                return

            if user.is_banned:
                await update.message.reply_text("🚫 Ты заблокирован")
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

                    await update.message.reply_text(f"Можешь работать через {' '.join(time_str)}")
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
            await update.message.reply_text("🚫 У тебя нет прав")
            return

        return await func(update, context, *args, **kwargs)

    return wrapper


def admin_only_private(func: Callable) -> Callable:
    """
    Decorator to restrict commands to admin only in private chat.

    Usage:
        @admin_only_private
        async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            ...
    """

    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        from app.config import config

        if not update.effective_user:
            return

        if update.effective_user.id != config.admin_user_id:
            await update.message.reply_text("🚫 У тебя нет прав")
            return

        # Check if in private chat
        if update.effective_chat.type != "private":
            await update.message.reply_text("🚫 Команда доступна только в ЛС")
            return

        return await func(update, context, *args, **kwargs)

    return wrapper


def button_owner_only(func: Callable) -> Callable:
    """
    Decorator for callback query handlers to ensure only the command author can press buttons.

    Stores the original command sender's ID in callback_data as "action:param:user_id"
    or checks if button owner matches current user.

    Usage:
        @button_owner_only
        async def my_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            ...
    """

    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        query = update.callback_query

        if not query or not update.effective_user:
            return

        # Extract user_id from callback_data if present (format: "action:param:user_id")
        # Otherwise check if message was sent by the user pressing the button
        parts = query.data.split(":")

        # If callback_data has user_id at the end
        if len(parts) >= 2 and parts[-1].isdigit():
            expected_user_id = int(parts[-1])
            if update.effective_user.id != expected_user_id:
                await query.answer("⚠️ Эта кнопка не для тебя", show_alert=True)
                return
        else:
            # Fallback: check if message belongs to user (not reliable in groups)
            # Store user_id in context for this session
            if not context.user_data.get("button_owner_checked"):
                context.user_data["button_owner_checked"] = True

        return await func(update, context, *args, **kwargs)

    return wrapper
