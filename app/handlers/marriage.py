"""Marriage handlers for Wedding Telegram Bot."""

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import User
from app.services.marriage_service import DIVORCE_COST, GIFT_MIN, PROPOSE_COST, MarriageService
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
        username = context.args[0].lstrip("@")

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
            "💍 <b>Предложение руки и сердца</b>\n\n"
            "Как использовать:\n"
            "• /propose (ответь на сообщение)\n"
            "• /propose @username",
            parse_mode="HTML"
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
            InlineKeyboardButton("❌ Отклонить", callback_data=f"propose_reject:{proposer_id}:{target_id}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    proposal_text = (
        f"💍 <b>Предложение руки и сердца</b>\n\n"
        f"<b>{proposer_name}</b> → <b>{target_name}</b>\n\n"
        f"💰 Стоимость: {format_diamonds(PROPOSE_COST)}"
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
        try:
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
                proposer_username = proposer.username or "User"
                target_username = target_user.username or "User"
                marriage_id = marriage.id

            await query.edit_message_text(
                f"🎉 <b>Поздравляем</b>\n\n"
                f"💍 {proposer_username} и {target_username} — муж и жена\n\n"
                f"💰 Потрачено: {PROPOSE_COST} алмазов\n\n"
                f"/marriage — управление браком",
                parse_mode="HTML",
            )

            logger.info("Proposal accepted", proposer_id=proposer_id, target_id=target_id, marriage_id=marriage_id)
        except Exception as e:
            logger.error("Failed to accept proposal", proposer_id=proposer_id, target_id=target_id, error=str(e))
            await query.edit_message_text("❌ Ошибка\n\nВозможно, кто-то уже женат", parse_mode="HTML")

    elif action == "propose_reject":
        await query.edit_message_text("❌ <b>Отказ</b>\n\nВ следующий раз повезет", parse_mode="HTML")

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
                "💔 <b>Не в браке</b>\n\n"
                "Чтобы жениться:\n"
                "• /propose (ответь на сообщение)\n"
                "• /propose @username",
                parse_mode="HTML"
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
                InlineKeyboardButton("💔 Развод", callback_data=f"marriage_divorce:{user_id}"),
            ],
            [
                InlineKeyboardButton("❤️ /makelove", callback_data=f"marriage_help_love:{user_id}"),
                InlineKeyboardButton("📅 /date", callback_data=f"marriage_help_date:{user_id}"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Build message
        days_married = (marriage.created_at - marriage.created_at).days  # Will be calculated properly
        partner_name = partner.username or f"User{partner.telegram_id}"

        message = (
            f"💍 <b>Брак</b>\n\n"
            f"👫 @{partner_name}\n"
            f"📅 Дней: {days_married}\n"
            f"❤️ Любовь: {marriage.love_count} раз\n\n"
            f"💰 Ты: {format_diamonds(user.balance)}\n"
            f"💰 Супруг: {format_diamonds(partner.balance)}"
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
                InlineKeyboardButton("❌ Нет", callback_data=f"divorce_cancel:{owner_id}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"⚠️ <b>Развод</b>\n\n"
            f"Точно хочешь развестись?\n\n"
            f"💰 Стоимость: {format_diamonds(DIVORCE_COST)}",
            reply_markup=reply_markup,
            parse_mode="HTML",
        )

    elif action == "divorce_confirm":
        with get_db() as db:
            success, message = MarriageService.divorce(db, owner_id)

            if success:
                await query.edit_message_text(
                    f"💔 <b>Развод оформлен</b>\n\n"
                    f"Брак расторгнут\n\n"
                    f"💰 Потрачено: {format_diamonds(DIVORCE_COST)}",
                    parse_mode="HTML"
                )
            else:
                await query.edit_message_text(f"❌ {message}", parse_mode="HTML")

    elif action == "divorce_cancel":
        # Go back to marriage menu
        await query.answer("Отменено")
        await marriage_command(update, context)

    elif action == "marriage_gift":
        await query.edit_message_text(
            f"💝 <b>Подарок супругу</b>\n\n"
            f"Использование:\n"
            f"/gift [количество]\n\n"
            f"Минимум {format_diamonds(GIFT_MIN)}",
            parse_mode="HTML"
        )

    elif action == "marriage_help_love":
        # Execute /makelove command inline
        with get_db() as db:
            can_love, error, cooldown = MarriageService.can_make_love(db, owner_id)

            if not can_love:
                if cooldown:
                    time_remaining = format_time_remaining(cooldown)
                    await query.edit_message_text(f"❤️ <b>Брачная ночь</b>\n\nСледующая попытка через {time_remaining}", parse_mode="HTML")
                else:
                    await query.edit_message_text(error, parse_mode="HTML")
                return

            success, conceived, same_gender = MarriageService.make_love(db, owner_id)

            if conceived:
                if same_gender:
                    await query.edit_message_text(
                        "❤️ <b>Любовь</b>\n\n" "🎉 Взяли ребенка из приюта!\n\n" "Ребенок — через 9 дней", parse_mode="HTML"
                    )
                else:
                    await query.edit_message_text(
                        "❤️ <b>Любовь</b>\n\n" "🎉 Зачатие!\n\n" "Ребенок — через 9 дней", parse_mode="HTML"
                    )
            else:
                await query.edit_message_text(
                    "❤️ <b>Любовь</b>\n\n" "Зачатия нет\n\n" "Следующая попытка — через 24 часа", parse_mode="HTML"
                )

            logger.info("Make love", user_id=owner_id, conceived=conceived, same_gender=same_gender)

    elif action == "marriage_help_date":
        # Execute /date command inline
        with get_db() as db:
            can_date, error, cooldown = MarriageService.can_date(db, owner_id)

            if not can_date:
                if cooldown:
                    time_remaining = format_time_remaining(cooldown)
                    await query.edit_message_text(f"📅 <b>Свидание</b>\n\nСледующее свидание через {time_remaining}", parse_mode="HTML")
                else:
                    await query.edit_message_text(error, parse_mode="HTML")
                return

            earned, location = MarriageService.go_on_date(db, owner_id)

            await query.edit_message_text(
                f"📅 <b>Свидание</b>\n\n"
                f"{location}\n\n"
                f"💰 {format_diamonds(earned)}\n\n"
                f"Следующее — через 12 часов",
                parse_mode="HTML",
            )

            logger.info("Date completed", user_id=owner_id, earned=earned, location=location)


@require_registered
async def gift_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /gift command."""
    if not update.effective_user or not update.message or not context.args:
        await update.message.reply_text(
            f"💝 <b>Подарок супругу</b>\n\n"
            f"Использование:\n"
            f"/gift [количество]\n\n"
            f"Минимум {format_diamonds(GIFT_MIN)}",
            parse_mode="HTML"
        )
        return

    user_id = update.effective_user.id

    try:
        amount = int(context.args[0])
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Укажи количество алмазов\n\nПример: /gift 100")
        return

    with get_db() as db:
        success, message = MarriageService.gift_diamonds(db, user_id, amount)

        if success:
            await update.message.reply_text(f"💝 <b>Подарок отправлен</b>\n\n{message}", parse_mode="HTML")
        else:
            await update.message.reply_text(f"❌ {message}", parse_mode="HTML")


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
                await update.message.reply_text(f"❤️ <b>Брачная ночь</b>\n\nСледующая попытка через {time_remaining}", parse_mode="HTML")
            else:
                await update.message.reply_text(error)
            return

        success, conceived, same_gender = MarriageService.make_love(db, user_id)

        if conceived:
            if same_gender:
                await update.message.reply_text(
                    "❤️ <b>Любовь</b>\n\n" "🎉 Взяли ребенка из приюта!\n\n" "Ребенок — через 9 дней", parse_mode="HTML"
                )
            else:
                await update.message.reply_text(
                    "❤️ <b>Любовь</b>\n\n" "🎉 Зачатие!\n\n" "Ребенок — через 9 дней", parse_mode="HTML"
                )
        else:
            await update.message.reply_text(
                "❤️ <b>Любовь</b>\n\n" "Зачатия нет\n\n" "Следующая попытка — через 24 часа", parse_mode="HTML"
            )

        logger.info("Make love", user_id=user_id, conceived=conceived, same_gender=same_gender)


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
                await update.message.reply_text(f"📅 <b>Свидание</b>\n\nСледующее свидание через {time_remaining}", parse_mode="HTML")
            else:
                await update.message.reply_text(error)
            return

        earned, location = MarriageService.go_on_date(db, user_id)

        await update.message.reply_text(
            f"📅 <b>Свидание</b>\n\n"
            f"{location}\n\n"
            f"💰 {format_diamonds(earned)}\n\n"
            f"Следующее — через 12 часов",
            parse_mode="HTML",
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
        username = context.args[0].lstrip("@")

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
            "Как использовать:\n"
            "• /cheat (ответь на сообщение)\n"
            "• /cheat @username\n\n"
            "⚠️ Риск 30%: развод + штраф 50% баланса",
            parse_mode="HTML",
        )
        return

    if target.is_bot or target_id == user_id:
        await update.message.reply_text("Нет")
        return

    with get_db() as db:
        marriage = MarriageService.get_active_marriage(db, user_id)
        if not marriage:
            await update.message.reply_text("Не женат — измена невозможна")
            return

        partner_id = MarriageService.get_partner_id(marriage, user_id)
        partner = db.query(User).filter(User.telegram_id == partner_id).first()

        caught, divorced, fine = MarriageService.cheat(db, user_id, target_id)

        if caught:
            await update.message.reply_text(
                f"💔 <b>Поймали</b>\n\n"
                f"Развод\n\n"
                f"💸 Штраф: {format_diamonds(fine)} (50% баланса)\n"
                f"💰 Супруг получил: {format_diamonds(fine)}\n\n"
                f"@{partner.username or 'Partner'} подал развод",
                parse_mode="HTML",
            )

            # Notify partner
            try:
                await context.bot.send_message(
                    chat_id=partner_id,
                    text=f"💔 <b>Измена</b>\n\n" f"Развод\n" f"💰 Получено: {format_diamonds(fine)} (50% баланса)",
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.warning("Failed to notify partner about cheat", partner_id=partner_id, error=str(e))
        else:
            await update.message.reply_text("🤫 <b>Успех</b>\n\n" "Никто не узнал\n\n" "Повезло", parse_mode="HTML")

        logger.info("Cheat processed", user_id=user_id, target_id=target_id, caught=caught)


def register_marriage_handlers(application):
    """Register marriage handlers."""
    application.add_handler(CommandHandler("propose", propose_command))
    application.add_handler(CommandHandler("marriage", marriage_command))
    application.add_handler(CommandHandler("gift", gift_command))
    application.add_handler(CommandHandler("makelove", makelove_command))
    application.add_handler(CommandHandler("date", date_command))
    application.add_handler(CommandHandler("cheat", cheat_command))
    application.add_handler(CallbackQueryHandler(propose_callback, pattern="^propose_"))
    application.add_handler(CallbackQueryHandler(marriage_callback, pattern="^(marriage_|divorce_)"))
