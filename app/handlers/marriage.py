"""Marriage handlers for Wedding Telegram Bot."""

import html
import os
from datetime import datetime, timedelta

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import Cooldown, User
from app.handlers.quest import update_quest_progress
from app.services.marriage_service import DIVORCE_COST, GIFT_MIN, PROPOSE_COST, MarriageService
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds, format_time_remaining
from app.utils.telegram_helpers import safe_edit_message

logger = structlog.get_logger()

# Check if DEBUG mode (DEV environment)
IS_DEBUG = os.environ.get("LOG_LEVEL", "INFO").upper() == "DEBUG"


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
            parse_mode="HTML",
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
        f"<b>{html.escape(proposer_name)}</b> → <b>{html.escape(target_name)}</b>\n\n"
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

    # Check clicker is registered and not banned
    with get_db() as db:
        clicker = db.query(User).filter(User.telegram_id == clicker_id).first()
        if not clicker or clicker.is_banned:
            await query.answer("Доступ запрещён", show_alert=True)
            return

    if action == "propose_accept":
        try:
            with get_db() as db:
                # Double-check conditions
                can_accept, error = MarriageService.can_accept_proposal(db, target_id, proposer_id)
                if not can_accept:
                    await safe_edit_message(query, f"❌ Не получилось: {error}")
                    logger.warning(
                        "Proposal rejected - can't accept", target_id=target_id, proposer_id=proposer_id, error=error
                    )
                    return

                can_propose, error = MarriageService.can_propose(db, proposer_id)
                if not can_propose:
                    await safe_edit_message(query, f"❌ Не получилось: {error}")
                    logger.warning(
                        "Proposal rejected - can't propose", target_id=target_id, proposer_id=proposer_id, error=error
                    )
                    return

                # Create marriage
                marriage = MarriageService.create_marriage(db, proposer_id, target_id)

                proposer = db.query(User).filter(User.telegram_id == proposer_id).first()
                target_user = db.query(User).filter(User.telegram_id == target_id).first()

                # Extract data before session closes
                proposer_username = proposer.username or "User"
                target_username = target_user.username or "User"
                marriage_id = marriage.id

            await safe_edit_message(
                query,
                f"🎉 <b>Поздравляем</b>\n\n"
                f"💍 {proposer_username} и {target_username} — муж и жена\n\n"
                f"💰 Потрачено: {format_diamonds(PROPOSE_COST)}\n\n"
                f"/marriage — управление браком",
            )

            logger.info("Proposal accepted", proposer_id=proposer_id, target_id=target_id, marriage_id=marriage_id)
        except Exception as e:
            logger.error(
                "Failed to accept proposal", proposer_id=proposer_id, target_id=target_id, error=str(e), exc_info=True
            )
            await safe_edit_message(query, "❌ <b>Ошибка</b>\n\nНе удалось создать брак. Попробуй позже")

    elif action == "propose_reject":
        await safe_edit_message(query, "❌ <b>Отказ</b>\n\nВ следующий раз повезет")

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
                parse_mode="HTML",
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
        days_married = (datetime.utcnow() - marriage.created_at).days
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

        await safe_edit_message(
            query,
            f"⚠️ <b>Развод</b>\n\n" f"Точно хочешь развестись?\n\n" f"💰 Стоимость: {format_diamonds(DIVORCE_COST)}",
            reply_markup=reply_markup,
        )

    elif action == "divorce_confirm":
        with get_db() as db:
            success, message, partner_id = MarriageService.divorce(db, owner_id)

            if success:
                settlement_text = "💔 <b>Развод оформлен</b>\n\nБрак расторгнут\n\n"
                settlement_text += f"💰 Потрачено: {format_diamonds(DIVORCE_COST)}"

                # Notify partner about divorce
                if partner_id:
                    try:
                        await context.bot.send_message(
                            chat_id=partner_id,
                            text=f"💔 <b>Развод</b>\n\nТвой супруг развелся с тобой",
                            parse_mode="HTML",
                        )
                    except Exception as e:
                        logger.warning("Failed to notify partner about divorce", partner_id=partner_id, error=str(e))

                await safe_edit_message(query, settlement_text)
            else:
                await safe_edit_message(query, f"❌ {message}")

    elif action == "divorce_cancel":
        # Go back to marriage menu
        await query.answer("Отменено")
        # Re-show marriage menu inline
        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == owner_id).first()
            marriage = MarriageService.get_active_marriage(db, owner_id)
            if marriage:
                partner_id = MarriageService.get_partner_id(marriage, owner_id)
                partner = db.query(User).filter(User.telegram_id == partner_id).first()
                partner_name = partner.username if partner else f"User{partner_id}"
                days_married = (datetime.utcnow() - marriage.created_at).days

                keyboard = [
                    [
                        InlineKeyboardButton("💝 Подарить", callback_data=f"marriage_gift:{owner_id}"),
                        InlineKeyboardButton("💔 Развод", callback_data=f"marriage_divorce:{owner_id}"),
                    ],
                    [
                        InlineKeyboardButton("❤️ Брачная ночь", callback_data=f"marriage_help_love:{owner_id}"),
                        InlineKeyboardButton("📅 Свидание", callback_data=f"marriage_help_date:{owner_id}"),
                    ],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                message = (
                    f"💍 <b>Брак</b>\n\n"
                    f"👫 @{partner_name}\n"
                    f"📅 {days_married} дней\n"
                    f"❤️ Любовь: {marriage.love_count} раз\n\n"
                    f"💰 Ты: {format_diamonds(user.balance)}\n"
                    f"💰 Партнёр: {format_diamonds(partner.balance)}"
                )
                await safe_edit_message(query, message, reply_markup=reply_markup)
            else:
                await safe_edit_message(query, "💔 Не в браке\n\n/propose — сделать предложение")

    elif action == "marriage_gift":
        await safe_edit_message(
            query,
            f"💝 <b>Подарок супругу</b>\n\n"
            f"Использование:\n"
            f"/gift [количество]\n\n"
            f"Минимум {format_diamonds(GIFT_MIN)}",
        )

    elif action == "marriage_help_love":
        # Execute /makelove command inline
        with get_db() as db:
            can_love, error, cooldown = MarriageService.can_make_love(db, owner_id)

            if not can_love:
                if cooldown:
                    time_remaining = format_time_remaining(cooldown)
                    await safe_edit_message(query, f"❤️ <b>Брачная ночь</b>\n\nСледующая попытка через {time_remaining}")
                else:
                    await safe_edit_message(query, error)
                return

            success, conceived, same_gender, can_have_children, requirements_error = MarriageService.make_love(
                db, owner_id
            )

            if not can_have_children:
                # Can't have children - just sex
                message_text = (
                    "❤️ <b>Брачная ночь</b>\n\n"
                    "💑 Просто секс\n\n"
                    "⚠️ Завести детей не получится:\n"
                    f"• {requirements_error}"
                )
                if IS_DEBUG:
                    message_text += "\n\n🔧 <i>Кулдаун убран (DEV)</i>"
                else:
                    message_text += "\n\n⏰ Следующая попытка: через 24 часа"
                await safe_edit_message(query, message_text)
            elif conceived:
                # Conceived successfully
                message_text = (
                    "❤️ <b>Брачная ночь</b>\n\n"
                    "🎉 Поздравляем!\n\n"
                    "👶 Зачатие прошло успешно\n"
                    "🍼 Ребёнок родился в семье\n\n"
                    "💡 Управление семьёй: /family"
                )
                if IS_DEBUG:
                    message_text += "\n\n🔧 <i>Кулдаун убран (DEV)</i>"
                await safe_edit_message(query, message_text)
            else:
                # No conception
                message_text = (
                    "❤️ <b>Брачная ночь</b>\n\n" "💑 Провели время вместе\n\n" "🍀 Зачатие: не произошло (шанс 10%)\n"
                )
                if IS_DEBUG:
                    message_text += "🔧 <i>Кулдаун убран (DEV)</i>"
                else:
                    message_text += "⏰ Следующая попытка: через 24 часа"
                await safe_edit_message(query, message_text)

            logger.info(
                "Make love",
                user_id=owner_id,
                conceived=conceived,
                same_gender=same_gender,
                can_have_children=can_have_children,
            )

    elif action == "marriage_help_date":
        # Execute /date command inline
        with get_db() as db:
            can_date, error, cooldown = MarriageService.can_date(db, owner_id)

            if not can_date:
                if cooldown:
                    time_remaining = format_time_remaining(cooldown)
                    await safe_edit_message(query, f"📅 <b>Свидание</b>\n\nСледующее свидание через {time_remaining}")
                else:
                    await safe_edit_message(query, error)
                return

            earned, location = MarriageService.go_on_date(db, owner_id)

            message_text = (
                f"📅 <b>Свидание</b>\n\n"
                f"❤️ Сходили в {location}\n"
                f"💑 Провели время вместе\n\n"
                f"💰 Заработано: {format_diamonds(earned)}\n\n"
            )
            if IS_DEBUG:
                message_text += "🔧 <i>Кулдаун убран (DEV)</i>"
            else:
                message_text += "⏰ Следующее свидание: через 12 часов"

            await safe_edit_message(query, message_text)

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
            parse_mode="HTML",
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
                await update.message.reply_text(
                    f"❤️ <b>Брачная ночь</b>\n\nСледующая попытка через {time_remaining}", parse_mode="HTML"
                )
            else:
                await update.message.reply_text(error)
            return

        success, conceived, same_gender, can_have_children, requirements_error = MarriageService.make_love(db, user_id)

        if not can_have_children:
            # Can't have children - just sex
            message_text = (
                "❤️ <b>Брачная ночь</b>\n\n"
                "💑 Просто секс\n\n"
                "⚠️ Завести детей не получится:\n"
                f"• {requirements_error}"
            )
            if IS_DEBUG:
                message_text += "\n\n🔧 <i>Кулдаун убран (DEV)</i>"
            else:
                message_text += "\n\n⏰ Следующая попытка: через 24 часа"
            await update.message.reply_text(message_text, parse_mode="HTML")
        elif conceived:
            # Conceived successfully
            message_text = (
                "❤️ <b>Брачная ночь</b>\n\n"
                "🎉 Поздравляем!\n\n"
                "👶 Зачатие прошло успешно\n"
                "🍼 Ребёнок родился в семье\n\n"
                "💡 Управление семьёй: /family"
            )
            if IS_DEBUG:
                message_text += "\n\n🔧 <i>Кулдаун убран (DEV)</i>"
            await update.message.reply_text(message_text, parse_mode="HTML")
        else:
            # No conception
            message_text = (
                "❤️ <b>Брачная ночь</b>\n\n" "💑 Провели время вместе\n\n" "🍀 Зачатие: не произошло (шанс 10%)\n"
            )
            if IS_DEBUG:
                message_text += "🔧 <i>Кулдаун убран (DEV)</i>"
            else:
                message_text += "⏰ Следующая попытка: через 24 часа"
            await update.message.reply_text(message_text, parse_mode="HTML")

        logger.info(
            "Make love",
            user_id=user_id,
            conceived=conceived,
            same_gender=same_gender,
            can_have_children=can_have_children,
        )


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
                await update.message.reply_text(
                    f"📅 <b>Свидание</b>\n\nСледующее свидание через {time_remaining}", parse_mode="HTML"
                )
            else:
                await update.message.reply_text(error)
            return

        earned, location = MarriageService.go_on_date(db, user_id)

        message_text = (
            f"📅 <b>Свидание</b>\n\n"
            f"❤️ Сходили в {location}\n"
            f"💑 Провели время вместе\n\n"
            f"💰 Заработано: {format_diamonds(earned)}\n\n"
        )
        if IS_DEBUG:
            message_text += "🔧 <i>Кулдаун убран (DEV)</i>"
        else:
            message_text += "⏰ Следующее свидание: через 12 часов"

        await update.message.reply_text(message_text, parse_mode="HTML")

        # Track quest progress
        try:
            update_quest_progress(user_id, "marriage")
        except Exception:
            pass

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

        # Check cooldown (6 hours)
        if not IS_DEBUG:
            cheat_cd = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "cheat").first()
            if cheat_cd and cheat_cd.expires_at > datetime.utcnow():
                remaining = cheat_cd.expires_at - datetime.utcnow()
                hours = int(remaining.total_seconds() / 3600)
                minutes = int((remaining.total_seconds() % 3600) / 60)
                time_str = f"{hours}ч {minutes}м" if hours > 0 else f"{minutes}м"
                await update.message.reply_text(f"⏰ Следующая измена через {time_str}")
                return

        partner_id = MarriageService.get_partner_id(marriage, user_id)
        partner = db.query(User).filter(User.telegram_id == partner_id).first()

        caught, divorced, fine = MarriageService.cheat(db, user_id, target_id)

        if caught:
            await update.message.reply_text(
                f"💔 <b>Поймали на измене</b>\n\n"
                f"⚠️ Супруг узнал о твоей измене\n"
                f"💔 Брак расторгнут автоматически\n\n"
                f"💸 Штраф: {format_diamonds(fine)} (50% баланса)\n"
                f"💰 Супруг получил компенсацию: {format_diamonds(fine)}\n\n"
                f"📝 Развод подал: @{partner.username or 'Partner'}",
                parse_mode="HTML",
            )

            # Notify partner
            try:
                await context.bot.send_message(
                    chat_id=partner_id,
                    text=(
                        f"💔 <b>Измена супруга</b>\n\n"
                        f"⚠️ Твой супруг тебе изменил\n"
                        f"💔 Брак расторгнут автоматически\n\n"
                        f"💰 Компенсация получена: {format_diamonds(fine)}\n"
                        f"💸 Это 50% баланса супруга"
                    ),
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.warning("Failed to notify partner about cheat", partner_id=partner_id, error=str(e))
        else:
            await update.message.reply_text(
                "🤫 <b>Измена прошла успешно</b>\n\n"
                "✅ Никто ничего не узнал\n"
                "🎲 Тебе повезло (был риск 30%)\n\n"
                "💡 Но в следующий раз может не повезти...",
                parse_mode="HTML",
            )

        # Set cheat cooldown (6 hours)
        cheat_cd = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "cheat").first()
        expires_at = datetime.utcnow() + timedelta(hours=6)
        if cheat_cd:
            cheat_cd.expires_at = expires_at
        else:
            cheat_cd = Cooldown(user_id=user_id, action="cheat", expires_at=expires_at)
            db.add(cheat_cd)

        logger.info("Cheat processed", user_id=user_id, target_id=target_id, caught=caught)


@require_registered
async def anniversary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /anniversary command."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        can_celebrate, error, cooldown = MarriageService.can_celebrate_anniversary(db, user_id)

        if not can_celebrate:
            if cooldown:
                time_remaining = format_time_remaining(cooldown)
                await update.message.reply_text(
                    f"🎉 <b>Годовщина</b>\n\nСледующая годовщина через {time_remaining}", parse_mode="HTML"
                )
            else:
                await update.message.reply_text(error)
            return

        reward, weeks = MarriageService.celebrate_anniversary(db, user_id)

        message_text = (
            f"🎉 <b>Годовщина свадьбы</b>\n\n"
            f"💑 Вместе {weeks} недель\n"
            f"💰 Награда: {format_diamonds(reward)} каждому\n\n"
        )
        if IS_DEBUG:
            message_text += "🔧 <i>Кулдаун убран (DEV)</i>"
        else:
            message_text += "⏰ Следующая годовщина: через 1 неделю"

        await update.message.reply_text(message_text, parse_mode="HTML")

        logger.info("Anniversary celebrated", user_id=user_id, weeks=weeks, reward=reward)


@require_registered
async def familybank_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /familybank command."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    # Check if has arguments
    if not context.args or len(context.args) == 0:
        # Show balance
        with get_db() as db:
            balance = MarriageService.get_family_bank_balance(db, user_id)

            if balance is None:
                await update.message.reply_text("💔 Ты не женат/замужем")
                return

            await update.message.reply_text(
                f"🏦 <b>Семейный банк</b>\n\n"
                f"💰 Баланс: {format_diamonds(balance)}\n\n"
                f"Команды:\n"
                f"• /familybank deposit [сумма]\n"
                f"• /familybank withdraw [сумма]",
                parse_mode="HTML",
            )
        return

    # Parse action and amount
    action = context.args[0].lower()

    if action not in ("deposit", "withdraw"):
        await update.message.reply_text("❌ Неизвестная команда\n\nИспользуй: deposit или withdraw")
        return

    if len(context.args) < 2:
        await update.message.reply_text(f"❌ Укажи сумму\n\nПример: /familybank {action} 100")
        return

    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Неправильная сумма")
        return

    with get_db() as db:
        if action == "deposit":
            success, message = MarriageService.deposit_to_family_bank(db, user_id, amount)
        else:  # withdraw
            success, message = MarriageService.withdraw_from_family_bank(db, user_id, amount)

        if success:
            balance = MarriageService.get_family_bank_balance(db, user_id)
            await update.message.reply_text(
                f"✅ <b>{message}</b>\n\n" f"🏦 Новый баланс: {format_diamonds(balance)}", parse_mode="HTML"
            )
        else:
            await update.message.reply_text(f"❌ {message}", parse_mode="HTML")


@require_registered
async def adopt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /adopt command."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    # Parse optional child name
    child_name = None
    if context.args and len(context.args) > 0:
        child_name = html.escape(" ".join(context.args).strip())
        # Limit name length
        if len(child_name) > 50:
            await update.message.reply_text("❌ Имя слишком длинное (макс 50 символов)")
            return

    with get_db() as db:
        marriage = MarriageService.get_active_marriage(db, user_id)

        if not marriage:
            await update.message.reply_text("💔 Ты не женат/замужем")
            return

        from app.services.children_service import ADOPTION_COST, ChildrenService

        success, error, child = ChildrenService.adopt_child(db, marriage.id, user_id, child_name)

        if not success:
            await update.message.reply_text(f"❌ <b>Усыновление не удалось</b>\n\n{error}", parse_mode="HTML")
            return

        await update.message.reply_text(
            f"👶 <b>Усыновление</b>\n\n"
            f"✅ Ребёнок усыновлён\n"
            f"📝 Имя: {html.escape(child.name)}\n"
            f"👤 Возраст: Ребёнок\n\n"
            f"💰 Потрачено: {format_diamonds(ADOPTION_COST)}\n\n"
            f"💡 Управление семьёй: /family",
            parse_mode="HTML",
        )

        logger.info("Child adopted", user_id=user_id, child_id=child.id, name=child.name)


@require_registered
async def childwork_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /childwork command."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    # Check if has child_id argument
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "💼 <b>Работа подростка</b>\n\n"
            "Использование:\n"
            "/childwork [ID ребёнка]\n\n"
            "Подростки приносят 20-50 💎 каждые 4 часа автоматически\n\n"
            "Узнать ID: /family",
            parse_mode="HTML",
        )
        return

    try:
        child_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Неправильный ID ребёнка")
        return

    with get_db() as db:
        # Check if child belongs to user
        from app.database.models import Child
        from app.services.children_service import ChildrenService

        child = db.query(Child).filter(Child.id == child_id).first()

        if not child or (child.parent1_id != user_id and child.parent2_id != user_id):
            await update.message.reply_text("❌ Ребёнок не найден или не твой")
            return

        success, error, new_status = ChildrenService.toggle_child_work(db, child_id)

        if not success:
            await update.message.reply_text(f"❌ {error}")
            return

        if new_status:
            await update.message.reply_text(
                f"✅ <b>Работа включена</b>\n\n"
                f"👦 {html.escape(child.name)} начал работать\n"
                f"💰 Заработок: 20-50 💎 каждые 4 часа\n\n"
                f"Деньги будут приходить автоматически",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(
                f"⏸ <b>Работа остановлена</b>\n\n" f"👦 {html.escape(child.name)} больше не работает", parse_mode="HTML"
            )

        logger.info("Child work toggled", user_id=user_id, child_id=child_id, is_working=new_status)


def register_marriage_handlers(application):
    """Register marriage handlers."""
    application.add_handler(CommandHandler("propose", propose_command))
    application.add_handler(CommandHandler("marriage", marriage_command))
    application.add_handler(CommandHandler("gift", gift_command))
    application.add_handler(CommandHandler("makelove", makelove_command))
    application.add_handler(CommandHandler("date", date_command))
    application.add_handler(CommandHandler("cheat", cheat_command))
    application.add_handler(CommandHandler("anniversary", anniversary_command))
    application.add_handler(CommandHandler("familybank", familybank_command))
    application.add_handler(CommandHandler("adopt", adopt_command))
    application.add_handler(CommandHandler("childwork", childwork_command))
    application.add_handler(CallbackQueryHandler(propose_callback, pattern="^propose_"))
    application.add_handler(CallbackQueryHandler(marriage_callback, pattern="^(marriage_|divorce_)"))
