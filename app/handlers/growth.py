"""Growth & viral features — new chat tracking, invite rewards, welcome messages."""

import html
import os
from datetime import datetime

import structlog
from telegram import ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ChatMemberHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import ChatActivity, User
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds
from app.utils.telegram_helpers import safe_edit_message

logger = structlog.get_logger()

ADMIN_USER_ID = int(os.environ.get("ADMIN_USER_ID", "710573786"))
INVITE_REWARD = 500  # diamonds for inviting bot to a new group
MIN_USERS_FOR_REWARD = 3  # group must have 3+ members for reward


# ==================== MY_CHAT_MEMBER — detect add/remove ====================


def _extract_status_change(chat_member_update: ChatMemberUpdated):
    """Extract whether the bot was added or removed."""
    old = chat_member_update.old_chat_member
    new = chat_member_update.new_chat_member

    old_is_member = old.status in ("member", "administrator", "creator")
    new_is_member = new.status in ("member", "administrator", "creator")

    if not old_is_member and new_is_member:
        return "added"
    elif old_is_member and not new_is_member:
        return "removed"
    return None


async def track_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bot being added to or removed from a chat."""
    if not update.my_chat_member:
        return

    change = _extract_status_change(update.my_chat_member)
    if not change:
        return

    chat = update.my_chat_member.chat
    inviter = update.my_chat_member.from_user

    if change == "added" and chat.type in ("group", "supergroup"):
        chat_title = html.escape(chat.title or "Без названия")
        inviter_name = ""
        if inviter:
            inviter_name = f"@{html.escape(inviter.username)}" if inviter.username else f"ID {inviter.id}"

        # Track in DB
        is_new = False
        with get_db() as db:
            activity = db.query(ChatActivity).filter(ChatActivity.chat_id == chat.id).first()
            if not activity:
                activity = ChatActivity(
                    chat_id=chat.id,
                    title=chat.title or "Unknown",
                    chat_type=chat.type,
                    command_count=0,
                )
                db.add(activity)
                is_new = True
            else:
                activity.title = chat.title or activity.title
                activity.last_active_at = datetime.utcnow()

        # Notify admin about new chat
        try:
            admin_text = (
                f"{'🆕' if is_new else '🔄'} <b>Бот добавлен в чат</b>\n\n"
                f"💬 {chat_title}\n"
                f"🆔 <code>{chat.id}</code>\n"
                f"👤 Пригласил: {inviter_name}\n"
                f"📝 Тип: {chat.type}"
            )
            await context.bot.send_message(chat_id=ADMIN_USER_ID, text=admin_text, parse_mode="HTML")
        except Exception as e:
            logger.warning("Failed to notify admin about new chat", error=str(e))

        # Reward inviter (only for new chats)
        if is_new and inviter and not inviter.is_bot:
            with get_db() as db:
                user = db.query(User).filter(User.telegram_id == inviter.id).first()
                if user and not user.is_banned:
                    user.balance += INVITE_REWARD
                    try:
                        await context.bot.send_message(
                            chat_id=inviter.id,
                            text=(
                                f"🎉 <b>Награда за приглашение!</b>\n\n"
                                f"Ты добавил бота в <b>{chat_title}</b>\n"
                                f"💎 +{format_diamonds(INVITE_REWARD)}\n\n"
                                f"💡 Добавляй бота в другие чаты и получай награды!"
                            ),
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass  # User might have blocked DM

        # Send welcome message to the group
        try:
            welcome = (
                "👋 <b>Привет!</b>\n\n"
                "Я — бот для симуляции жизни 💍\n\n"
                "Работа, брак, дети, казино, банды и многое другое!\n\n"
                "🚀 Начни: /start\n"
                "📋 Команды: /help\n"
                "🎰 Игры: /casino\n\n"
                "💡 Добавьте меня в другие чаты — весь прогресс общий!"
            )
            await context.bot.send_message(chat_id=chat.id, text=welcome, parse_mode="HTML")
        except Exception as e:
            logger.warning("Failed to send welcome", chat_id=chat.id, error=str(e))

        logger.info("Bot added to chat", chat_id=chat.id, title=chat.title, inviter=inviter_name, is_new=is_new)

    elif change == "removed":
        chat_title = html.escape(chat.title or "???")
        try:
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=f"🚫 <b>Бот удалён из чата</b>\n\n💬 {chat_title}\n🆔 <code>{chat.id}</code>",
                parse_mode="HTML",
            )
        except Exception:
            pass

        logger.info("Bot removed from chat", chat_id=chat.id, title=chat.title)


# ==================== /invite — viral sharing ====================


@require_registered
async def invite_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show invite link and stats."""
    if not update.effective_user or not update.message:
        return

    bot_username = (await context.bot.get_me()).username

    # Count how many chats this user invited the bot to (approximate — check chat activity)
    text = (
        f"📢 <b>Пригласи бота в чат!</b>\n\n"
        f"Добавь бота в любой групповой чат и получи <b>{format_diamonds(INVITE_REWARD)}</b> за каждый новый чат!\n\n"
        f"🔗 Ссылка для добавления:\n"
        f"<code>https://t.me/{bot_username}?startgroup=true</code>\n\n"
        f"💡 Весь прогресс общий — играй в любом чате!\n"
        f"🏆 Топ чатов: /topchats"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "➕ Добавить в чат",
                    url=f"https://t.me/{bot_username}?startgroup=true",
                )
            ]
        ]
    )

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)


# ==================== ADMIN /dashboard ====================


@require_registered
async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin dashboard with full stats."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    from app.config import config

    if user_id != config.admin_user_id:
        return

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📊 Обзор", callback_data=f"dash:overview:{user_id}"),
                InlineKeyboardButton("💰 Экономика", callback_data=f"dash:economy:{user_id}"),
            ],
            [
                InlineKeyboardButton("💬 Чаты", callback_data=f"dash:chats:{user_id}"),
                InlineKeyboardButton("⭐ Донаты", callback_data=f"dash:donates:{user_id}"),
            ],
            [
                InlineKeyboardButton("🏆 Топы", callback_data=f"dash:tops:{user_id}"),
                InlineKeyboardButton("📈 Активность", callback_data=f"dash:activity:{user_id}"),
            ],
        ]
    )

    await update.message.reply_text("🎛 <b>Дашборд</b>\n\nВыбери раздел:", parse_mode="HTML", reply_markup=keyboard)


async def dashboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle dash:* callbacks."""
    query = update.callback_query
    if not query or not update.effective_user:
        return

    parts = query.data.split(":")
    action = parts[1]
    owner_id = int(parts[2])
    user_id = update.effective_user.id

    if user_id != owner_id:
        await query.answer("Нет доступа", show_alert=True)
        return

    from app.config import config

    if user_id != config.admin_user_id:
        return

    await query.answer()
    back_btn = InlineKeyboardButton("« Назад", callback_data=f"dash:menu:{user_id}")

    if action == "menu":
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("📊 Обзор", callback_data=f"dash:overview:{user_id}"),
                    InlineKeyboardButton("💰 Экономика", callback_data=f"dash:economy:{user_id}"),
                ],
                [
                    InlineKeyboardButton("💬 Чаты", callback_data=f"dash:chats:{user_id}"),
                    InlineKeyboardButton("⭐ Донаты", callback_data=f"dash:donates:{user_id}"),
                ],
                [
                    InlineKeyboardButton("🏆 Топы", callback_data=f"dash:tops:{user_id}"),
                    InlineKeyboardButton("📈 Активность", callback_data=f"dash:activity:{user_id}"),
                ],
            ]
        )
        await safe_edit_message(query, "🎛 <b>Дашборд</b>\n\nВыбери раздел:", reply_markup=keyboard)

    elif action == "overview":
        text = _build_overview()
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup([[back_btn]]))

    elif action == "economy":
        text = _build_economy()
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup([[back_btn]]))

    elif action == "chats":
        text = _build_chats()
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup([[back_btn]]))

    elif action == "donates":
        text = _build_donates()
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup([[back_btn]]))

    elif action == "tops":
        text = _build_tops()
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup([[back_btn]]))

    elif action == "activity":
        text = _build_activity()
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup([[back_btn]]))


# ==================== DASHBOARD DATA BUILDERS ====================


def _build_overview() -> str:
    from app.database.models import Business, CasinoGame, Child, Gang, Marriage, Pet

    with get_db() as db:
        total_users = db.query(User).count()
        banned = db.query(User).filter(User.is_banned.is_(True)).count()
        marriages = db.query(Marriage).filter(Marriage.is_active.is_(True)).count()
        children = db.query(Child).filter(Child.is_alive.is_(True)).count()
        businesses = db.query(Business).count()
        pets = db.query(Pet).filter(Pet.is_alive.is_(True)).count()
        gangs = db.query(Gang).count()
        chats = db.query(ChatActivity).count()
        group_chats = db.query(ChatActivity).filter(ChatActivity.chat_type.in_(["group", "supergroup"])).count()

        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        new_today = db.query(User).filter(User.created_at >= today).count()
        casino_today = db.query(CasinoGame).filter(CasinoGame.played_at >= today).count()

    return (
        f"📊 <b>Обзор</b>\n\n"
        f"👥 Игроков: <b>{total_users}</b> (🆕 {new_today} сегодня)\n"
        f"🚫 Забанено: {banned}\n"
        f"💬 Чатов: <b>{group_chats}</b> групп ({chats} всего)\n\n"
        f"💍 Браков: {marriages}\n"
        f"👶 Детей: {children}\n"
        f"💼 Бизнесов: {businesses}\n"
        f"🐾 Питомцев: {pets}\n"
        f"⚔️ Банд: {gangs}\n\n"
        f"🎰 Казино сегодня: {casino_today}"
    )


def _build_economy() -> str:
    from app.database.models import Business, StarPurchase

    with get_db() as db:
        from sqlalchemy.sql import func

        total_diamonds = db.query(func.sum(User.balance)).scalar() or 0
        avg_balance = db.query(func.avg(User.balance)).scalar() or 0
        max_balance = db.query(func.max(User.balance)).scalar() or 0
        median_q = db.query(User.balance).order_by(User.balance).all()
        median = median_q[len(median_q) // 2][0] if median_q else 0

        richest = db.query(User).order_by(User.balance.desc()).first()
        richest_name = richest.username or f"ID {richest.telegram_id}" if richest else "—"
        richest_bal = richest.balance if richest else 0

        total_biz_count = db.query(Business).count()
        total_stars = db.query(func.sum(StarPurchase.stars_amount)).scalar() or 0
        total_donate_diamonds = db.query(func.sum(StarPurchase.diamonds_granted)).scalar() or 0

    return (
        f"💰 <b>Экономика</b>\n\n"
        f"💎 В обороте: <b>{format_diamonds(total_diamonds)}</b>\n"
        f"📊 Средний баланс: {format_diamonds(int(avg_balance))}\n"
        f"📈 Медиана: {format_diamonds(median)}\n"
        f"🏆 Максимум: {format_diamonds(max_balance)}\n"
        f"👑 Богатейший: @{html.escape(richest_name)} ({format_diamonds(richest_bal)})\n\n"
        f"💼 Бизнесов: {total_biz_count}\n"
        f"⭐ Всего звёзд: {total_stars}\n"
        f"💎 Донат-алмазов: {format_diamonds(total_donate_diamonds)}"
    )


def _build_chats() -> str:
    with get_db() as db:
        chats = (
            db.query(ChatActivity)
            .filter(ChatActivity.chat_type.in_(["group", "supergroup"]))
            .order_by(ChatActivity.command_count.desc())
            .limit(15)
            .all()
        )

        rows = []
        for c in chats:
            title = html.escape(c.title or "???")
            rows.append(f"{title}: <b>{c.command_count}</b> cmd")

        total = db.query(ChatActivity).filter(ChatActivity.chat_type.in_(["group", "supergroup"])).count()

    text = f"💬 <b>Чаты</b> ({total} групп)\n\n"
    if rows:
        text += "\n".join(f"{i}. {r}" for i, r in enumerate(rows, 1))
    else:
        text += "Нет данных"
    return text


def _build_donates() -> str:
    from app.database.models import StarPurchase

    with get_db() as db:
        from sqlalchemy.sql import func

        total_purchases = db.query(StarPurchase).count()
        total_stars = db.query(func.sum(StarPurchase.stars_amount)).scalar() or 0
        total_diamonds = db.query(func.sum(StarPurchase.diamonds_granted)).scalar() or 0
        unique_donors = db.query(func.count(func.distinct(StarPurchase.user_id))).scalar() or 0

        # Top donors
        top_donors = (
            db.query(
                StarPurchase.user_id,
                func.sum(StarPurchase.stars_amount).label("total"),
            )
            .group_by(StarPurchase.user_id)
            .order_by(func.sum(StarPurchase.stars_amount).desc())
            .limit(10)
            .all()
        )

        donor_rows = []
        for d in top_donors:
            user = db.query(User).filter(User.telegram_id == d.user_id).first()
            name = f"@{html.escape(user.username)}" if user and user.username else f"ID {d.user_id}"
            donor_rows.append(f"{name}: <b>{d.total}⭐</b>")

        # Recent purchases
        recent = db.query(StarPurchase).order_by(StarPurchase.created_at.desc()).limit(5).all()
        recent_rows = []
        for p in recent:
            user = db.query(User).filter(User.telegram_id == p.user_id).first()
            name = f"@{html.escape(user.username)}" if user and user.username else f"ID {p.user_id}"
            recent_rows.append(f"{name}: {p.stars_amount}⭐ ({p.product})")

    text = (
        f"⭐ <b>Донаты</b>\n\n"
        f"Покупок: <b>{total_purchases}</b>\n"
        f"Звёзд: <b>{total_stars}⭐</b>\n"
        f"Алмазов выдано: <b>{format_diamonds(total_diamonds)}</b>\n"
        f"Доноров: <b>{unique_donors}</b>\n\n"
    )

    if donor_rows:
        text += "<b>Топ доноров:</b>\n"
        text += "\n".join(f"{i}. {r}" for i, r in enumerate(donor_rows, 1))
        text += "\n\n"

    if recent_rows:
        text += "<b>Последние:</b>\n"
        text += "\n".join(f"• {r}" for r in recent_rows)

    return text


def _build_tops() -> str:
    with get_db() as db:
        # Top by balance
        rich = db.query(User).order_by(User.balance.desc()).limit(5).all()
        rich_rows = []
        for u in rich:
            name = f"@{html.escape(u.username)}" if u.username else f"ID {u.telegram_id}"
            rich_rows.append(f"{name}: {format_diamonds(u.balance)}")

        # Top by reputation
        rep = db.query(User).filter(User.reputation > 0).order_by(User.reputation.desc()).limit(5).all()
        rep_rows = []
        for u in rep:
            name = f"@{html.escape(u.username)}" if u.username else f"ID {u.telegram_id}"
            rep_rows.append(f"{name}: {u.reputation}⭐")

        # Top by streak
        streak = db.query(User).filter(User.daily_streak > 0).order_by(User.daily_streak.desc()).limit(5).all()
        streak_rows = []
        for u in streak:
            name = f"@{html.escape(u.username)}" if u.username else f"ID {u.telegram_id}"
            streak_rows.append(f"{name}: {u.daily_streak}🔥")

        # Top by prestige
        prestige = db.query(User).filter(User.prestige_level > 0).order_by(User.prestige_level.desc()).limit(5).all()
        prest_rows = []
        for u in prestige:
            name = f"@{html.escape(u.username)}" if u.username else f"ID {u.telegram_id}"
            prest_rows.append(f"{name}: P{u.prestige_level}")

    text = "🏆 <b>Топы</b>\n\n"
    text += "<b>💎 Баланс:</b>\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(rich_rows, 1)) + "\n\n"
    if rep_rows:
        text += "<b>⭐ Репутация:</b>\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(rep_rows, 1)) + "\n\n"
    if streak_rows:
        text += "<b>🔥 Серия:</b>\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(streak_rows, 1)) + "\n\n"
    if prest_rows:
        text += "<b>🔄 Престиж:</b>\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(prest_rows, 1))

    return text


def _build_activity() -> str:
    from app.database.models import CasinoGame

    with get_db() as db:
        from sqlalchemy.sql import func

        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        new_users_today = db.query(User).filter(User.created_at >= today).count()
        active_today = db.query(ChatActivity).filter(ChatActivity.last_active_at >= today).count()
        casino_today = db.query(CasinoGame).filter(CasinoGame.played_at >= today).count()

        # Users who did /daily today
        daily_today = db.query(User).filter(User.last_daily_at >= today).count()

        # Total commands today (sum of command_count increases — approximate)
        total_cmds = db.query(func.sum(ChatActivity.command_count)).scalar() or 0

        # Active streaks
        streakers = db.query(User).filter(User.daily_streak >= 7).count()

    return (
        f"📈 <b>Активность</b>\n\n"
        f"🆕 Новых сегодня: <b>{new_users_today}</b>\n"
        f"💬 Активных чатов: <b>{active_today}</b>\n"
        f"📋 /daily сегодня: <b>{daily_today}</b>\n"
        f"🎰 Казино сегодня: <b>{casino_today}</b>\n"
        f"🔥 Серия 7+: <b>{streakers}</b>\n\n"
        f"📊 Всего команд (все время): {total_cmds}"
    )


# ==================== REGISTER ====================


def register_growth_handlers(application):
    """Register growth handlers."""
    # my_chat_member — bot added/removed from groups
    application.add_handler(ChatMemberHandler(track_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    # Commands
    application.add_handler(CommandHandler("invite", invite_command))
    application.add_handler(CommandHandler("dashboard", dashboard_command))

    # Dashboard callbacks
    application.add_handler(CallbackQueryHandler(dashboard_callback, pattern=r"^dash:"))

    logger.info("Growth handlers registered")
