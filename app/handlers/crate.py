"""Streak crate system — meaningful daily streak rewards with social announcements."""

import html
import random
from datetime import datetime

import structlog
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import Pet, User
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds

logger = structlog.get_logger()

# Crate types unlocked at specific streak milestones
# These replace the underwhelming milestone bonuses with exciting random loot
CRATE_MILESTONES = {
    7: "bronze",
    14: "silver",
    21: "gold",
    30: "diamond",
    50: "legendary",
}

CRATE_INFO = {
    "bronze": {
        "name": "Бронзовый сундук",
        "emoji": "🟤",
        "loot_table": [
            {"type": "diamonds", "amount": (100, 300), "chance": 40, "display": "💎 {amount} алмазов"},
            {"type": "diamonds", "amount": (300, 500), "chance": 25, "display": "💎 {amount} алмазов"},
            {"type": "title", "title_id": "survivor", "chance": 15, "display": "🏷 Титул: 🔥 Выживший"},
            {"type": "diamonds", "amount": (500, 800), "chance": 10, "display": "💎 {amount} алмазов"},
            {"type": "pet_acc", "acc": "bow", "chance": 10, "display": "🎀 Бантик для питомца"},
        ],
    },
    "silver": {
        "name": "Серебряный сундук",
        "emoji": "⚪",
        "loot_table": [
            {"type": "diamonds", "amount": (300, 600), "chance": 30, "display": "💎 {amount} алмазов"},
            {"type": "diamonds", "amount": (600, 1000), "chance": 25, "display": "💎 {amount} алмазов"},
            {"type": "title", "title_id": "dedicated", "chance": 15, "display": "🏷 Титул: 💪 Преданный"},
            {"type": "diamonds", "amount": (1000, 1500), "chance": 15, "display": "💎 {amount} алмазов"},
            {"type": "pet_acc", "acc": "crown", "chance": 10, "display": "👑 Корона для питомца"},
            {"type": "rep_boost", "amount": 5, "chance": 5, "display": "⭐ +5 репутации"},
        ],
    },
    "gold": {
        "name": "Золотой сундук",
        "emoji": "🟡",
        "loot_table": [
            {"type": "diamonds", "amount": (500, 1000), "chance": 25, "display": "💎 {amount} алмазов"},
            {"type": "diamonds", "amount": (1000, 2000), "chance": 25, "display": "💎 {amount} алмазов"},
            {"type": "title", "title_id": "veteran", "chance": 15, "display": "🏷 Титул: ⚔️ Ветеран"},
            {"type": "diamonds", "amount": (2000, 3000), "chance": 15, "display": "💎 {amount} алмазов"},
            {"type": "pet_acc", "acc": "wings", "chance": 10, "display": "🦋 Крылья для питомца"},
            {"type": "rep_boost", "amount": 10, "chance": 10, "display": "⭐ +10 репутации"},
        ],
    },
    "diamond": {
        "name": "Алмазный сундук",
        "emoji": "💎",
        "loot_table": [
            {"type": "diamonds", "amount": (1000, 2000), "chance": 20, "display": "💎 {amount} алмазов"},
            {"type": "diamonds", "amount": (2000, 4000), "chance": 20, "display": "💎 {amount} алмазов"},
            {"type": "title", "title_id": "immortal", "chance": 15, "display": "🏷 Титул: 🌟 Бессмертный"},
            {"type": "diamonds", "amount": (4000, 6000), "chance": 15, "display": "💎 {amount} алмазов"},
            {"type": "pet_acc", "acc": "collar", "chance": 10, "display": "💎 Ошейник для питомца"},
            {"type": "rep_boost", "amount": 20, "chance": 10, "display": "⭐ +20 репутации"},
            {"type": "diamonds", "amount": (6000, 10000), "chance": 10, "display": "💎 {amount} алмазов ДЖЕКПОТ!"},
        ],
    },
    "legendary": {
        "name": "Легендарный сундук",
        "emoji": "✨",
        "loot_table": [
            {"type": "diamonds", "amount": (3000, 5000), "chance": 15, "display": "💎 {amount} алмазов"},
            {"type": "diamonds", "amount": (5000, 10000), "chance": 20, "display": "💎 {amount} алмазов"},
            {"type": "title", "title_id": "mythic", "chance": 15, "display": "🏷 Титул: 🐲 Мифический"},
            {"type": "diamonds", "amount": (10000, 15000), "chance": 15, "display": "💎 {amount} алмазов"},
            {"type": "rep_boost", "amount": 50, "chance": 10, "display": "⭐ +50 репутации"},
            {"type": "diamonds", "amount": (15000, 25000), "chance": 10, "display": "💎 {amount} алмазов МЕГА!"},
            {"type": "prestige_point", "chance": 5, "display": "🔄 +1 к престижу БЕСПЛАТНО!"},
            {"type": "diamonds", "amount": (25000, 50000), "chance": 10, "display": "💎 {amount} ЛЕГЕНДА!!!"},
        ],
    },
}

# Exclusive streak titles (not in regular shop)
STREAK_TITLES = {
    "survivor": {"name": "Выживший", "emoji": "🔥", "display": "🔥 Выживший"},
    "dedicated": {"name": "Преданный", "emoji": "💪", "display": "💪 Преданный"},
    "veteran": {"name": "Ветеран", "emoji": "⚔️", "display": "⚔️ Ветеран"},
    "immortal": {"name": "Бессмертный", "emoji": "🌟", "display": "🌟 Бессмертный"},
    "mythic": {"name": "Мифический", "emoji": "🐲", "display": "🐲 Мифический"},
}


def roll_crate(crate_type: str) -> dict:
    """Roll for loot from a crate."""
    info = CRATE_INFO[crate_type]
    loot_table = info["loot_table"]

    roll = random.randint(1, 100)
    cumulative = 0
    for item in loot_table:
        cumulative += item["chance"]
        if roll <= cumulative:
            result = dict(item)
            if result["type"] == "diamonds":
                result["rolled_amount"] = random.randint(*result["amount"])
            return result

    # Fallback
    return loot_table[0]


def apply_crate_reward(user_id: int, reward: dict) -> str:
    """Apply crate reward to user and return display text."""
    reward_type = reward["type"]

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            return "❌ Ошибка"

        if reward_type == "diamonds":
            amount = reward["rolled_amount"]
            user.balance += amount
            return reward["display"].format(amount=amount)

        elif reward_type == "title":
            title_id = reward["title_id"]
            # Add to purchased titles
            titles = user.purchased_titles.split(",") if user.purchased_titles else []
            titles = [t for t in titles if t]
            if title_id not in titles:
                titles.append(title_id)
                user.purchased_titles = ",".join(titles)
                user.active_title = title_id
            return reward["display"]

        elif reward_type == "pet_acc":
            acc_code = reward["acc"]
            pet = db.query(Pet).filter(Pet.user_id == user_id, Pet.is_alive.is_(True)).first()
            if pet:
                owned = pet.accessories.split(",") if pet.accessories else []
                owned = [a for a in owned if a]
                if acc_code not in owned:
                    owned.append(acc_code)
                    pet.accessories = ",".join(owned)
                    return reward["display"]
                else:
                    # Already has it — give diamonds instead
                    fallback = random.randint(200, 500)
                    user.balance += fallback
                    return f"💎 {fallback} алмазов (аксессуар уже есть)"
            else:
                # No pet — give diamonds
                fallback = random.randint(200, 500)
                user.balance += fallback
                return f"💎 {fallback} алмазов (нет питомца)"

        elif reward_type == "rep_boost":
            amount = reward["amount"]
            user.reputation += amount
            return reward["display"]

        elif reward_type == "prestige_point":
            from app.handlers.prestige import MAX_PRESTIGE

            current = user.prestige_level or 0
            if current < MAX_PRESTIGE:
                user.prestige_level = current + 1
                return reward["display"]
            else:
                # Max prestige — give big diamonds
                fallback = random.randint(5000, 10000)
                user.balance += fallback
                return f"💎 {fallback} алмазов (макс. престиж)"

    return "❌ Ошибка"


def check_streak_crate(streak: int) -> str | None:
    """Check if the streak number unlocks a crate."""
    return CRATE_MILESTONES.get(streak)


@require_registered
async def crate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /crate — show streak crate info and upcoming milestones."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        streak = user.daily_streak or 0

    text = "🎁 <b>Сундуки за серию</b>\n\n"
    text += f"📅 Текущая серия: {streak} дней\n\n"

    for day, crate_type in sorted(CRATE_MILESTONES.items()):
        info = CRATE_INFO[crate_type]
        if streak >= day:
            text += f"✅ {info['emoji']} <b>{info['name']}</b> ({day} дней) — получен!\n"
        else:
            days_left = day - streak
            text += f"🔒 {info['emoji']} <b>{info['name']}</b> ({day} дней) — через {days_left} дней\n"

    text += (
        "\n<b>Как получить:</b>\n"
        "Заходи /daily каждый день, не пропускай!\n"
        "При достижении нужной серии сундук откроется автоматически\n\n"
        "⚠️ Если пропустишь день — серия обнулится!"
    )

    await update.message.reply_text(text, parse_mode="HTML")


async def open_crate_and_announce(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, streak: int):
    """Open a crate and announce the result. Called from daily.py after streak update."""
    crate_type = check_streak_crate(streak)
    if not crate_type:
        return None

    info = CRATE_INFO[crate_type]
    reward = roll_crate(crate_type)
    reward_text = apply_crate_reward(user_id, reward)

    username = ""
    if update.effective_user:
        username = html.escape(update.effective_user.username or update.effective_user.first_name or f"User{user_id}")

    # Build dramatic crate opening text
    crate_text = (
        f"\n\n{'=' * 20}\n"
        f"{info['emoji']} <b>СУНДУК!</b> {info['emoji']}\n\n"
        f"🎊 {info['name']} за {streak} дней!\n\n"
        f"Лут: <b>{reward_text}</b>\n"
        f"{'=' * 20}"
    )

    # Announce in production chat for rare items
    if crate_type in ("gold", "diamond", "legendary"):
        from app.constants import PRODUCTION_CHAT_ID

        try:
            announce_text = (
                f"{info['emoji']} <b>@{username} открыл {info['name']}!</b>\n\n"
                f"📅 Серия: {streak} дней\n"
                f"Лут: <b>{reward_text}</b>"
            )
            await context.bot.send_message(
                chat_id=PRODUCTION_CHAT_ID,
                text=announce_text,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Failed to announce crate", error=str(e))

    logger.info("Crate opened", user_id=user_id, crate=crate_type, reward=reward_text, streak=streak)

    return crate_text


def register_crate_handlers(application):
    """Register crate handlers."""
    application.add_handler(CommandHandler("crate", crate_command))
    logger.info("Crate handlers registered")
