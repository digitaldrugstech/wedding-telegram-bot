"""Telegram-specific helper utilities."""

from telegram.error import BadRequest


async def safe_edit_message(query, text: str, reply_markup=None, parse_mode="HTML"):
    """Safely edit message, ignoring 'message is not modified' error.

    This helper catches the common BadRequest error that occurs when trying to edit
    a message to the exact same content. This often happens with inline keyboards
    when the user clicks a button that refreshes the same state.

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
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise
