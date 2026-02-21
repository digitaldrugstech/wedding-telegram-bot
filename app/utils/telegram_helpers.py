"""Telegram-specific helper utilities."""

import asyncio

import structlog
from telegram.error import BadRequest, RetryAfter

logger = structlog.get_logger()


async def safe_edit_message(query, text: str, reply_markup=None, parse_mode="HTML"):
    """Safely edit message, handling 'message is not modified' and flood control.

    Args:
        query: The CallbackQuery object from telegram.
        text: The new text content for the message.
        reply_markup: Optional InlineKeyboardMarkup for the message.
        parse_mode: Parse mode for the text (default: "HTML").

    Raises:
        BadRequest: If the error is not about the message being unmodified.
    """
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except RetryAfter as e:
        await asyncio.sleep(e.retry_after)
        try:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            pass
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise


def schedule_delete(context, chat_id: int, message_ids: list, delay: int = 60):
    """Schedule messages for deletion after delay seconds.

    Use for routine menus/status views to keep chat clean.
    Does NOT delete important results (purchases, wins, etc).
    """
    context.job_queue.run_once(
        _delete_messages_job,
        when=delay,
        data={"chat_id": chat_id, "message_ids": message_ids},
    )


async def _delete_messages_job(context):
    """Job callback to delete scheduled messages."""
    data = context.job.data
    chat_id = data["chat_id"]
    for msg_id in data["message_ids"]:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass  # Message already deleted or bot lacks permissions


async def delete_command_and_reply(update, reply_message, context, delay: int = 60):
    """Schedule both the user's command message and bot's reply for deletion.

    Call this after sending a menu/status response that should auto-clean.
    """
    message_ids = []
    if update.message:
        message_ids.append(update.message.message_id)
    if reply_message:
        message_ids.append(reply_message.message_id)
    if message_ids:
        schedule_delete(context, update.effective_chat.id, message_ids, delay=delay)
