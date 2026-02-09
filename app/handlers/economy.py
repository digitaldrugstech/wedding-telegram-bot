"""Economy handlers — tax system."""

import structlog
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.constants import TAX_RATE, TAX_THRESHOLD
from app.database.connection import get_db
from app.database.models import TaxPayment, User
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds, format_word

logger = structlog.get_logger()


@require_registered
async def tax_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show tax information."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()

        taxable_amount = max(0, user.balance - TAX_THRESHOLD)
        weekly_tax = int(taxable_amount * TAX_RATE)

        # Get total taxes paid
        total_taxes = db.query(TaxPayment).filter(TaxPayment.user_id == user_id).count()
        total_paid = sum(t.amount for t in db.query(TaxPayment).filter(TaxPayment.user_id == user_id).all())

        text = (
            f"🏛 <b>Налоговая система</b>\n\n"
            f"Баланс: {format_diamonds(user.balance)}\n"
            f"Налогооблагаемая база: {format_diamonds(taxable_amount)}\n\n"
            f"Еженедельный налог: {format_diamonds(weekly_tax)}\n"
            f"Ставка: {int(TAX_RATE * 100)}% от суммы свыше {format_diamonds(TAX_THRESHOLD)}\n\n"
            f"Всего выплачено налогов: {format_diamonds(total_paid)}\n"
            f"{format_word(total_taxes, 'Выплата', 'Выплаты', 'Выплат')}"
        )

        await update.message.reply_text(text, parse_mode="HTML")


def register_economy_handlers(application):
    """Register economy handlers."""
    application.add_handler(CommandHandler("tax", tax_command))
