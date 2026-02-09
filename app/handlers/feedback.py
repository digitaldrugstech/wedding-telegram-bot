"""Feedback handlers for bug reports and feature requests."""

import html
import json
import os
from datetime import datetime

import structlog
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from app.utils.decorators import require_registered

logger = structlog.get_logger()

# Conversation states
WAITING_FOR_TEXT = 1

# Feedback storage file
FEEDBACK_FILE = os.environ.get("FEEDBACK_FILE", "/app/data/feedback.json")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_USER_ID", "710573786"))


def load_feedback() -> list:
    """Load feedback from file."""
    if not os.path.exists(FEEDBACK_FILE):
        return []
    try:
        with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def save_feedback(feedback_list: list):
    """Save feedback to file."""
    os.makedirs(os.path.dirname(FEEDBACK_FILE), exist_ok=True)
    with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
        json.dump(feedback_list, f, ensure_ascii=False, indent=2, default=str)


def add_feedback(user_id: int, username: str, feedback_type: str, text: str):
    """Add new feedback entry."""
    feedback_list = load_feedback()
    entry = {
        "id": len(feedback_list) + 1,
        "user_id": user_id,
        "username": username,
        "type": feedback_type,
        "text": text,
        "created_at": datetime.utcnow().isoformat(),
        "status": "new",
    }
    feedback_list.append(entry)
    save_feedback(feedback_list)
    logger.info("Feedback saved", feedback_id=entry["id"], type=feedback_type, user_id=user_id)
    return entry


@require_registered
async def bug_report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /bug_report command - start bug report conversation."""
    if not update.effective_user or not update.message:
        return ConversationHandler.END

    context.user_data["feedback_type"] = "bug"

    await update.message.reply_text(
        "<b>Опиши баг:</b>\n\n"
        "Расскажи что произошло, что ожидал и как воспроизвести.\n\n"
        "Можешь написать на русском или английском.\n\n"
        "/cancel — отмена",
        parse_mode="HTML",
    )

    return WAITING_FOR_TEXT


@require_registered
async def feature_request_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /feature_request command - start feature request conversation."""
    if not update.effective_user or not update.message:
        return ConversationHandler.END

    context.user_data["feedback_type"] = "feature"

    await update.message.reply_text(
        "<b>Опиши фичу:</b>\n\n"
        "Расскажи что хочешь видеть в боте, как это должно работать.\n\n"
        "Можешь написать на русском или английском.\n\n"
        "/cancel — отмена",
        parse_mode="HTML",
    )

    return WAITING_FOR_TEXT


async def receive_feedback_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive feedback text from user."""
    if not update.effective_user or not update.message:
        return ConversationHandler.END

    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    feedback_type = context.user_data.get("feedback_type", "unknown")
    text = update.message.text

    if not text or len(text) < 10:
        await update.message.reply_text("Слишком короткий текст. Напиши подробнее или /cancel для отмены.")
        return WAITING_FOR_TEXT

    if len(text) > 2000:
        await update.message.reply_text("Слишком длинный текст. Максимум 2000 символов.")
        return WAITING_FOR_TEXT

    # Save feedback
    entry = add_feedback(user_id, username, feedback_type, text)

    type_emoji = "🐛" if feedback_type == "bug" else "💡"
    type_name = "Баг-репорт" if feedback_type == "bug" else "Запрос фичи"

    await update.message.reply_text(
        f"{type_emoji} <b>{type_name} #{entry['id']}</b>\n\n"
        f"Записано!\n\n"
        f"Разработчики рассмотрят твоё обращение.",
        parse_mode="HTML",
    )

    # Notify admin
    try:
        safe_text = html.escape(text[:500]) + ("..." if len(text) > 500 else "")
        admin_message = (
            f"{type_emoji} <b>Новый {type_name.lower()}</b>\n\n"
            f"👤 @{username} ({user_id})\n"
            f"📝 #{entry['id']}\n\n"
            f"{safe_text}"
        )
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_message, parse_mode="HTML")
    except Exception as e:
        logger.warning("Failed to notify admin about feedback", error=str(e))

    return ConversationHandler.END


async def cancel_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel feedback conversation."""
    if not update.message:
        return ConversationHandler.END

    await update.message.reply_text("Отменено")
    return ConversationHandler.END


def register_feedback_handlers(application):
    """Register feedback handlers."""
    bug_handler = ConversationHandler(
        entry_points=[CommandHandler("bug_report", bug_report_command)],
        states={
            WAITING_FOR_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_feedback_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel_feedback)],
        allow_reentry=True,
    )

    feature_handler = ConversationHandler(
        entry_points=[CommandHandler("feature_request", feature_request_command)],
        states={
            WAITING_FOR_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_feedback_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel_feedback)],
        allow_reentry=True,
    )

    application.add_handler(bug_handler)
    application.add_handler(feature_handler)
