"""Admin commands for bot management."""

import asyncio
import html

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import Business, ChatActivity, Child, Cooldown, Marriage, User
from app.utils.decorators import admin_only, admin_only_private
from app.utils.formatters import format_diamonds
from app.utils.telegram_helpers import safe_edit_message

logger = structlog.get_logger()

# Maintenance mode flag (in-memory)
MAINTENANCE_MODE = False


@admin_only
async def reset_cooldown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset cooldown for a user (admin only)."""
    if not update.effective_user or not update.message:
        return

    # Check if replying to someone
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_user_id = update.message.reply_to_message.from_user.id
        target_username = (
            update.message.reply_to_message.from_user.username or update.message.reply_to_message.from_user.first_name
        )
    else:
        # Reset own cooldown
        target_user_id = update.effective_user.id
        target_username = update.effective_user.username or update.effective_user.first_name

    with get_db() as db:
        # Delete all cooldowns for the user
        deleted_count = db.query(Cooldown).filter(Cooldown.user_id == target_user_id).delete()


        if deleted_count > 0:
            await update.message.reply_text(
                f"✅ Сброшено {deleted_count} кулдаунов\n{target_username} (ID: {target_user_id})"
            )
        else:
            await update.message.reply_text(f"⚠️ Нет активных кулдаунов\n{target_username} (ID: {target_user_id})")


@admin_only_private
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin menu (private only)."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data=f"admin:stats:{user_id}")],
        [InlineKeyboardButton("👤 Управление пользователями", callback_data=f"admin:users:{user_id}")],
        [InlineKeyboardButton("📢 Рассылка", callback_data=f"admin:broadcast:{user_id}")],
        [InlineKeyboardButton("🔧 Maintenance", callback_data=f"admin:maintenance:{user_id}")],
        [InlineKeyboardButton("💾 Backup", callback_data=f"admin:backup:{user_id}")],
        [InlineKeyboardButton("📋 Логи", callback_data=f"admin:logs:{user_id}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    maintenance_status = "🔴 Включён" if MAINTENANCE_MODE else "🟢 Выключен"

    await update.message.reply_text(
        f"🔐 <b>Админ панель</b>\n\n" f"Maintenance: {maintenance_status}\n\n" f"Выбери действие:",
        reply_markup=reply_markup,
        parse_mode="HTML",
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot statistics (available for all users)."""
    if not update.effective_user or not update.message:
        return

    from datetime import datetime, timedelta

    from app.database.models import CasinoGame

    with get_db() as db:
        # Count users
        total_users = db.query(User).count()
        active_marriages = db.query(Marriage).filter(Marriage.is_active.is_(True)).count()
        total_children = db.query(Child).filter(Child.is_alive.is_(True)).count()
        dead_children = db.query(Child).filter(Child.is_alive.is_(False)).count()
        total_businesses = db.query(Business).count()

        # Total diamonds
        from sqlalchemy.sql import func

        total_diamonds = db.query(func.sum(User.balance)).scalar() or 0

        # Casino stats - today only
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        casino_games_today = db.query(CasinoGame).filter(CasinoGame.played_at >= today_start).count()

        # Top 10 richest — extract plain values inside session
        top_users = [
            (u.username or f"User{u.telegram_id}", u.balance)
            for u in db.query(User).order_by(User.balance.desc()).limit(10).all()
        ]

    message = (
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Игроков: {total_users}\n"
        f"💍 Браков: {active_marriages}\n"
        f"👶 Детей: {total_children}\n"
        f"💀 Мёртвых детей: {dead_children}\n"
        f"💼 Бизнесов: {total_businesses}\n"
        f"💰 Алмазов в экономике: {format_diamonds(total_diamonds)}\n"
        f"🎰 Игр в казино за сегодня: {casino_games_today}\n\n"
        f"<b>Топ 10 богатых:</b>\n"
    )

    for i, (username, balance) in enumerate(top_users, 1):
        message += f"{i}. @{html.escape(username)} — {format_diamonds(balance)}\n"

    await update.message.reply_text(message, parse_mode="HTML")


@admin_only_private
async def user_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed user info."""
    if not update.effective_user or not update.message:
        return
    if not context.args:
        await update.message.reply_text(
            "👤 <b>Информация о пользователе</b>\n\n"
            "Использование:\n"
            "/user_info [telegram_id]\n\n"
            "Пример: /user_info 123456789",
            parse_mode="HTML",
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Неверный ID")
        return

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == target_id).first()

        if not user:
            await update.message.reply_text(f"❌ Пользователь {target_id} не найден")
            return

        # Get marriage
        marriage = (
            db.query(Marriage)
            .filter(
                (Marriage.partner1_id == target_id) | (Marriage.partner2_id == target_id),
                Marriage.is_active.is_(True),
            )
            .first()
        )

        # Get children
        children_count = (
            db.query(Child)
            .filter((Child.parent1_id == target_id) | (Child.parent2_id == target_id), Child.is_alive.is_(True))
            .count()
        )

        # Get businesses
        businesses_count = db.query(Business).filter(Business.user_id == target_id).count()

        message = (
            f"👤 <b>Пользователь {user.telegram_id}</b>\n\n"
            f"Username: @{html.escape(user.username or 'нет')}\n"
            f"Пол: {user.gender or 'не выбран'}\n"
            f"💰 Баланс: {format_diamonds(user.balance)}\n"
            f"🚫 Забанен: {'Да' if user.is_banned else 'Нет'}\n"
            f"📅 Регистрация: {user.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
            f"💍 В браке: {'Да' if marriage else 'Нет'}\n"
            f"👶 Детей: {children_count}\n"
            f"💼 Бизнесов: {businesses_count}"
        )

        await update.message.reply_text(message, parse_mode="HTML")


@admin_only
async def give_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Give diamonds to user (works with @username or telegram_id)."""
    if not update.effective_user or not update.message:
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "💰 <b>Выдать алмазы</b>\n\n"
            "Использование:\n"
            "/give @username [amount]\n"
            "/give [telegram_id] [amount]\n\n"
            "Примеры:\n"
            "/give @user 1000\n"
            "/give 123456789 1000",
            parse_mode="HTML",
        )
        return

    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Сумма должна быть числом")
        return

    if amount <= 0:
        await update.message.reply_text("❌ Сумма должна быть больше 0")
        return

    with get_db() as db:
        # Check if first arg is @username or telegram_id
        target_input = context.args[0].lstrip("@")

        # Try as username first
        user = db.query(User).filter(User.username == target_input).first()

        # If not found, try as telegram_id
        if not user:
            try:
                target_id = int(context.args[0])
                user = db.query(User).filter(User.telegram_id == target_id).first()
            except ValueError:
                await update.message.reply_text(f"❌ Пользователь @{target_input} не найден")
                return

        if not user:
            await update.message.reply_text(f"❌ Пользователь {context.args[0]} не найден")
            return

        user.balance += amount


        await update.message.reply_text(
            f"✅ Выдано {format_diamonds(amount)}\n"
            f"@{user.username or user.telegram_id}\n"
            f"Новый баланс: {format_diamonds(user.balance)}"
        )

        logger.info(
            "Admin gave diamonds",
            admin_id=update.effective_user.id,
            target_id=user.telegram_id,
            target_username=user.username,
            amount=amount,
        )


@admin_only_private
async def take_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Take diamonds from user."""
    if not update.effective_user or not update.message:
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "💰 <b>Забрать алмазы</b>\n\n"
            "Использование:\n"
            "/take [telegram_id] [amount]\n\n"
            "Пример: /take 123456789 500",
            parse_mode="HTML",
        )
        return

    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Неверные параметры")
        return

    if amount <= 0:
        await update.message.reply_text("❌ Сумма должна быть больше 0")
        return

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == target_id).first()

        if not user:
            await update.message.reply_text(f"❌ Пользователь {target_id} не найден")
            return

        user.balance = max(0, user.balance - amount)


        await update.message.reply_text(
            f"✅ Забрано {format_diamonds(amount)}\n"
            f"@{user.username or target_id}\n"
            f"Новый баланс: {format_diamonds(user.balance)}"
        )

        logger.info("Admin took diamonds", admin_id=update.effective_user.id, target_id=target_id, amount=amount)


@admin_only
async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ban user (works with @username or telegram_id, optional reason)."""
    if not update.effective_user or not update.message:
        return
    if not context.args:
        await update.message.reply_text(
            "🚫 <b>Забанить пользователя</b>\n\n"
            "Использование:\n"
            "/ban @username [причина]\n"
            "/ban [telegram_id] [причина]\n\n"
            "Примеры:\n"
            "/ban @user читерство\n"
            "/ban 123456789",
            parse_mode="HTML",
        )
        return

    # Get reason if provided
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "Не указана"

    with get_db() as db:
        # Check if first arg is @username or telegram_id
        target_input = context.args[0].lstrip("@")

        # Try as username first
        user = db.query(User).filter(User.username == target_input).first()

        # If not found, try as telegram_id
        if not user:
            try:
                target_id = int(context.args[0])
                user = db.query(User).filter(User.telegram_id == target_id).first()
            except ValueError:
                await update.message.reply_text(f"❌ Пользователь @{target_input} не найден")
                return

        if not user:
            await update.message.reply_text(f"❌ Пользователь {context.args[0]} не найден")
            return

        user.is_banned = True


        await update.message.reply_text(
            f"✅ Пользователь @{user.username or user.telegram_id} забанен\n\n" f"Причина: {reason}"
        )

        logger.info(
            "Admin banned user",
            admin_id=update.effective_user.id,
            target_id=user.telegram_id,
            target_username=user.username,
            reason=reason,
        )


@admin_only
async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unban user (works with @username or telegram_id)."""
    if not update.effective_user or not update.message:
        return
    if not context.args:
        await update.message.reply_text(
            "✅ <b>Разбанить пользователя</b>\n\n"
            "Использование:\n"
            "/unban @username\n"
            "/unban [telegram_id]\n\n"
            "Примеры:\n"
            "/unban @user\n"
            "/unban 123456789",
            parse_mode="HTML",
        )
        return

    with get_db() as db:
        # Check if first arg is @username or telegram_id
        target_input = context.args[0].lstrip("@")

        # Try as username first
        user = db.query(User).filter(User.username == target_input).first()

        # If not found, try as telegram_id
        if not user:
            try:
                target_id = int(context.args[0])
                user = db.query(User).filter(User.telegram_id == target_id).first()
            except ValueError:
                await update.message.reply_text(f"❌ Пользователь @{target_input} не найден")
                return

        if not user:
            await update.message.reply_text(f"❌ Пользователь {context.args[0]} не найден")
            return

        user.is_banned = False


        await update.message.reply_text(f"✅ Пользователь @{user.username or user.telegram_id} разбанен")

        logger.info(
            "Admin unbanned user",
            admin_id=update.effective_user.id,
            target_id=user.telegram_id,
            target_username=user.username,
        )


@admin_only_private
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast message to all users."""
    if not update.effective_user or not update.message:
        return
    if not context.args:
        await update.message.reply_text(
            "📢 <b>Рассылка</b>\n\n" "Использование:\n" "/broadcast [message]\n\n" "Пример: /broadcast Привет всем!",
            parse_mode="HTML",
        )
        return

    message_text = " ".join(context.args)

    with get_db() as db:
        user_ids = [u.telegram_id for u in db.query(User).filter(User.is_banned.is_(False)).all()]

    sent_count = 0
    failed_count = 0

    for user_id in user_ids:
        try:
            await context.bot.send_message(chat_id=user_id, text=message_text, parse_mode="HTML")
            sent_count += 1
        except Exception as e:
            failed_count += 1
            logger.warning("Failed to send broadcast", user_id=user_id, error=str(e))
        await asyncio.sleep(0.05)  # Rate limit: 20 msg/sec

    await update.message.reply_text(
        f"📢 <b>Рассылка завершена</b>\n\n" f"✅ Отправлено: {sent_count}\n" f"❌ Ошибок: {failed_count}",
        parse_mode="HTML",
    )

    logger.info("Broadcast completed", admin_id=update.effective_user.id, sent=sent_count, failed=failed_count)


@admin_only_private
async def maintenance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle maintenance mode."""
    global MAINTENANCE_MODE

    if not update.effective_user or not update.message:
        return
    if not context.args:
        status = "включён" if MAINTENANCE_MODE else "выключен"
        await update.message.reply_text(
            f"🔧 <b>Режим обслуживания</b>\n\n"
            f"Статус: {status}\n\n"
            f"Использование:\n"
            f"/maintenance on - включить\n"
            f"/maintenance off - выключить",
            parse_mode="HTML",
        )
        return

    action = context.args[0].lower()

    if action == "on":
        MAINTENANCE_MODE = True
        await update.message.reply_text("🔴 Режим обслуживания включён\nБот доступен только админу")
        logger.info("Maintenance mode enabled", admin_id=update.effective_user.id)
    elif action == "off":
        MAINTENANCE_MODE = False
        await update.message.reply_text("🟢 Режим обслуживания выключен\nБот доступен всем")
        logger.info("Maintenance mode disabled", admin_id=update.effective_user.id)
    else:
        await update.message.reply_text("❌ Используй: /maintenance on|off")


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin menu callbacks."""
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

    if action == "stats":
        # Build stats inline for callback (stats_command requires update.message)
        from datetime import datetime

        from app.database.models import CasinoGame

        with get_db() as db:
            total_users = db.query(User).count()
            active_marriages = db.query(Marriage).filter(Marriage.is_active.is_(True)).count()
            total_children = db.query(Child).filter(Child.is_alive.is_(True)).count()
            total_businesses = db.query(Business).count()

            from sqlalchemy.sql import func

            total_diamonds = db.query(func.sum(User.balance)).scalar() or 0

            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            casino_games_today = db.query(CasinoGame).filter(CasinoGame.played_at >= today_start).count()

        stats_text = (
            f"📊 <b>Статистика</b>\n\n"
            f"👥 Игроков: {total_users}\n"
            f"💍 Браков: {active_marriages}\n"
            f"👶 Детей: {total_children}\n"
            f"💼 Бизнесов: {total_businesses}\n"
            f"💰 В экономике: {format_diamonds(total_diamonds)}\n"
            f"🎰 Казино сегодня: {casino_games_today}"
        )
        await safe_edit_message(query, stats_text)

    elif action == "users":
        await safe_edit_message(
            query,
            "👤 <b>Управление пользователями</b>\n\n"
            "Команды:\n"
            "/user_info [id] - информация\n"
            "/give [id] [amount] - выдать💎\n"
            "/take [id] [amount] - забрать💎\n"
            "/ban [id] - забанить\n"
            "/unban [id] - разбанить",
        )

    elif action == "broadcast":
        await safe_edit_message(query, "📢 <b>Рассылка</b>\n\n" "Команда:\n" "/broadcast [текст сообщения]")

    elif action == "maintenance":
        status = "🔴 Включён" if MAINTENANCE_MODE else "🟢 Выключен"
        await safe_edit_message(
            query,
            f"🔧 <b>Режим обслуживания</b>\n\n"
            f"Статус: {status}\n\n"
            f"Команды:\n"
            f"/maintenance on - включить\n"
            f"/maintenance off - выключить",
        )

    elif action == "backup":
        await safe_edit_message(
            query, "💾 <b>Backup</b>\n\n" "⚠️ Функция в разработке\n\n" "Используй pg_dump для бэкапа PostgreSQL"
        )

    elif action == "logs":
        await safe_edit_message(
            query,
            "📋 <b>Логи</b>\n\n"
            "⚠️ Функция в разработке\n\n"
            "Используй docker logs wedding-bot-dev для просмотра логов",
        )


@admin_only
async def chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /chats — show all chats where bot is active (admin only)."""
    if not update.effective_user or not update.message:
        return

    with get_db() as db:
        chats = db.query(ChatActivity).order_by(ChatActivity.command_count.desc()).all()

        if not chats:
            await update.message.reply_text("Нет данных о чатах. Трекинг только начался.")
            return

        text = "💬 <b>Чаты бота</b>\n\n"
        for i, c in enumerate(chats, 1):
            title = html.escape(c.title or f"ID {c.chat_id}")
            text += (
                f"{i}. <b>{title}</b>\n"
                f"   ID: <code>{c.chat_id}</code>\n"
                f"   Команд: {c.command_count}\n"
                f"   Тип: {c.chat_type}\n\n"
            )

    await update.message.reply_text(text, parse_mode="HTML")


async def topchats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /topchats — show most active chats (public)."""
    if not update.effective_user or not update.message:
        return

    with get_db() as db:
        chats = db.query(ChatActivity).order_by(ChatActivity.command_count.desc()).limit(10).all()

        if not chats:
            await update.message.reply_text("📊 Пока нет данных о чатах")
            return

        rows = []
        for i, c in enumerate(chats, 1):
            title = html.escape(c.title or "???")
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            rows.append(f"{medal} {title} — {c.command_count} команд")

    text = "💬 <b>Топ чатов</b>\n\n" + "\n".join(rows)
    await update.message.reply_text(text, parse_mode="HTML")


@admin_only_private
async def announce_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Announce to all tracked group chats, pin only in production chat."""
    if not update.effective_user or not update.message:
        return
    if not context.args:
        await update.message.reply_text(
            "📢 <b>Анонс во все чаты</b>\n\n"
            "Использование:\n"
            "/announce [текст в HTML]\n\n"
            "Отправляет во все отслеживаемые чаты\n"
            "Закрепляет только в продовом",
            parse_mode="HTML",
        )
        return

    from app.constants import PRODUCTION_CHAT_ID

    message_text = " ".join(context.args)

    # Get all tracked group chats
    with get_db() as db:
        chats = db.query(ChatActivity).filter(ChatActivity.chat_type.in_(["group", "supergroup"])).all()
        chat_ids = [c.chat_id for c in chats]

    if not chat_ids:
        await update.message.reply_text("Нет отслеживаемых чатов")
        return

    sent_count = 0
    failed_count = 0
    pinned = False

    for chat_id in chat_ids:
        try:
            result = await context.bot.send_message(chat_id=chat_id, text=message_text, parse_mode="HTML")
            sent_count += 1

            # Pin only in production chat
            if chat_id == PRODUCTION_CHAT_ID:
                try:
                    await context.bot.pin_chat_message(chat_id=chat_id, message_id=result.message_id)
                    pinned = True
                except Exception as e:
                    logger.warning("Failed to pin announcement", chat_id=chat_id, error=str(e))
        except Exception as e:
            failed_count += 1
            logger.warning("Failed to send announcement", chat_id=chat_id, error=str(e))
        await asyncio.sleep(0.1)

    pin_status = "📌 Закреплено в проде" if pinned else "⚠️ Не закреплено в проде"
    await update.message.reply_text(
        f"📢 <b>Анонс отправлен</b>\n\n"
        f"✅ Чатов: {sent_count}\n"
        f"❌ Ошибок: {failed_count}\n"
        f"{pin_status}",
        parse_mode="HTML",
    )

    logger.info("Announcement sent", admin_id=update.effective_user.id, sent=sent_count, failed=failed_count, pinned=pinned)


def register_admin_handlers(application):
    """Register admin handlers."""
    application.add_handler(CommandHandler("reset_cd", reset_cooldown_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("user_info", user_info_command))
    application.add_handler(CommandHandler("give", give_command))
    application.add_handler(CommandHandler("take", take_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("unban", unban_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("maintenance", maintenance_command))
    application.add_handler(CommandHandler("chats", chats_command))
    application.add_handler(CommandHandler("topchats", topchats_command))
    application.add_handler(CommandHandler("announce", announce_command))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin:"))
