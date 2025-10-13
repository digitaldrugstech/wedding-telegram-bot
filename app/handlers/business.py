"""Business handlers for Wedding Telegram Bot."""

import structlog
from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.services.business_service import BUSINESS_TYPES, BusinessService
from app.utils.decorators import require_registered
from app.utils.keyboards import business_buy_keyboard, business_menu_keyboard
from app.utils.formatters import format_diamonds

logger = structlog.get_logger()


@require_registered
async def business_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /business command - show business menu."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        businesses = BusinessService.get_user_businesses(db, user_id)

        if businesses:
            # Has businesses - show list
            message = "<b>💼 Твои бизнесы</b>\n\n"

            total_income = 0
            for business in businesses:
                message += (
                    f"{business['name']}\n"
                    f"📈 {format_diamonds(business['weekly_payout'])}/неделя\n\n"
                )
                total_income += business['weekly_payout']

            message += f"💰 <b>Итого:</b> {format_diamonds(total_income)}/неделя"

            await update.message.reply_text(
                message,
                reply_markup=business_menu_keyboard(user_id=user_id),
                parse_mode="HTML"
            )
        else:
            # No businesses
            message = (
                "💼 <b>Бизнесы</b>\n\n"
                "У тебя нет бизнесов\n\n"
                "💡 Бизнесы приносят пассивный доход раз в неделю"
            )

            await update.message.reply_text(
                message,
                reply_markup=business_menu_keyboard(user_id=user_id),
                parse_mode="HTML"
            )


async def business_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle business menu callbacks."""
    query = update.callback_query
    await query.answer()

    if not update.effective_user:
        return

    user_id = update.effective_user.id
    parts = query.data.split(":")
    action = parts[1]

    # Check button owner
    if len(parts) >= 3:
        owner_id = int(parts[2])
        if user_id != owner_id:
            await query.answer("Эта кнопка не для тебя", show_alert=True)
            return

    if action == "buy":
        # Show buy menu
        await query.edit_message_text(
            "💼 <b>Покупка бизнеса</b>\n\n"
            "Выбери тип бизнеса:\n\n"
            "💡 Максимум 3 каждого типа",
            reply_markup=business_buy_keyboard(user_id=user_id),
            parse_mode="HTML"
        )

    elif action == "buy_confirm":
        # Buy business
        business_type = int(parts[2])

        with get_db() as db:
            can_buy, error = BusinessService.can_buy_business(db, user_id, business_type)

            if not can_buy:
                await query.edit_message_text(f"❌ {error}", parse_mode="HTML")
                return

            success, message = BusinessService.buy_business(db, user_id, business_type)

            if success:
                await query.edit_message_text(message, parse_mode="HTML")
            else:
                await query.edit_message_text("❌ Ошибка покупки", parse_mode="HTML")

    elif action == "list":
        # Show businesses list
        with get_db() as db:
            businesses = BusinessService.get_user_businesses(db, user_id)

            if not businesses:
                await query.edit_message_text(
                    "💼 <b>Бизнесы</b>\n\nУ тебя нет бизнесов",
                    parse_mode="HTML"
                )
                return

            message = "<b>💼 Твои бизнесы</b>\n\n"
            total_income = 0

            for business in businesses:
                message += (
                    f"{business['name']}\n"
                    f"📈 {format_diamonds(business['weekly_payout'])}/неделя\n\n"
                )
                total_income += business['weekly_payout']

            message += f"💰 <b>Итого:</b> {format_diamonds(total_income)}/неделя"

            await query.edit_message_text(
                message,
                reply_markup=business_menu_keyboard(user_id=user_id),
                parse_mode="HTML"
            )

    elif action == "sell":
        # For simplicity, just show message
        # In full implementation, would show list of businesses to sell
        await query.edit_message_text(
            "💼 <b>Продажа бизнеса</b>\n\n"
            "Функция в разработке\n\n"
            "💡 Возврат 70% от цены покупки",
            parse_mode="HTML"
        )


def register_business_handlers(application):
    """Register business handlers."""
    application.add_handler(CommandHandler("business", business_command))
    application.add_handler(CallbackQueryHandler(business_callback, pattern="^business:"))
