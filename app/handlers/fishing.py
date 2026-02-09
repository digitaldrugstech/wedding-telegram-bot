"""Fishing minigame handler — catch fish, sell or collect."""

import random
from datetime import datetime, timedelta

import structlog
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

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

        # Add sell price to balance
        user.balance += sell_price

        # Set cooldown
        expires_at = datetime.utcnow() + timedelta(minutes=FISHING_COOLDOWN_MINUTES)
        if cooldown:
            cooldown.expires_at = expires_at
        else:
            db.add(Cooldown(user_id=user_id, action="fishing", expires_at=expires_at))

        balance = user.balance

    # Build message
    if sell_price == 0:
        # Caught junk
        text = (
            f"🎣 <b>Рыбалка</b>\n\n"
            f"Ты закинул удочку...\n\n"
            f"{fish_emoji} Поймал: {fish_name}\n\n"
            f"Наживка потрачена зря!\n"
            f"💸 -{format_diamonds(BAIT_COST)}\n"
            f"💰 Баланс: {format_diamonds(balance)}"
        )
    elif sell_price < BAIT_COST:
        profit = sell_price - BAIT_COST
        text = (
            f"🎣 <b>Рыбалка</b>\n\n"
            f"Ты закинул удочку...\n\n"
            f"{fish_emoji} Поймал: <b>{fish_name}</b>\n"
            f"💰 Продано за {format_diamonds(sell_price)}\n\n"
            f"📉 Итого: {profit} (наживка {format_diamonds(BAIT_COST)})\n"
            f"💰 Баланс: {format_diamonds(balance)}"
        )
    else:
        profit = sell_price - BAIT_COST
        text = (
            f"🎣 <b>Рыбалка</b>\n\n"
            f"Ты закинул удочку...\n\n"
            f"{fish_emoji} Поймал: <b>{fish_name}</b>!\n"
            f"💰 Продано за {format_diamonds(sell_price)}\n\n"
            f"📈 Профит: +{format_diamonds(profit)} (наживка {format_diamonds(BAIT_COST)})\n"
            f"💰 Баланс: {format_diamonds(balance)}"
        )

    await update.message.reply_text(text, parse_mode="HTML")

    try:
        update_quest_progress(user_id, "casino")
    except Exception:
        pass

    logger.info("Fishing", user_id=user_id, fish=fish_name, sell_price=sell_price)


@require_registered
async def fishlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /fishlist — show all fish and prices."""
    text = "🎣 <b>Виды рыб</b>\n\n"
    text += f"🪱 Наживка: {format_diamonds(BAIT_COST)}\n\n"

    for name, emoji, price, chance in FISH:
        if price == 0:
            text += f"{emoji} {name} — мусор\n"
        else:
            rarity = "обычная" if chance >= 15 else "редкая" if chance >= 5 else "легендарная"
            text += f"{emoji} {name} — {format_diamonds(price)} ({rarity})\n"

    text += "\n💡 /fish — забросить удочку"

    await update.message.reply_text(text, parse_mode="HTML")


def register_fishing_handlers(application):
    """Register fishing handlers."""
    application.add_handler(CommandHandler(["fish", "fishing"], fishing_command))
    application.add_handler(CommandHandler("fishlist", fishlist_command))
    logger.info("Fishing handlers registered")
