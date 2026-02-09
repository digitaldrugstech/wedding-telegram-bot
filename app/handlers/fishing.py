"""Fishing minigame handler — catch fish, sell or collect."""

import asyncio
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

BAIT_COST = 20
FISHING_COOLDOWN_MINUTES = 30

# Fish rarities and catch rates (total = 100%)
# EV: ~19.25 per cast vs 20 bait = ~4% house edge
FISH = [
    # (name, emoji, sell_price, chance%)
    ("Карась", "🐟", 2, 25),
    ("Окунь", "🐟", 5, 20),
    ("Щука", "🐠", 10, 15),
    ("Сом", "🐠", 15, 10),
    ("Форель", "🐡", 25, 8),
    ("Лосось", "🐡", 35, 7),
    ("Осётр", "🦈", 50, 5),
    ("Тунец", "🦈", 70, 4),
    ("Рыба-меч", "⚔️", 100, 3),
    ("Золотая рыбка", "✨", 100, 2),
    ("Ботинок", "👢", 0, 1),  # Junk — lose bait
]
# Total: 25+20+15+10+8+7+5+4+3+2+1 = 100%

# Animation frames
CAST_ANIMATIONS = [
    "🎣 Забрасываешь удочку...",
    "🎣 Удочка в воде...\n🌊 ~~ ~~ ~~",
    "🎣 Ждёшь...\n🌊 ~~ 🐟? ~~ ~~",
    "🎣 Что-то клюёт!\n🌊 ~~ ‼️ ~~ ~~",
    "🎣 Тянешь!\n💪 ~~ ~~ ~~",
]


def catch_fish():
    """Roll for a fish catch based on probability weights."""
    roll = random.randint(1, 100)
    cumulative = 0
    for name, emoji, price, chance in FISH:
        cumulative += chance
        if roll <= cumulative:
            return name, emoji, price
    # Fallback (shouldn't reach)
    return FISH[0][0], FISH[0][1], FISH[0][2]


async def animate_fishing(msg):
    """Play fishing animation by editing message."""
    for frame in CAST_ANIMATIONS:
        await asyncio.sleep(0.8)
        try:
            await msg.edit_text(frame)
        except BadRequest:
            pass


@require_registered
async def fishing_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /fish command."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            return

        # Check cooldown
        cooldown = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "fishing").first()
        if cooldown and cooldown.expires_at > datetime.utcnow():
            remaining = cooldown.expires_at - datetime.utcnow()
            minutes = int(remaining.total_seconds() // 60)
            seconds = int(remaining.total_seconds() % 60)
            if minutes > 0:
                await update.message.reply_text(f"⏰ Следующая рыбалка через {minutes}м {seconds}с")
            else:
                await update.message.reply_text(f"⏰ Следующая рыбалка через {seconds}с")
            return

        # Check balance for bait
        if user.balance < BAIT_COST:
            await update.message.reply_text(
                f"❌ Нужна наживка!\n\n"
                f"Стоимость: {format_diamonds(BAIT_COST)}\n"
                f"У тебя: {format_diamonds(user.balance)}"
            )
            return

        # Pay for bait
        user.balance -= BAIT_COST

        # Catch fish
        fish_name, fish_emoji, sell_price = catch_fish()

        # Apply double income boost
        from app.handlers.premium import has_active_boost

        if has_active_boost(user_id, "double_income"):
            sell_price *= 2

        # Add sell price to balance
        user.balance += sell_price

        # Set cooldown
        expires_at = datetime.utcnow() + timedelta(minutes=FISHING_COOLDOWN_MINUTES)
        if cooldown:
            cooldown.expires_at = expires_at
        else:
            db.add(Cooldown(user_id=user_id, action="fishing", expires_at=expires_at))

        balance = user.balance

    # Send initial message and animate
    msg = await update.message.reply_text("🎣 Готовишь наживку...")
    await animate_fishing(msg)

    # Build result message
    if sell_price == 0:
        text = (
            f"🎣 <b>Рыбалка</b>\n\n"
            f"{fish_emoji} Поймал: <b>{fish_name}</b>\n\n"
            f"Наживка потрачена зря!\n"
            f"💸 -{format_diamonds(BAIT_COST)}\n"
            f"💰 Баланс: {format_diamonds(balance)}"
        )
    elif sell_price < BAIT_COST:
        profit = sell_price - BAIT_COST
        text = (
            f"🎣 <b>Рыбалка</b>\n\n"
            f"{fish_emoji} Поймал: <b>{fish_name}</b>\n"
            f"💰 Продано за {format_diamonds(sell_price)}\n\n"
            f"📉 Убыток: {format_diamonds(abs(profit))} (наживка {format_diamonds(BAIT_COST)})\n"
            f"💰 Баланс: {format_diamonds(balance)}"
        )
    else:
        profit = sell_price - BAIT_COST
        rarity = ""
        if sell_price >= 100:
            rarity = " 🌟 ЛЕГЕНДА!"
        elif sell_price >= 50:
            rarity = " ✨ Редкий улов!"
        text = (
            f"🎣 <b>Рыбалка</b>\n\n"
            f"{fish_emoji} Поймал: <b>{fish_name}</b>!{rarity}\n"
            f"💰 Продано за {format_diamonds(sell_price)}\n\n"
            f"📈 Профит: +{format_diamonds(profit)} (наживка {format_diamonds(BAIT_COST)})\n"
            f"💰 Баланс: {format_diamonds(balance)}"
        )

    fish_kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📋 Виды рыб", callback_data=f"fish:list:{user_id}"),
                InlineKeyboardButton("« Игры", callback_data=f"menu:games:{user_id}"),
            ]
        ]
    )

    try:
        await msg.edit_text(text, parse_mode="HTML", reply_markup=fish_kb)
    except BadRequest:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=fish_kb)

    try:
        update_quest_progress(user_id, "fish")
    except Exception:
        pass

    logger.info("Fishing", user_id=user_id, fish=fish_name, sell_price=sell_price)


def _build_fishlist_text():
    """Build fish list text."""
    text = "🎣 <b>Виды рыб</b>\n\n"
    text += f"🪱 Наживка: {format_diamonds(BAIT_COST)}\n\n"

    for name, emoji, price, chance in FISH:
        if price == 0:
            text += f"{emoji} {name} — мусор\n"
        else:
            rarity = "обычная" if chance >= 15 else "редкая" if chance >= 5 else "легендарная"
            text += f"{emoji} {name} — {format_diamonds(price)} ({rarity})\n"

    return text


@require_registered
async def fishlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /fishlist — show all fish and prices."""
    if not update.effective_user or not update.message:
        return
    text = _build_fishlist_text() + "\n💡 /fish — забросить удочку"
    await update.message.reply_text(text, parse_mode="HTML")


async def fishlist_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle fish:list button."""
    query = update.callback_query
    if not query or not update.effective_user:
        return

    parts = query.data.split(":")
    if len(parts) != 3:
        return

    owner_id = int(parts[2])
    user_id = update.effective_user.id

    if user_id != owner_id:
        await query.answer("Эта кнопка не для тебя", show_alert=True)
        return

    await query.answer()

    text = _build_fishlist_text()
    keyboard = [[InlineKeyboardButton("« Игры", callback_data=f"menu:games:{user_id}")]]

    from app.utils.telegram_helpers import safe_edit_message

    await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard))


def register_fishing_handlers(application):
    """Register fishing handlers."""
    application.add_handler(CommandHandler(["fish", "fishing"], fishing_command))
    application.add_handler(CommandHandler("fishlist", fishlist_command))
    application.add_handler(CallbackQueryHandler(fishlist_callback, pattern=r"^fish:list:"))
    logger.info("Fishing handlers registered")
