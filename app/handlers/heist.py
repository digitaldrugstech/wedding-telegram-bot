"""Cooperative bank heist — multiplayer PvE minigame."""

import asyncio
import html
import random
from datetime import datetime, timedelta

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import Cooldown, User
from app.handlers.quest import update_quest_progress
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds

logger = structlog.get_logger()

HEIST_JOIN_TIMEOUT_SECONDS = 120
HEIST_COOLDOWN_HOURS = 6
HEIST_MIN_PLAYERS = 2
HEIST_MAX_PLAYERS = 8

HEIST_TIERS = {
    "easy": {
        "name": "Лёгкое",
        "emoji": "🟢",
        "entry_fee": 200,
        "base_success": 60,
        "player_bonus": 5,
        "max_success": 85,
        "payout_min": 250,
        "payout_max": 350,
    },
    "medium": {
        "name": "Среднее",
        "emoji": "🟡",
        "entry_fee": 500,
        "base_success": 45,
        "player_bonus": 5,
        "max_success": 75,
        "payout_min": 700,
        "payout_max": 1100,
    },
    "hard": {
        "name": "Сложное",
        "emoji": "🔴",
        "entry_fee": 1000,
        "base_success": 30,
        "player_bonus": 7,
        "max_success": 65,
        "payout_min": 1800,
        "payout_max": 2800,
    },
}

# Active heists: {chat_id: {tier, players: {uid: username}, host_id, created_at}}
active_heists = {}

HEIST_ANIMATIONS = [
    "🏦 Подъезжаете к банку...",
    "🏦 Отключаете камеры...\n🔧 ████░░░░░░",
    "🏦 Вскрываете хранилище...\n🔧 ████████░░",
    "🏦 Грузите алмазы...\n💎💎💎💎💎",
    "🚨 СИГНАЛИЗАЦИЯ!\n🚨🚨🚨🚨🚨",
]


@require_registered
async def heist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /heist [easy|medium|hard] — start a cooperative bank heist."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not context.args:
        tiers_text = ""
        for key, tier in HEIST_TIERS.items():
            chance = f"{tier['base_success']}%-{tier['max_success']}%"
            tiers_text += (
                f"{tier['emoji']} <b>{tier['name']}</b> ({key})\n"
                f"   Вход: {format_diamonds(tier['entry_fee'])}\n"
                f"   Выигрыш: {format_diamonds(tier['payout_min'])}-{format_diamonds(tier['payout_max'])}\n"
                f"   Шанс: {chance}\n\n"
            )

        await update.message.reply_text(
            f"🏦 <b>Ограбление банка</b>\n\n"
            f"/heist [easy|medium|hard] — начать\n\n"
            f"• Кооперативная игра на 2-{HEIST_MAX_PLAYERS} человек\n"
            f"• Чем больше участников, тем выше шанс\n"
            f"• Провал = все теряют вход\n"
            f"• Кулдаун: {HEIST_COOLDOWN_HOURS}ч\n\n"
            f"<b>Уровни:</b>\n\n{tiers_text}",
            parse_mode="HTML",
        )
        return

    tier_key = context.args[0].lower()
    if tier_key not in HEIST_TIERS:
        await update.message.reply_text(f"❌ Неизвестный уровень\n\nДоступные: easy, medium, hard")
        return

    tier = HEIST_TIERS[tier_key]
    entry_fee = tier["entry_fee"]

    if chat_id in active_heists:
        await update.message.reply_text("❌ В этом чате уже идёт ограбление")
        return

    with get_db() as db:
        # Check cooldown
        cooldown = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "heist").first()
        if cooldown and cooldown.expires_at > datetime.utcnow():
            remaining = cooldown.expires_at - datetime.utcnow()
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            time_parts = []
            if hours > 0:
                time_parts.append(f"{hours}ч")
            if minutes > 0:
                time_parts.append(f"{minutes}м")
            await update.message.reply_text(f"⏰ Следующее ограбление через {' '.join(time_parts)}")
            return

        # Check and deduct balance
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user or user.balance < entry_fee:
            await update.message.reply_text(
                f"❌ Недостаточно алмазов\n\nВход: {format_diamonds(entry_fee)}\n"
                f"У тебя: {format_diamonds(user.balance if user else 0)}"
            )
            return

        user.balance -= entry_fee

    username = html.escape(update.effective_user.username or update.effective_user.first_name or f"User{user_id}")

    active_heists[chat_id] = {
        "tier_key": tier_key,
        "tier": tier,
        "players": {user_id: username},
        "host_id": user_id,
        "created_at": datetime.utcnow(),
    }

    chance = tier["base_success"]
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"🏦 Войти ({format_diamonds(entry_fee)})", callback_data=f"heist:join:{chat_id}")],
            [InlineKeyboardButton("🚀 НАЧАТЬ!", callback_data=f"heist:go:{chat_id}:{user_id}")],
        ]
    )

    await update.message.reply_text(
        f"🏦 <b>ОГРАБЛЕНИЕ!</b>\n\n"
        f"{tier['emoji']} Уровень: <b>{tier['name']}</b>\n"
        f"💰 Вход: {format_diamonds(entry_fee)}\n"
        f"🎯 Шанс: {chance}%\n\n"
        f"👥 Участники (1/{HEIST_MAX_PLAYERS}):\n"
        f"• @{username}\n\n"
        f"⏰ {HEIST_JOIN_TIMEOUT_SECONDS // 60} мин на сбор\n"
        f"Нужно минимум {HEIST_MIN_PLAYERS} участника\n\n"
        f"<i>Организатор жмёт «НАЧАТЬ!» когда все готовы</i>",
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    logger.info("Heist started", user_id=user_id, chat_id=chat_id, tier=tier_key)


async def heist_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle heist join button."""
    query = update.callback_query
    if not query or not update.effective_user:
        return

    user_id = update.effective_user.id
    parts = query.data.split(":")
    chat_id = int(parts[2])

    if chat_id not in active_heists:
        await query.answer("❌ Ограбление уже завершено", show_alert=True)
        return

    heist = active_heists[chat_id]

    # Check timeout
    elapsed = (datetime.utcnow() - heist["created_at"]).total_seconds()
    if elapsed > HEIST_JOIN_TIMEOUT_SECONDS:
        _refund_all(heist)
        del active_heists[chat_id]
        await query.answer("❌ Время вышло, ставки возвращены", show_alert=True)
        return

    if user_id in heist["players"]:
        await query.answer("Ты уже в команде!", show_alert=True)
        return

    if len(heist["players"]) >= HEIST_MAX_PLAYERS:
        await query.answer("❌ Команда полная!", show_alert=True)
        return

    tier = heist["tier"]
    entry_fee = tier["entry_fee"]

    # Check registration, ban, and balance
    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            await query.answer("❌ Ты не зарегистрирован — /start", show_alert=True)
            return
        if user.is_banned:
            await query.answer("❌ Ты забанен", show_alert=True)
            return

        # Check cooldown
        cooldown = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "heist").first()
        if cooldown and cooldown.expires_at > datetime.utcnow():
            await query.answer("❌ У тебя кулдаун на ограбления", show_alert=True)
            return

        if user.balance < entry_fee:
            await query.answer(f"❌ Нужно {format_diamonds(entry_fee)}", show_alert=True)
            return
        user.balance -= entry_fee

    username = html.escape(update.effective_user.username or update.effective_user.first_name or f"User{user_id}")
    heist["players"][user_id] = username
    count = len(heist["players"])
    chance = min(tier["max_success"], tier["base_success"] + (count - 1) * tier["player_bonus"])

    await query.answer(f"Ты в команде! ({count} чел, {chance}% шанс)")

    # Update message
    player_list = "\n".join(f"• @{name}" for name in heist["players"].values())
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"🏦 Войти ({format_diamonds(entry_fee)})", callback_data=f"heist:join:{chat_id}")],
            [InlineKeyboardButton("🚀 НАЧАТЬ!", callback_data=f"heist:go:{chat_id}:{heist['host_id']}")],
        ]
    )

    try:
        await query.edit_message_text(
            f"🏦 <b>ОГРАБЛЕНИЕ!</b>\n\n"
            f"{tier['emoji']} Уровень: <b>{tier['name']}</b>\n"
            f"💰 Вход: {format_diamonds(entry_fee)}\n"
            f"🎯 Шанс: {chance}%\n\n"
            f"👥 Участники ({count}/{HEIST_MAX_PLAYERS}):\n"
            f"{player_list}\n\n"
            f"<i>Организатор жмёт «НАЧАТЬ!» когда все готовы</i>",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except BadRequest:
        pass

    logger.info("Heist player joined", user_id=user_id, chat_id=chat_id, count=count)


async def heist_go_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle heist start button — execute the heist."""
    query = update.callback_query
    if not query or not update.effective_user:
        return

    user_id = update.effective_user.id
    parts = query.data.split(":")
    chat_id = int(parts[2])
    host_id = int(parts[3])

    if user_id != host_id:
        await query.answer("❌ Только организатор может начать", show_alert=True)
        return

    if chat_id not in active_heists:
        await query.answer("❌ Ограбление уже завершено", show_alert=True)
        return

    heist = active_heists.pop(chat_id)
    players = heist["players"]
    tier = heist["tier"]
    count = len(players)

    await query.answer()

    if count < HEIST_MIN_PLAYERS:
        _refund_all(heist)
        try:
            await query.edit_message_text(
                f"❌ <b>Ограбление отменено</b>\n\n"
                f"Недостаточно участников: {count}/{HEIST_MIN_PLAYERS}\n"
                f"Ставки возвращены",
                parse_mode="HTML",
            )
        except BadRequest:
            pass
        return

    # Animation
    try:
        for frame in HEIST_ANIMATIONS:
            await query.edit_message_text(frame)
            await asyncio.sleep(0.8)
    except BadRequest:
        pass

    # Calculate result
    chance = min(tier["max_success"], tier["base_success"] + (count - 1) * tier["player_bonus"])
    success = random.randint(1, 100) <= chance

    entry_fee = tier["entry_fee"]
    player_ids = list(players.keys())

    if success:
        # Each player gets individual random payout
        payouts = {}
        with get_db() as db:
            for pid in player_ids:
                payout = random.randint(tier["payout_min"], tier["payout_max"])
                payouts[pid] = payout
                player_user = db.query(User).filter(User.telegram_id == pid).first()
                if player_user:
                    player_user.balance += payout

            # Set cooldown for all
            expires_at = datetime.utcnow() + timedelta(hours=HEIST_COOLDOWN_HOURS)
            for pid in player_ids:
                cd = db.query(Cooldown).filter(Cooldown.user_id == pid, Cooldown.action == "heist").first()
                if cd:
                    cd.expires_at = expires_at
                else:
                    db.add(Cooldown(user_id=pid, action="heist", expires_at=expires_at))

        total_stolen = sum(payouts.values())
        player_lines = []
        for pid in player_ids:
            name = players[pid]
            profit = payouts[pid] - entry_fee
            player_lines.append(f"  💰 @{name}: +{format_diamonds(profit)} чистыми")

        result_text = (
            f"🏦💰 <b>ОГРАБЛЕНИЕ ВЕКА!</b>\n\n"
            f"✅ Вы ворвались в банк и ушли с добычей!\n\n"
            f"👥 Участников: {count} (шанс был {chance}%)\n\n"
            + "\n".join(player_lines)
            + f"\n\n💎 Всего украдено: {format_diamonds(total_stolen)}"
        )
    else:
        # Failure — entry fees burned (already deducted)
        total_lost = entry_fee * count

        with get_db() as db:
            # Set cooldown for all
            expires_at = datetime.utcnow() + timedelta(hours=HEIST_COOLDOWN_HOURS)
            for pid in player_ids:
                cd = db.query(Cooldown).filter(Cooldown.user_id == pid, Cooldown.action == "heist").first()
                if cd:
                    cd.expires_at = expires_at
                else:
                    db.add(Cooldown(user_id=pid, action="heist", expires_at=expires_at))

        result_text = (
            f"🚨 <b>ПРОВАЛ!</b>\n\n"
            f"Сработала сигнализация — охрана вас поймала!\n\n"
            f"👥 Участников: {count} (шанс был {chance}%)\n"
            f"💸 Потеряно: {format_diamonds(total_lost)} (по {format_diamonds(entry_fee)} с каждого)\n\n"
            f"<i>Попробуйте снова через {HEIST_COOLDOWN_HOURS}ч</i>"
        )

    try:
        await query.edit_message_text(result_text, parse_mode="HTML")
    except BadRequest:
        pass

    # Track quest progress for participants
    for pid in player_ids:
        try:
            update_quest_progress(pid, "casino")
        except Exception:
            pass

    logger.info(
        "Heist completed",
        chat_id=chat_id,
        tier=heist["tier_key"],
        players=count,
        success=success,
        chance=chance,
    )


def _refund_all(heist: dict):
    """Refund all players in a heist."""
    entry_fee = heist["tier"]["entry_fee"]
    with get_db() as db:
        for pid in heist["players"]:
            user = db.query(User).filter(User.telegram_id == pid).first()
            if user:
                user.balance += entry_fee


def register_heist_handlers(application):
    """Register heist handlers."""
    application.add_handler(CommandHandler("heist", heist_command))
    application.add_handler(CallbackQueryHandler(heist_join_callback, pattern=r"^heist:join:"))
    application.add_handler(CallbackQueryHandler(heist_go_callback, pattern=r"^heist:go:"))
    logger.info("Heist handlers registered")
