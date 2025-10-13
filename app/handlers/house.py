"""House handlers for Wedding Telegram Bot."""

import structlog
from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.services.house_service import HOUSE_TYPES, HouseService
from app.utils.decorators import require_registered
from app.utils.keyboards import house_buy_keyboard, house_menu_keyboard
from app.utils.formatters import format_diamonds

logger = structlog.get_logger()


@require_registered
async def house_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /house command - show house menu."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        can_sell, error, house_id = HouseService.can_sell_house(db, user_id)

        if can_sell:
            # Has house - show info and sell option
            house_info = HouseService.get_house_info(db, house_id)

            message = (
                f"🏠 <b>Твой дом</b>\n\n"
                f"{house_info['name']}\n"
                f"💰 Куплен за: {format_diamonds(house_info['price'])}\n"
                f"🛡️ Защита: {house_info['protection']}%\n\n"
                f"💡 Защита от похищения детей"
            )

            await update.message.reply_text(
                message,
                reply_markup=house_menu_keyboard(has_house=True, user_id=user_id),
                parse_mode="HTML"
            )
        else:
            # No house - show buy menu
            message = (
                "🏠 <b>Покупка дома</b>\n\n"
                "Выбери дом:\n\n"
                "💡 Дом защищает детей от похищения"
            )

            await update.message.reply_text(
                message,
                reply_markup=house_menu_keyboard(has_house=False, user_id=user_id),
                parse_mode="HTML"
            )


async def house_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle house menu callbacks."""
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
            "🏠 <b>Покупка дома</b>\n\n"
            "Выбери тип дома:",
            reply_markup=house_buy_keyboard(user_id=user_id),
            parse_mode="HTML"
        )

    elif action == "buy_confirm":
        # Buy house
        house_type = int(parts[2])

        with get_db() as db:
            can_buy, error = HouseService.can_buy_house(db, user_id, house_type)

            if not can_buy:
                await query.edit_message_text(f"❌ {error}", parse_mode="HTML")
                return

            success, message, house_id = HouseService.buy_house(db, user_id, house_type)

            if success:
                await query.edit_message_text(message, parse_mode="HTML")
            else:
                await query.edit_message_text(f"❌ Ошибка покупки", parse_mode="HTML")

    elif action == "sell":
        # Sell house
        with get_db() as db:
            can_sell, error, house_id = HouseService.can_sell_house(db, user_id)

            if not can_sell:
                await query.edit_message_text(f"❌ {error}", parse_mode="HTML")
                return

            success, message = HouseService.sell_house(db, user_id)

            if success:
                await query.edit_message_text(message, parse_mode="HTML")
            else:
                await query.edit_message_text("❌ Ошибка продажи", parse_mode="HTML")

    elif action == "info":
        # Show house info
        with get_db() as db:
            can_sell, error, house_id = HouseService.can_sell_house(db, user_id)

            if not can_sell:
                await query.edit_message_text(f"❌ {error}", parse_mode="HTML")
                return

            house_info = HouseService.get_house_info(db, house_id)

            message = (
                f"🏠 <b>Информация о доме</b>\n\n"
                f"{house_info['name']}\n"
                f"💰 Куплен за: {format_diamonds(house_info['price'])}\n"
                f"🛡️ Защита: {house_info['protection']}%\n\n"
                f"💡 Дом защищает от похищения детей"
            )

            await query.edit_message_text(
                message,
                reply_markup=house_menu_keyboard(has_house=True, user_id=user_id),
                parse_mode="HTML"
            )


def register_house_handlers(application):
    """Register house handlers."""
    application.add_handler(CommandHandler("house", house_command))
    application.add_handler(CallbackQueryHandler(house_callback, pattern="^house:"))
