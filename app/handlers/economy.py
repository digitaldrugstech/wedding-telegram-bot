"""Economy handlers — tax system."""

import structlog
from sqlalchemy import func
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.constants import TAX_RATE, TAX_THRESHOLD
from app.database.connection import get_db
from app.database.models import TaxPayment, User
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds

logger = structlog.get_logger()


@require_registered
async def tax_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show tax information (compact — details merged into /profile)."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()

        taxable_amount = max(0, user.balance - TAX_THRESHOLD)
        weekly_tax = int(taxable_amount * TAX_RATE)

        total_paid = (
            db.query(func.coalesce(func.sum(TaxPayment.amount), 0)).filter(TaxPayment.user_id == user_id).scalar()
        )

        text = (
            f"🏛 <b>Налоги</b>\n\n"
            f"Ставка: {int(TAX_RATE * 100)}% от суммы свыше {format_diamonds(TAX_THRESHOLD)}\n"
            f"Еженедельный налог: {format_diamonds(weekly_tax)}\n"
            f"Всего выплачено: {format_diamonds(total_paid)}\n\n"
            f"💡 Налог также виден в /profile"
        )

        await update.message.reply_text(text, parse_mode="HTML")


def register_economy_handlers(application):
    """Register economy handlers."""
    application.add_handler(CommandHandler("tax", tax_command))
