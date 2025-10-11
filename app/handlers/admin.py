"""Admin commands for bot management."""

from app.database.connection import get_db
from app.database.models import Cooldown
from app.utils.decorators import admin_only
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes


@admin_only
async def reset_cooldown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset cooldown for a user (admin only)."""
    if not update.effective_user or not update.message:
        return

    # Check if replying to someone
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_user_id = update.message.reply_to_message.from_user.id
        target_username = (
            update.message.reply_to_message.from_user.username or update.message.reply_to_message.from_user.first_name
        )
    else:
        # Reset own cooldown
        target_user_id = update.effective_user.id
        target_username = update.effective_user.username or update.effective_user.first_name

    with get_db() as db:
        # Delete all cooldowns for the user
        deleted_count = db.query(Cooldown).filter(Cooldown.user_id == target_user_id).delete()
        db.commit()

        if deleted_count > 0:
            await update.message.reply_text(
                f"✅ Сброшено {deleted_count} кулдаунов\n{target_username} (ID: {target_user_id})"
            )
        else:
            await update.message.reply_text(f"⚠️ Нет активных кулдаунов\n{target_username} (ID: {target_user_id})")


def register_admin_handlers(application):
    """Register admin handlers."""
    application.add_handler(CommandHandler("reset_cd", reset_cooldown_command))
