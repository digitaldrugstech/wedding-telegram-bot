"""Gift box (mystery box) command handlers — money sink."""

import random
from datetime import datetime, timedelta

import structlog
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import Cooldown, User
from app.handlers.quest import update_quest_progress
from app.handlers.shop import SHOP_TITLES, add_user_title, get_user_titles
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds

logger = structlog.get_logger()

GIFTBOX_COOLDOWN_SECONDS = 120  # 2 min between boxes

# Box tiers
BOXES = {
    "small": {
        "name": "🎁 Маленький бокс",
        "price": 50,
        "rewards": [
            {"type": "diamonds", "amount": 15, "label": "15💎", "weight": 30},
            {"type": "diamonds", "amount": 30, "label": "30💎", "weight": 25},
            {"type": "diamonds", "amount": 50, "label": "50💎", "weight": 18},
            {"type": "diamonds", "amount": 100, "label": "100💎", "weight": 7},
            {"type": "diamonds", "amount": 150, "label": "150💎", "weight": 3},
            {"type": "diamonds", "amount": 5, "label": "5💎", "weight": 10},
            {"type": "nothing", "amount": 0, "label": "Пусто", "weight": 7},
        ],
        # EV = 0.30*15 + 0.25*30 + 0.18*50 + 0.07*100 + 0.03*150 + 0.10*5 + 0.07*0 = 4.5+7.5+9+7+4.5+0.5 = 33
        # House edge = (50-33)/50 = 34%
    },
    "medium": {
        "name": "🎁 Средний бокс",
        "price": 200,
        "rewards": [
            {"type": "diamonds", "amount": 50, "label": "50💎", "weight": 25},
            {"type": "diamonds", "amount": 100, "label": "100💎", "weight": 20},
            {"type": "diamonds", "amount": 200, "label": "200💎", "weight": 12},
            {"type": "diamonds", "amount": 500, "label": "500💎", "weight": 3},
            {"type": "title", "title_id": "shadow", "label": "☠️ Титул «Тень»", "weight": 5},
            {"type": "title", "title_id": "fire", "label": "🔥 Титул «Огненный»", "weight": 5},
            {"type": "nothing", "amount": 0, "label": "Пусто", "weight": 30},
        ],
        # EV diamonds = 0.25*50 + 0.20*100 + 0.12*200 + 0.03*500 = 12.5+20+24+15 = 71.5
        # Titles worth ~1000-1500 each, 10% chance = ~100-150 EV
        # Total EV ~170-220 vs 200 cost = ~10-15% house edge on average
    },
    "large": {
        "name": "🎁 Большой бокс",
        "price": 500,
        "rewards": [
            {"type": "diamonds", "amount": 100, "label": "100💎", "weight": 20},
            {"type": "diamonds", "amount": 250, "label": "250💎", "weight": 18},
            {"type": "diamonds", "amount": 500, "label": "500💎", "weight": 10},
            {"type": "diamonds", "amount": 1000, "label": "1000💎", "weight": 3},
            {"type": "diamonds", "amount": 2500, "label": "2500💎 ДЖЕКПОТ!", "weight": 1},
            {"type": "title", "title_id": "legend", "label": "⭐ Титул «Легенда»", "weight": 4},
            {"type": "title", "title_id": "angel", "label": "😇 Титул «Ангел»", "weight": 4},
            {"type": "title", "title_id": "devil", "label": "😈 Титул «Дьявол»", "weight": 4},
            {"type": "nothing", "amount": 0, "label": "Пусто", "weight": 36},
        ],
        # EV diamonds = 0.20*100 + 0.18*250 + 0.10*500 + 0.03*1000 + 0.01*2500 = 20+45+50+30+25 = 170
        # Titles worth 2000-2500 each, 12% chance = ~240-300
        # Total EV ~410-470 vs 500 cost = ~6-18% house edge
    },
}


def roll_reward(box_type: str) -> dict:
    """Roll a random reward from a box."""
    box = BOXES[box_type]
    rewards = box["rewards"]
    weights = [r["weight"] for r in rewards]
    return random.choices(rewards, weights=weights, k=1)[0]


@require_registered
async def giftbox_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /giftbox [small|medium|large] command."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    # Parse box type
    if not context.args:
        text = (
            "🎁 <b>Гифт-боксы</b>\n\n"
            "Открой бокс и получи случайный приз!\n\n"
            f"🎁 /giftbox small — {format_diamonds(BOXES['small']['price'])}\n"
            "   Алмазы 5-150 или пусто\n\n"
            f"🎁 /giftbox medium — {format_diamonds(BOXES['medium']['price'])}\n"
            "   Алмазы 50-500 или титул\n\n"
            f"🎁 /giftbox large — {format_diamonds(BOXES['large']['price'])}\n"
            "   Алмазы 100-2500 или редкий титул\n\n"
            "💡 Титулы также продаются в /shop"
        )
        await update.message.reply_text(text, parse_mode="HTML")
        return

    box_type = context.args[0].lower()
    if box_type not in BOXES:
        await update.message.reply_text("❌ Выбери: small, medium или large")
        return

    box = BOXES[box_type]

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()

        # Check balance
        if user.balance < box["price"]:
            await update.message.reply_text(
                f"❌ Недостаточно алмазов\n\n"
                f"Цена: {format_diamonds(box['price'])}\n"
                f"У тебя: {format_diamonds(user.balance)}"
            )
            return

        # Check cooldown
        cooldown = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "giftbox").first()
        if cooldown and cooldown.expires_at > datetime.utcnow():
            remaining = cooldown.expires_at - datetime.utcnow()
            seconds_left = int(remaining.total_seconds())
            await update.message.reply_text(f"⏰ Следующий бокс через {seconds_left}с")
            return

        # Deduct payment
        user.balance -= box["price"]

        # Set cooldown
        expires_at = datetime.utcnow() + timedelta(seconds=GIFTBOX_COOLDOWN_SECONDS)
        if cooldown:
            cooldown.expires_at = expires_at
        else:
            db.add(Cooldown(user_id=user_id, action="giftbox", expires_at=expires_at))

        # Roll reward
        reward = roll_reward(box_type)

        # Apply reward
        reward_text = ""
        if reward["type"] == "diamonds":
            amount = reward["amount"]
            user.balance += amount
            reward_text = f"💎 +{format_diamonds(amount)}"
        elif reward["type"] == "title":
            title_id = reward["title_id"]
            owned = get_user_titles(user)
            if title_id in owned:
                # Already has title — give diamond equivalent instead
                title_data = SHOP_TITLES.get(title_id, {})
                refund = title_data.get("price", 500) // 2
                user.balance += refund
                reward_text = f"🔄 Титул уже есть → +{format_diamonds(refund)}"
            else:
                add_user_title(user, title_id)
                user.active_title = title_id
                reward_text = f"🏆 {reward['label']} — установлен!"
        else:
            reward_text = "💨 Пусто... Повезёт в следующий раз!"

        balance = user.balance

    # Build message
    text = (
        f"{box['name']}\n\n"
        f"Потрачено: {format_diamonds(box['price'])}\n\n"
        f"<b>{reward_text}</b>\n\n"
        f"💰 Баланс: {format_diamonds(balance)}"
    )

    await update.message.reply_text(text, parse_mode="HTML")

    try:
        update_quest_progress(user_id, "casino")
    except Exception:
        pass

    logger.info(
        "Giftbox opened",
        user_id=user_id,
        box_type=box_type,
        reward_type=reward["type"],
        reward_label=reward["label"],
        cost=box["price"],
    )


def register_giftbox_handlers(application):
    """Register giftbox handlers."""
    application.add_handler(CommandHandler("giftbox", giftbox_command))
    logger.info("Giftbox handlers registered")
