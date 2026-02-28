"""Social feature handlers (friends, achievements, rating)."""

import html

import structlog
from sqlalchemy import desc, func
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import Achievement, CasinoGame, Friendship, Job, User, UserAchievement
from app.utils.decorators import button_owner_only, require_registered
from app.utils.formatters import format_diamonds, format_word
from app.utils.telegram_helpers import safe_edit_message

logger = structlog.get_logger()


# Constants for achievements
ACHIEVEMENTS_DATA = [
    {"code": "first_steps", "name": "Первые шаги", "description": "Зарегистрировался в боте", "emoji": "👣"},
    {"code": "rich", "name": "Богач", "description": "Накопил 10,000 алмазов", "emoji": "💰"},
    {"code": "tycoon", "name": "Магнат", "description": "Накопил 100,000 алмазов", "emoji": "💎"},
    {"code": "hard_worker", "name": "Трудяга", "description": "Поработал 100 раз", "emoji": "⚒️"},
    {"code": "family_man", "name": "Семьянин", "description": "Женился/вышла замуж", "emoji": "💍"},
    {"code": "parent", "name": "Родитель", "description": "Родил ребёнка", "emoji": "👶"},
    {"code": "businessman", "name": "Бизнесмен", "description": "Купил первый бизнес", "emoji": "🏪"},
    {"code": "empire", "name": "Империя", "description": "Купил 10 бизнесов", "emoji": "🏙️"},
    {"code": "gambler", "name": "Азартный", "description": "Сыграл 100 игр в казино", "emoji": "🎰"},
    {"code": "lucky", "name": "Счастливчик", "description": "Выиграл джекпот в слотах", "emoji": "🍀"},
    {"code": "recruiter", "name": "Рекрутер", "description": "Пригласил первого друга", "emoji": "📨"},
    {"code": "influencer", "name": "Инфлюенсер", "description": "Пригласил 10 друзей", "emoji": "🌟"},
]


def init_achievements():
    """Initialize achievements in database if they don't exist."""
    with get_db() as db:
        for ach_data in ACHIEVEMENTS_DATA:
            existing = db.query(Achievement).filter(Achievement.code == ach_data["code"]).first()
            if not existing:
                achievement = Achievement(
                    code=ach_data["code"],
                    name=ach_data["name"],
                    description=ach_data["description"],
                    emoji=ach_data["emoji"],
                )
                db.add(achievement)
                logger.info("Achievement created", code=ach_data["code"])


def check_and_award_achievement(user_id: int, achievement_code: str, db=None):
    """
    Check and award achievement to user if not already earned.

    Pass an existing db session to avoid opening a nested one.
    """
    from app.services.achievement_service import AchievementService

    return AchievementService.check_and_award(user_id, achievement_code, db=db)


# ==================== FRIENDS ====================


@require_registered
async def friends_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /friends command - show friends list."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        # Get all friendships where user is involved
        friendships = (
            db.query(Friendship)
            .filter(
                ((Friendship.user1_id == user_id) | (Friendship.user2_id == user_id))
                & (Friendship.status == "accepted")
            )
            .all()
        )

        # Get pending requests received
        pending_received = (
            db.query(Friendship).filter(Friendship.user2_id == user_id, Friendship.status == "pending").all()
        )

        # Get pending requests sent
        pending_sent = db.query(Friendship).filter(Friendship.user1_id == user_id, Friendship.status == "pending").all()

        # Batch-load all related user IDs to avoid N+1 queries
        all_user_ids = set()
        for f in friendships:
            all_user_ids.add(f.user2_id if f.user1_id == user_id else f.user1_id)
        for f in pending_received:
            all_user_ids.add(f.user1_id)
        for f in pending_sent:
            all_user_ids.add(f.user2_id)

        users_map = {}
        if all_user_ids:
            users = db.query(User).filter(User.telegram_id.in_(all_user_ids)).all()
            users_map = {u.telegram_id: u for u in users}

        def _display_name(uid):
            u = users_map.get(uid)
            if u and u.username:
                return f"@{html.escape(u.username)}"
            return f"ID {uid}"

        text = "<b>👥 Друзья</b>\n\n"

        if friendships:
            text += "<b>✅ Друзья:</b>\n"
            for friendship in friendships:
                friend_id = friendship.user2_id if friendship.user1_id == user_id else friendship.user1_id
                text += f"• {_display_name(friend_id)}\n"
            text += "\n"

        if pending_received:
            text += "<b>📥 Входящие заявки:</b>\n"
            for friendship in pending_received:
                text += f"• {_display_name(friendship.user1_id)}\n"
            text += "\n"

        if pending_sent:
            text += "<b>📤 Исходящие заявки:</b>\n"
            for friendship in pending_sent:
                text += f"• {_display_name(friendship.user2_id)}\n"
            text += "\n"

        if not friendships and not pending_received and not pending_sent:
            text += "У тебя пока нет друзей\n\n"

        text += "<b>Команды:</b>\n"
        text += "/addfriend @user — добавить в друзья\n"
        text += "/removefriend @user — удалить из друзей"

        # Add accept/decline buttons for pending requests
        keyboard = []
        if pending_received:
            for friendship in pending_received:
                username = _display_name(friendship.user1_id)
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"✅ Принять {username}", callback_data=f"friend:accept:{friendship.id}:{user_id}"
                        ),
                        InlineKeyboardButton(
                            f"❌ Отклонить {username}", callback_data=f"friend:decline:{friendship.id}:{user_id}"
                        ),
                    ]
                )

        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)


@require_registered
async def addfriend_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /addfriend @user command."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    # Parse username
    if not context.args:
        await update.message.reply_text(
            "👥 <b>Добавить в друзья</b>\n\n" "Использование:\n" "/addfriend @username",
            parse_mode="HTML",
        )
        return

    username = context.args[0].lstrip("@")

    with get_db() as db:
        # Get target user
        target = db.query(User).filter(User.username == username).first()

        if not target:
            await update.message.reply_text(f"❌ Пользователь @{username} не найден")
            return

        if target.telegram_id == user_id:
            await update.message.reply_text("❌ Нельзя добавить себя в друзья")
            return

        # Check if already friends or pending
        existing = (
            db.query(Friendship)
            .filter(
                ((Friendship.user1_id == user_id) & (Friendship.user2_id == target.telegram_id))
                | ((Friendship.user1_id == target.telegram_id) & (Friendship.user2_id == user_id))
            )
            .first()
        )

        if existing:
            if existing.status == "accepted":
                await update.message.reply_text(f"❌ @{username} уже в твоих друзьях")
            else:
                await update.message.reply_text(f"❌ Заявка @{username} уже отправлена")
            return

        # Create friendship request
        friendship = Friendship(user1_id=user_id, user2_id=target.telegram_id, status="pending")
        db.add(friendship)

        await update.message.reply_text(
            f"✅ <b>Заявка в друзья отправлена</b>\n\n" f"👤 @{html.escape(username)}", parse_mode="HTML"
        )


@require_registered
async def removefriend_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /removefriend @user command."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    # Parse username
    if not context.args:
        await update.message.reply_text(
            "👥 <b>Удалить из друзей</b>\n\n" "Использование:\n" "/removefriend @username",
            parse_mode="HTML",
        )
        return

    username = context.args[0].lstrip("@")

    with get_db() as db:
        # Get target user
        target = db.query(User).filter(User.username == username).first()

        if not target:
            await update.message.reply_text(f"❌ Пользователь @{username} не найден")
            return

        # Find friendship
        friendship = (
            db.query(Friendship)
            .filter(
                ((Friendship.user1_id == user_id) & (Friendship.user2_id == target.telegram_id))
                | ((Friendship.user1_id == target.telegram_id) & (Friendship.user2_id == user_id))
            )
            .first()
        )

        if not friendship:
            await update.message.reply_text(f"❌ @{username} не в твоих друзьях")
            return

        db.delete(friendship)

        await update.message.reply_text(
            f"✅ <b>Удалено из друзей</b>\n\n" f"👤 @{html.escape(username)}", parse_mode="HTML"
        )


@button_owner_only
async def friend_accept_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle friend request accept callback."""
    query = update.callback_query
    await query.answer()

    try:
        friendship_id = int(query.data.split(":")[2])
    except (ValueError, IndexError):
        return

    with get_db() as db:
        # Ban check
        user = db.query(User).filter(User.telegram_id == update.effective_user.id).first()
        if not user or user.is_banned:
            return

        friendship = db.query(Friendship).filter(Friendship.id == friendship_id).first()

        if not friendship:
            await safe_edit_message(query, "❌ Заявка не найдена")
            return

        friendship.status = "accepted"

        sender = db.query(User).filter(User.telegram_id == friendship.user1_id).first()
        username = f"@{html.escape(sender.username)}" if sender and sender.username else f"ID {friendship.user1_id}"

        await safe_edit_message(query, f"✅ <b>Заявка принята</b>\n\n👤 {username}\n\nТеперь друзья!")


@button_owner_only
async def friend_decline_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle friend request decline callback."""
    query = update.callback_query
    await query.answer()

    try:
        friendship_id = int(query.data.split(":")[2])
    except (ValueError, IndexError):
        return

    with get_db() as db:
        # Ban check
        user = db.query(User).filter(User.telegram_id == update.effective_user.id).first()
        if not user or user.is_banned:
            await safe_edit_message(query, "❌ Доступ запрещён")
            return

        friendship = db.query(Friendship).filter(Friendship.id == friendship_id).first()

        if not friendship:
            await safe_edit_message(query, "❌ Заявка не найдена")
            return

        sender = db.query(User).filter(User.telegram_id == friendship.user1_id).first()
        username = f"@{html.escape(sender.username)}" if sender and sender.username else f"ID {friendship.user1_id}"

        db.delete(friendship)

        await safe_edit_message(query, f"❌ <b>Заявка отклонена</b>\n\n👤 {username}")


# ==================== GIFT (to friends only) ====================

FRIENDGIFT_FEE_RATE = 2  # 2% fee (reduced from 5% for regular /transfer)


@require_registered
async def gift_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /friendgift @user amount command (only for friends, reduced fee)."""
    if not update.effective_user or not update.message:
        return

    sender_id = update.effective_user.id

    # Parse arguments
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "🎁 <b>Подарить алмазы другу</b>\n\n"
            "Использование:\n"
            "/friendgift @username [сумма]\n\n"
            "Минимум: 10 алмазов\n"
            f"Комиссия: {FRIENDGIFT_FEE_RATE}% (для друзей)\n\n"
            "Пример: /friendgift @user 100",
            parse_mode="HTML",
        )
        return

    # Parse username and amount
    username = context.args[0].lstrip("@")
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Сумма должна быть числом")
        return

    # Validate amount
    if amount < 10:
        await update.message.reply_text("❌ Минимум 10 алмазов")
        return

    fee = max(1, int(amount * FRIENDGIFT_FEE_RATE / 100))
    total_cost = amount + fee

    with get_db() as db:
        # Get sender
        sender = db.query(User).filter(User.telegram_id == sender_id).first()

        # Check balance (amount + fee)
        if sender.balance < total_cost:
            await update.message.reply_text(
                f"❌ Недостаточно алмазов\n\n"
                f"💰 Подарок: {format_diamonds(amount)}\n"
                f"💸 Комиссия: {format_diamonds(fee)}\n"
                f"📊 Итого: {format_diamonds(total_cost)}\n\n"
                f"💰 Твой баланс: {format_diamonds(sender.balance)}"
            )
            return

        # Get recipient
        recipient = db.query(User).filter(User.username == username).first()

        if not recipient:
            await update.message.reply_text(f"❌ Пользователь @{html.escape(username)} не найден", parse_mode="HTML")
            return

        # Can't gift to self
        if sender_id == recipient.telegram_id:
            await update.message.reply_text("❌ Нельзя подарить себе")
            return

        # Check friendship
        friendship = (
            db.query(Friendship)
            .filter(
                ((Friendship.user1_id == sender_id) & (Friendship.user2_id == recipient.telegram_id))
                | ((Friendship.user1_id == recipient.telegram_id) & (Friendship.user2_id == sender_id)),
                Friendship.status == "accepted",
            )
            .first()
        )

        if not friendship:
            await update.message.reply_text(
                f"❌ @{html.escape(username)} не в твоих друзьях\n\nДарить можно только друзьям", parse_mode="HTML"
            )
            return

        # Execute gift (deduct amount + fee from sender, give amount to recipient)
        sender.balance -= total_cost
        recipient.balance += amount

        balance = sender.balance

    await update.message.reply_text(
        f"🎁 <b>Подарок отправлен</b>\n\n"
        f"💰 {format_diamonds(amount)} → @{html.escape(username)}\n"
        f"💸 Комиссия: {format_diamonds(fee)}\n\n"
        f"💰 Твой баланс: {format_diamonds(balance)}",
        parse_mode="HTML",
    )


# ==================== ACHIEVEMENTS ====================


@require_registered
async def achievements_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /achievements command."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        # Check and award any new achievements before displaying
        from app.services.achievement_service import AchievementService

        try:
            AchievementService.check_all_achievements(user_id, db=db)
            db.flush()
        except Exception:
            pass

        # Get all achievements
        all_achievements = db.query(Achievement).all()

        # Get user's achievements
        user_achievements = db.query(UserAchievement).filter(UserAchievement.user_id == user_id).all()
        earned_ids = {ua.achievement_id for ua in user_achievements}

        text = "<b>🏆 Достижения</b>\n\n"

        # Count
        total = len(all_achievements)
        earned_count = len(earned_ids)
        text += f"<b>Прогресс: {earned_count}/{total}</b>\n\n"

        # List achievements
        for ach in all_achievements:
            if ach.id in earned_ids:
                text += f"✅ {ach.emoji} <b>{ach.name}</b>\n"
                text += f"   {ach.description}\n\n"
            else:
                text += f"🔒 {ach.emoji} <b>{ach.name}</b>\n"
                text += f"   {ach.description}\n\n"

    await update.message.reply_text(text, parse_mode="HTML")


# ==================== RATING ====================


def rating_keyboard(user_id: int, category: str = "balance") -> InlineKeyboardMarkup:
    """Build keyboard for rating categories."""
    categories = [
        ("💰 Баланс", "balance"),
        ("⚒️ Работы", "works"),
        ("🎰 Казино", "casino"),
    ]

    keyboard = []
    for name, code in categories:
        if code == category:
            keyboard.append([InlineKeyboardButton(f"✅ {name}", callback_data="noop")])
        else:
            keyboard.append([InlineKeyboardButton(name, callback_data=f"rating:{code}:{user_id}")])

    return InlineKeyboardMarkup(keyboard)


@require_registered
async def rating_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /rating command — redirect to /top."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    from app.handlers.start import build_top_message

    text, reply_markup = build_top_message("balance", user_id)
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)


async def show_rating(message, user_id: int, category: str):
    """Show rating by category."""
    with get_db() as db:
        text = "<b>📊 Рейтинг</b>\n\n"

        if category == "balance":
            text += "<b>💰 По балансу</b>\n\n"
            top_users = db.query(User).order_by(desc(User.balance)).limit(10).all()
            for idx, user in enumerate(top_users, 1):
                username = f"@{html.escape(user.username)}" if user.username else f"ID {user.telegram_id}"
                text += f"{idx}. {username} — {format_diamonds(user.balance)}\n"

        elif category == "reputation":
            text += "<b>⭐ По репутации</b>\n\n"
            top_users = db.query(User).order_by(desc(User.reputation)).limit(10).all()
            for idx, user in enumerate(top_users, 1):
                username = f"@{html.escape(user.username)}" if user.username else f"ID {user.telegram_id}"
                text += f"{idx}. {username} — {user.reputation:+d}\n"

        elif category == "works":
            text += "<b>⚒️ По количеству работ</b>\n\n"
            top_jobs = db.query(Job).order_by(desc(Job.times_worked)).limit(10).all()
            for idx, job in enumerate(top_jobs, 1):
                user = db.query(User).filter(User.telegram_id == job.user_id).first()
                if user:
                    username = f"@{html.escape(user.username)}" if user.username else f"ID {user.telegram_id}"
                    text += f"{idx}. {username} — {format_word(job.times_worked, 'работа', 'работы', 'работ')}\n"

        elif category == "casino":
            text += "<b>🎰 По выигрышам в казино</b>\n\n"
            # Sum total winnings per user
            casino_stats = (
                db.query(CasinoGame.user_id, func.sum(CasinoGame.payout).label("total_payout"))
                .filter(CasinoGame.result == "win")
                .group_by(CasinoGame.user_id)
                .order_by(desc("total_payout"))
                .limit(10)
                .all()
            )
            for idx, (user_id_stat, total_payout) in enumerate(casino_stats, 1):
                user = db.query(User).filter(User.telegram_id == user_id_stat).first()
                if user:
                    username = f"@{html.escape(user.username)}" if user.username else f"ID {user.telegram_id}"
                    text += f"{idx}. {username} — {format_diamonds(total_payout)}\n"

    keyboard = rating_keyboard(user_id, category)
    await message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)


@button_owner_only
async def rating_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle rating category switch callback."""
    query = update.callback_query
    await query.answer()

    category = query.data.split(":")[1]

    with get_db() as db:
        text = "<b>📊 Рейтинг</b>\n\n"

        if category == "balance":
            text += "<b>💰 По балансу</b>\n\n"
            top_users = db.query(User).order_by(desc(User.balance)).limit(10).all()
            for idx, user in enumerate(top_users, 1):
                username = f"@{html.escape(user.username)}" if user.username else f"ID {user.telegram_id}"
                text += f"{idx}. {username} — {format_diamonds(user.balance)}\n"

        elif category == "works":
            text += "<b>⚒️ По количеству работ</b>\n\n"
            top_jobs = db.query(Job).order_by(desc(Job.times_worked)).limit(10).all()
            for idx, job in enumerate(top_jobs, 1):
                user = db.query(User).filter(User.telegram_id == job.user_id).first()
                if user:
                    username = f"@{html.escape(user.username)}" if user.username else f"ID {user.telegram_id}"
                    text += f"{idx}. {username} — {format_word(job.times_worked, 'работа', 'работы', 'работ')}\n"

        elif category == "casino":
            text += "<b>🎰 По выигрышам в казино</b>\n\n"
            casino_stats = (
                db.query(CasinoGame.user_id, func.sum(CasinoGame.payout).label("total_payout"))
                .filter(CasinoGame.result == "win")
                .group_by(CasinoGame.user_id)
                .order_by(desc("total_payout"))
                .limit(10)
                .all()
            )
            for idx, (user_id_stat, total_payout) in enumerate(casino_stats, 1):
                user = db.query(User).filter(User.telegram_id == user_id_stat).first()
                if user:
                    username = f"@{html.escape(user.username)}" if user.username else f"ID {user.telegram_id}"
                    text += f"{idx}. {username} — {format_diamonds(total_payout)}\n"

    user_id = int(query.data.split(":")[2])
    keyboard = rating_keyboard(user_id, category)
    await safe_edit_message(query, text, reply_markup=keyboard)


# ==================== REGISTER HANDLERS ====================


def register_social_handlers(application):
    """Register social feature handlers."""
    # Initialize achievements
    init_achievements()

    # Friends
    application.add_handler(CommandHandler("friends", friends_command))
    application.add_handler(CommandHandler("addfriend", addfriend_command))
    application.add_handler(CommandHandler("removefriend", removefriend_command))
    application.add_handler(CallbackQueryHandler(friend_accept_callback, pattern=r"^friend:accept:"))
    application.add_handler(CallbackQueryHandler(friend_decline_callback, pattern=r"^friend:decline:"))

    # Gift
    application.add_handler(CommandHandler("friendgift", gift_command))

    # Achievements
    application.add_handler(CommandHandler("achievements", achievements_command))

    # Rating
    application.add_handler(CommandHandler("rating", rating_command))
    application.add_handler(CallbackQueryHandler(rating_callback, pattern=r"^rating:"))
