"""Marriage handlers for Wedding Telegram Bot."""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
import structlog

from app.database.connection import get_db
from app.database.models import User
from app.services.marriage_service import MarriageService, PROPOSE_COST, DIVORCE_COST, GIFT_MIN
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds, format_time_remaining

logger = structlog.get_logger()


@require_registered
async def propose_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /propose command."""
    if not update.effective_user or not update.message:
        return

    proposer_id = update.effective_user.id
    target = None
    target_id = None

    # Option 1: Reply to message
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target = update.message.reply_to_message.from_user
        target_id = target.id
    # Option 2: Username argument (@username)
    elif context.args and len(context.args) > 0:
        username = context.args[0].lstrip('@')

        with get_db() as db:
            target_user = db.query(User).filter(User.username == username).first()
            if not target_user:
                await update.message.reply_text(f"Пользователь @{username} не найден")
                return
            target_id = target_user.telegram_id

            # Create simple target object
            class FakeUser:
                def __init__(self, user_id, username, first_name):
                    self.id = user_id
                    self.first_name = first_name
                    self.is_bot = False

            target = FakeUser(target_id, username, username)
    else:
        await update.message.reply_text(
            "Используй одну из команд:\n"
            "• /propose (ответь на сообщение)\n"
            "• /propose @username"
        )
        return

    if target.is_bot:
        await update.message.reply_text("Нельзя жениться на боте")
        return

    if target_id == proposer_id:
        await update.message.reply_text("Нельзя жениться на себе")
        return

    with get_db() as db:
        # Check proposer can propose
        can_propose, error = MarriageService.can_propose(db, proposer_id)
        if not can_propose:
            await update.message.reply_text(error)
            return

        # Check target exists and is registered
        target_user = db.query(User).filter(User.telegram_id == target_id).first()
        if not target_user:
            await update.message.reply_text("Этот человек не зарегистрирован в боте")
            return

        # Check target can accept
        can_accept, error = MarriageService.can_accept_proposal(db, target_id, proposer_id)
        if not can_accept:
            await update.message.reply_text(f"Нельзя: {error}")
            return

    # Send proposal with buttons
    proposer_name = update.effective_user.first_name
    target_name = target.first_name

    keyboard = [
        [
            InlineKeyboardButton("💍 Принять", callback_data=f"propose_accept:{proposer_id}:{target_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"propose_reject:{proposer_id}:{target_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    proposal_text = (
        f"💍 <b>Предложение руки и сердца!</b>\n\n"
        f"<b>{proposer_name}</b> делает предложение <b>{target_name}</b>\n\n"
        f"💰 Стоимость: {PROPOSE_COST} алмазов\n\n"
        f"Ты согласен/согласна?"
    )

    await update.message.reply_text(proposal_text, reply_markup=reply_markup, parse_mode="HTML")

    logger.info("Proposal sent", proposer_id=proposer_id, target_id=target_id)


async def propose_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle proposal accept/reject."""
    query = update.callback_query
    await query.answer()

    if not update.effective_user:
        return

    action, proposer_id, target_id = query.data.split(":")
    proposer_id = int(proposer_id)
    target_id = int(target_id)
    clicker_id = update.effective_user.id

    # Only target can click
    if clicker_id != target_id:
        await query.answer("Эта кнопка не для тебя", show_alert=True)
        return

    if action == "propose_accept":
        with get_db() as db:
            # Double-check conditions
            can_accept, error = MarriageService.can_accept_proposal(db, target_id, proposer_id)
            if not can_accept:
                await query.edit_message_text(f"❌ Не получилось: {error}")
                return

            can_propose, error = MarriageService.can_propose(db, proposer_id)
            if not can_propose:
                await query.edit_message_text(f"❌ Не получилось: {error}")
                return

            # Create marriage
            marriage = MarriageService.create_marriage(db, proposer_id, target_id)

            proposer = db.query(User).filter(User.telegram_id == proposer_id).first()
            target_user = db.query(User).filter(User.telegram_id == target_id).first()

            # Extract data before session closes
            proposer_username = proposer.username or 'User'
            target_username = target_user.username or 'User'
            marriage_id = marriage.id

        await query.edit_message_text(
            f"🎉 <b>Поздравляем!</b>\n\n"
            f"💍 {proposer_username} и {target_username} теперь муж и жена!\n\n"
            f"💰 Потрачено: {PROPOSE_COST} алмазов\n\n"
            f"Используй /marriage для управления браком",
            parse_mode="HTML"
        )

        logger.info("Proposal accepted", proposer_id=proposer_id, target_id=target_id, marriage_id=marriage_id)

    elif action == "propose_reject":
        await query.edit_message_text(
            f"❌ <b>Предложение отклонено</b>\n\n"
            f"Может, в следующий раз повезет...",
            parse_mode="HTML"
        )

        logger.info("Proposal rejected", proposer_id=proposer_id, target_id=target_id)


@require_registered
async def marriage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /marriage command - show marriage menu."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        marriage = MarriageService.get_active_marriage(db, user_id)

        if not marriage:
            await update.message.reply_text(
                "💔 Ты не женат/замужем\n\n"
                "Используй /propose чтобы сделать предложение"
            )
            return

        # Get partner info
        partner_id = MarriageService.get_partner_id(marriage, user_id)
        partner = db.query(User).filter(User.telegram_id == partner_id).first()
        user = db.query(User).filter(User.telegram_id == user_id).first()

        # Build keyboard
        keyboard = [
            [
                InlineKeyboardButton("💝 Подарить", callback_data=f"marriage_gift:{user_id}"),
                InlineKeyboardButton("💔 Развод", callback_data=f"marriage_divorce:{user_id}")
            ],
            [
                InlineKeyboardButton("❤️ /makelove", callback_data=f"marriage_help_love:{user_id}"),
                InlineKeyboardButton("📅 /date", callback_data=f"marriage_help_date:{user_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Build message
        days_married = (marriage.created_at - marriage.created_at).days  # Will be calculated properly
        partner_name = partner.username or f"User{partner.telegram_id}"

        message = (
            f"💍 <b>Твой брак</b>\n\n"
            f"👫 <b>Супруг/Супруга:</b> @{partner_name}\n"
            f"📅 <b>В браке:</b> {days_married} дней\n"
            f"❤️ <b>Занимались любовью:</b> {marriage.love_count} раз\n\n"
            f"💰 <b>Твой баланс:</b> {format_diamonds(user.balance)}\n"
            f"💰 <b>Баланс супруга:</b> {format_diamonds(partner.balance)}"
        )

        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode="HTML")


async def marriage_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle marriage menu callbacks."""
    query = update.callback_query
    await query.answer()

    if not update.effective_user:
        return

    action, owner_id = query.data.split(":")[0], int(query.data.split(":")[1])
    clicker_id = update.effective_user.id

    # Only owner can click
    if clicker_id != owner_id:
        await query.answer("Эта кнопка не для тебя", show_alert=True)
        return

    if action == "marriage_divorce":
        # Show confirmation
        keyboard = [
            [
                InlineKeyboardButton("✅ Да", callback_data=f"divorce_confirm:{owner_id}"),
                InlineKeyboardButton("❌ Нет", callback_data=f"divorce_cancel:{owner_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"⚠️ <b>Развод</b>\n\n"
            f"Точно хочешь развестись?\n\n"
            f"💰 <b>Стоимость:</b> {DIVORCE_COST} алмазов",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )

    elif action == "divorce_confirm":
        with get_db() as db:
            success, message = MarriageService.divorce(db, owner_id)

            if success:
                await query.edit_message_text(
                    f"💔 <b>Вы развелись</b>\n\n"
                    f"💰 Потрачено: {DIVORCE_COST} алмазов",
                    parse_mode="HTML"
                )
            else:
                await query.edit_message_text(f"❌ {message}")

    elif action == "divorce_cancel":
        # Go back to marriage menu
        await query.answer("Отменено")
        await marriage_command(update, context)

    elif action == "marriage_gift":
        await query.edit_message_text(
            f"💝 <b>Подарить алмазы супругу</b>\n\n"
            f"Напиши: /gift [количество]\n\n"
            f"Минимум: {GIFT_MIN} алмазов"
        )

    elif action == "marriage_help_love":
        await query.answer(
            "Используй /makelove чтобы заняться любовью с супругом (20% шанс зачатия ребенка)",
            show_alert=True
        )

    elif action == "marriage_help_date":
        await query.answer(
            "Используй /date чтобы сходить на свидание (заработок 10-50 алмазов)",
            show_alert=True
        )


@require_registered
async def gift_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /gift command."""
    if not update.effective_user or not update.message or not context.args:
        await update.message.reply_text(f"Используй: /gift [количество]\n\nМинимум: {GIFT_MIN} алмазов")
        return

    user_id = update.effective_user.id

    try:
        amount = int(context.args[0])
    except (ValueError, IndexError):
        await update.message.reply_text("Укажи правильное количество алмазов")
        return

    with get_db() as db:
        success, message = MarriageService.gift_diamonds(db, user_id, amount)

        if success:
            await update.message.reply_text(
                f"💝 {message}",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(f"❌ {message}")


@require_registered
async def makelove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /makelove command."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        can_love, error, cooldown = MarriageService.can_make_love(db, user_id)

        if not can_love:
            if cooldown:
                time_remaining = format_time_remaining(cooldown)
                await update.message.reply_text(f"❤️ Можешь заняться любовью через {time_remaining}")
            else:
                await update.message.reply_text(error)
            return

        success, conceived = MarriageService.make_love(db, user_id)

        if conceived:
            await update.message.reply_text(
                "❤️ <b>Вы занялись любовью</b>\n\n"
                "🎉 <b>Поздравляем!</b> Ваша жена забеременела!\n\n"
                "Ребенок родится через 9 дней (скоро в обновлении)",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                "❤️ <b>Вы занялись любовью</b>\n\n"
                "Было приятно, но зачатие не произошло\n\n"
                "Попробуй еще раз через 24 часа",
                parse_mode="HTML"
            )

        logger.info("Make love", user_id=user_id, conceived=conceived)


@require_registered
async def date_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /date command."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        can_date, error, cooldown = MarriageService.can_date(db, user_id)

        if not can_date:
            if cooldown:
                time_remaining = format_time_remaining(cooldown)
                await update.message.reply_text(f"📅 Можешь сходить на свидание через {time_remaining}")
            else:
                await update.message.reply_text(error)
            return

        earned, location = MarriageService.go_on_date(db, user_id)

        await update.message.reply_text(
            f"📅 <b>Свидание</b>\n\n"
            f"Вы сходили в <b>{location}</b>\n\n"
            f"💰 <b>Заработали:</b> {format_diamonds(earned)}\n\n"
            f"Следующее свидание через 12 часов",
            parse_mode="HTML"
        )

        logger.info("Date completed", user_id=user_id, earned=earned, location=location)


@require_registered
async def cheat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cheat command - RISKY."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    target = None
    target_id = None

    # Option 1: Reply to message
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target = update.message.reply_to_message.from_user
        target_id = target.id
    # Option 2: Username argument (@username)
    elif context.args and len(context.args) > 0:
        username = context.args[0].lstrip('@')

        with get_db() as db:
            target_user = db.query(User).filter(User.username == username).first()
            if not target_user:
                await update.message.reply_text(f"Пользователь @{username} не найден")
                return
            target_id = target_user.telegram_id

            # Simple target object
            class FakeUser:
                def __init__(self, user_id):
                    self.id = user_id
                    self.is_bot = False

            target = FakeUser(target_id)
    else:
        await update.message.reply_text(
            "⚠️ <b>Измена</b>\n\n"
            "Используй одну из команд:\n"
            "• /cheat (ответь на сообщение)\n"
            "• /cheat @username\n\n"
            "⚠️ Риск: 30% что поймают и разведут с конфискацией 50% баланса",
            parse_mode="HTML"
        )
        return

    if target.is_bot or target_id == user_id:
        await update.message.reply_text("Нет")
        return

    with get_db() as db:
        marriage = MarriageService.get_active_marriage(db, user_id)
        if not marriage:
            await update.message.reply_text("Ты не женат/замужем, измена невозможна")
            return

        partner_id = MarriageService.get_partner_id(marriage, user_id)
        partner = db.query(User).filter(User.telegram_id == partner_id).first()

        caught, divorced, fine = MarriageService.cheat(db, user_id, target_id)

        if caught:
            await update.message.reply_text(
                f"💔 <b>ТЕБЯ ПОЙМАЛИ!</b>\n\n"
                f"Супруг/Супруга узнал(а) об измене\n\n"
                f"💔 <b>Развод:</b> Да\n"
                f"💸 <b>Конфискация:</b> {format_diamonds(fine)} (50% баланса)\n"
                f"💰 <b>Супруг получил:</b> {format_diamonds(fine)}\n\n"
                f"@{partner.username or 'Partner'} подал(а) на развод",
                parse_mode="HTML"
            )

            # Notify partner
            try:
                await context.bot.send_message(
                    chat_id=partner_id,
                    text=f"💔 <b>Твой супруг изменил тебе!</b>\n\n"
                         f"Вы разведены\n"
                         f"💰 Получено: {format_diamonds(fine)} (50% его баланса)",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning("Failed to notify partner about cheat", partner_id=partner_id, error=str(e))
        else:
            await update.message.reply_text(
                "🤫 <b>Измена прошла успешно</b>\n\n"
                "Никто ничего не узнал...\n\n"
                "Тебе повезло",
                parse_mode="HTML"
            )

        logger.info("Cheat processed", user_id=user_id, target_id=target_id, caught=caught)


def register_marriage_handlers(application):
    """Register marriage handlers."""
    application.add_handler(CommandHandler("propose", propose_command))
    application.add_handler(CommandHandler("marriage", marriage_command))
    application.add_handler(CommandHandler("gift", gift_command))
    application.add_handler(CommandHandler("makelove", makelove_command))
    application.add_handler(CommandHandler("date", date_command))
    application.add_handler(CommandHandler("cheat", cheat_command))
    application.add_handler(CallbackQueryHandler(propose_callback, pattern="^propose_(accept|reject):"))
    application.add_handler(CallbackQueryHandler(marriage_callback, pattern="^(marriage_|divorce_)"))
