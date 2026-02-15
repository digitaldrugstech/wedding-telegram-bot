"""Gift box handler — redirects to scratch cards."""

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.utils.decorators import require_registered


@require_registered
async def giftbox_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /giftbox — redirect to /scratch."""
    if not update.effective_user or not update.message:
        return

    await update.message.reply_text(
        "🎫 Гифт-боксы объединены со скретч-картами!\n\n" "Используй /scratch [ставка] — от 10 до 1000💎"
    )


def register_giftbox_handlers(application):
    """Register giftbox handlers."""
    application.add_handler(CommandHandler("giftbox", giftbox_command))
