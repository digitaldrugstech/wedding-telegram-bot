"""Business handlers for Wedding Telegram Bot."""

import structlog
from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import User
from app.services.business_service import BusinessService
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds
from app.utils.keyboards import business_buy_keyboard, business_menu_keyboard
from app.utils.telegram_helpers import safe_edit_message

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
                message += f"{business['name']}\n" f"📈 {format_diamonds(business['weekly_payout'])}/неделя\n\n"
                total_income += business["weekly_payout"]

            message += f"💰 <b>Итого:</b> {format_diamonds(total_income)}/неделя"

            await update.message.reply_text(
                message, reply_markup=business_menu_keyboard(user_id=user_id), parse_mode="HTML"
            )
        else:
            # No businesses
            message = (
                "💼 <b>Бизнесы</b>\n\n" "У тебя нет бизнесов\n\n" "💡 Бизнесы приносят пассивный доход раз в неделю"
            )

            await update.message.reply_text(
                message, reply_markup=business_menu_keyboard(user_id=user_id), parse_mode="HTML"
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

    # Check button owner (user_id is the last part)
    if len(parts) >= 3 and parts[-1].isdigit():
        owner_id = int(parts[-1])
        if user_id != owner_id:
            await query.answer("Эта кнопка не для тебя", show_alert=True)
            return

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user or user.is_banned:
            await query.answer("Доступ запрещён", show_alert=True)
            return

    if action == "buy":
        # Show buy menu (page 1)
        await safe_edit_message(
            query,
            "💼 <b>Покупка бизнеса</b>\n\n" "Выбери тип бизнеса:\n\n" "💡 Максимум 3 каждого типа",
            reply_markup=business_buy_keyboard(user_id=user_id, page=1),
        )

    elif action == "buy_page":
        # Navigate business pages
        try:
            page = int(parts[2])
        except (ValueError, IndexError):
            return
        await safe_edit_message(
            query,
            "💼 <b>Покупка бизнеса</b>\n\n" "Выбери тип бизнеса:\n\n" "💡 Максимум 3 каждого типа",
            reply_markup=business_buy_keyboard(user_id=user_id, page=page),
        )

    elif action == "buy_confirm":
        # Buy business
        try:
            business_type = int(parts[2])
        except (ValueError, IndexError):
            return

        with get_db() as db:
            can_buy, error = BusinessService.can_buy_business(db, user_id, business_type)

            if not can_buy:
                await safe_edit_message(query, f"❌ {error}")
                return

            success, message = BusinessService.buy_business(db, user_id, business_type)

            if success:
                await safe_edit_message(query, message)
            else:
                await safe_edit_message(query, "❌ Ошибка покупки")

    elif action == "list":
        # Show businesses list
        with get_db() as db:
            businesses = BusinessService.get_user_businesses(db, user_id)

            if not businesses:
                await safe_edit_message(query, "💼 <b>Бизнесы</b>\n\nУ тебя нет бизнесов")
                return

            message = "<b>💼 Твои бизнесы</b>\n\n"
            total_income = 0

            for business in businesses:
                message += f"{business['name']}\n" f"📈 {format_diamonds(business['weekly_payout'])}/неделя\n\n"
                total_income += business["weekly_payout"]

            message += f"💰 <b>Итого:</b> {format_diamonds(total_income)}/неделя"

            await safe_edit_message(query, message, reply_markup=business_menu_keyboard(user_id=user_id))

    elif action == "sell":
        # Show sell menu with user's businesses
        with get_db() as db:
            businesses = BusinessService.get_user_businesses(db, user_id)

            if not businesses:
                await safe_edit_message(query, "💼 <b>Продажа</b>\n\nУ тебя нет бизнесов для продажи")
                return

            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            message = "💼 <b>Продажа бизнеса</b>\n\n💡 Возврат 70% от цены покупки\n\nВыбери бизнес:"
            keyboard = []
            for business in businesses:
                refund = int(business["purchase_price"] * 0.7)
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"{business['name']} → {format_diamonds(refund)}",
                            callback_data=f"business:sell_confirm:{business['id']}:{user_id}",
                        )
                    ]
                )
            keyboard.append([InlineKeyboardButton("« Назад", callback_data=f"business:back:{user_id}")])

            await safe_edit_message(query, message, reply_markup=InlineKeyboardMarkup(keyboard))

    elif action == "sell_confirm":
        # Sell specific business
        try:
            business_id = int(parts[2])
        except (ValueError, IndexError):
            return

        with get_db() as db:
            success, message = BusinessService.sell_business(db, business_id, user_id)

            if success:
                await safe_edit_message(query, message)
            else:
                await safe_edit_message(query, f"❌ {message}")

    elif action == "back":
        # Go back to main business menu
        with get_db() as db:
            businesses = BusinessService.get_user_businesses(db, user_id)

            if businesses:
                message = "<b>💼 Твои бизнесы</b>\n\n"
                total_income = 0

                for business in businesses:
                    message += f"{business['name']}\n" f"📈 {format_diamonds(business['weekly_payout'])}/неделя\n\n"
                    total_income += business["weekly_payout"]

                message += f"💰 <b>Итого:</b> {format_diamonds(total_income)}/неделя"
            else:
                message = "💼 <b>Бизнесы</b>\n\nУ тебя нет бизнесов\n\n💡 Бизнесы приносят пассивный доход раз в неделю"

            await safe_edit_message(query, message, reply_markup=business_menu_keyboard(user_id=user_id))


def register_business_handlers(application):
    """Register business handlers."""
    application.add_handler(CommandHandler("business", business_command))
    application.add_handler(CallbackQueryHandler(business_callback, pattern="^business:"))
