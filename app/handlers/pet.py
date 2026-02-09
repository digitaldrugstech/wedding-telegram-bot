"""Pet command handlers."""

import random
from datetime import datetime, timedelta

import structlog
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import Cooldown, Pet, User
from app.handlers.quest import update_quest_progress
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds

logger = structlog.get_logger()

PET_PRICES = {
    "cat": 500,
    "dog": 1000,
    "dragon": 5000,
}

PET_NAMES = {
    "cat": "🐱 Кот",
    "dog": "🐶 Собака",
    "dragon": "🐉 Дракон",
}

PET_EMOJIS = {
    "cat": "🐱",
    "dog": "🐶",
    "dragon": "🐉",
}

FEED_COST = 10
PLAY_COOLDOWN_HOURS = 1
PLAY_MIN_REWARD = 5
PLAY_MAX_REWARD = 15
DEATH_DAYS = 3


@require_registered
async def pet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show pet info or buy pet (/pet [buy cat|dog|dragon])."""
    user_id = update.effective_user.id
    args = context.args

    # Handle buy subcommand
    if args and args[0] == "buy":
        if len(args) < 2:
            text = (
                "🐾 <b>Купить питомца</b>\n\n"
                "Используй: /pet buy [cat|dog|dragon]\n\n"
                f"🐱 Кот — {format_diamonds(PET_PRICES['cat'])}\n"
                f"🐶 Собака — {format_diamonds(PET_PRICES['dog'])}\n"
                f"🐉 Дракон — {format_diamonds(PET_PRICES['dragon'])}"
            )
            await update.message.reply_text(text, parse_mode="HTML")
            return

        pet_type = args[1].lower()
        if pet_type not in PET_PRICES:
            await update.message.reply_text("❌ Неизвестный тип питомца\n\nДоступны: cat, dog, dragon")
            return

        await buy_pet(update, user_id, pet_type)
        return

    # Handle feed subcommand
    if args and args[0] == "feed":
        await feed_pet(update, user_id)
        return

    # Handle play subcommand
    if args and args[0] == "play":
        await play_with_pet(update, user_id)
        return

    # Show pet info
    await show_pet(update, user_id)


async def buy_pet(update: Update, user_id: int, pet_type: str):
    """Buy a pet."""
    price = PET_PRICES[pet_type]

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            return

        # Check if already has pet
        existing_pet = db.query(Pet).filter(Pet.user_id == user_id, Pet.is_alive.is_(True)).first()
        if existing_pet:
            await update.message.reply_text("❌ У тебя уже есть питомец")
            return

        # Check balance
        if user.balance < price:
            await update.message.reply_text(
                f"❌ Недостаточно алмазов\n\n"
                f"Нужно: {format_diamonds(price)}\n"
                f"У тебя: {format_diamonds(user.balance)}"
            )
            return

        # Deduct payment
        user.balance -= price

        # Remove dead pet record if exists (unique constraint on user_id)
        dead_pet = db.query(Pet).filter(Pet.user_id == user_id, Pet.is_alive.is_(False)).first()
        if dead_pet:
            db.delete(dead_pet)
            db.flush()

        # Create pet
        pet = Pet(
            user_id=user_id,
            pet_type=pet_type,
            name=PET_NAMES[pet_type],
            hunger=50,
            happiness=50,
            last_fed_at=datetime.utcnow(),
        )
        db.add(pet)

        logger.info("Pet purchased", user_id=user_id, pet_type=pet_type, price=price)

    emoji = PET_EMOJIS[pet_type]
    await update.message.reply_text(
        f"{emoji} <b>Поздравляю с покупкой!</b>\n\n"
        f"Ты приобрёл {PET_NAMES[pet_type]}\n"
        f"Потрачено: {format_diamonds(price)}\n\n"
        f"💡 Не забывай кормить питомца каждые 3 дня",
        parse_mode="HTML",
    )


async def feed_pet(update: Update, user_id: int):
    """Feed pet."""
    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        pet = db.query(Pet).filter(Pet.user_id == user_id, Pet.is_alive.is_(True)).first()

        if not pet:
            await update.message.reply_text("❌ У тебя нет питомца")
            return

        # Check balance
        if user.balance < FEED_COST:
            await update.message.reply_text(f"❌ Недостаточно алмазов для корма\n\nНужно: {format_diamonds(FEED_COST)}")
            return

        # Deduct payment
        user.balance -= FEED_COST

        # Update pet stats
        pet.last_fed_at = datetime.utcnow()
        pet.hunger = min(100, pet.hunger + 30)
        pet.happiness = min(100, pet.happiness + 10)

        logger.info("Pet fed", user_id=user_id, cost=FEED_COST)

    emoji = PET_EMOJIS[pet.pet_type]
    await update.message.reply_text(
        f"{emoji} <b>Покормил питомца</b>\n\n"
        f"Голод: {pet.hunger}%\n"
        f"Счастье: {pet.happiness}%\n\n"
        f"Потрачено: {format_diamonds(FEED_COST)}",
        parse_mode="HTML",
    )

    # Track quest progress
    try:
        update_quest_progress(user_id, "pet")
    except Exception:
        pass


async def play_with_pet(update: Update, user_id: int):
    """Play with pet."""
    with get_db() as db:
        pet = db.query(Pet).filter(Pet.user_id == user_id, Pet.is_alive.is_(True)).first()

        if not pet:
            await update.message.reply_text("❌ У тебя нет питомца")
            return

        # Check cooldown
        cooldown = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "pet_play").first()

        if cooldown and cooldown.expires_at > datetime.utcnow():
            remaining = cooldown.expires_at - datetime.utcnow()
            hours, remainder = divmod(remaining.total_seconds(), 3600)
            minutes = remainder // 60

            time_str = []
            if hours > 0:
                time_str.append(f"{int(hours)}ч")
            if minutes > 0:
                time_str.append(f"{int(minutes)}м")

            await update.message.reply_text(f"⏰ Можешь поиграть через {' '.join(time_str)}")
            return

        # Play with pet
        reward = random.randint(PLAY_MIN_REWARD, PLAY_MAX_REWARD)
        user = db.query(User).filter(User.telegram_id == user_id).first()
        user.balance += reward

        # Update pet stats
        pet.happiness = min(100, pet.happiness + 20)
        pet.last_played_at = datetime.utcnow()

        # Set cooldown
        expires_at = datetime.utcnow() + timedelta(hours=PLAY_COOLDOWN_HOURS)
        if cooldown:
            cooldown.expires_at = expires_at
        else:
            cooldown = Cooldown(user_id=user_id, action="pet_play", expires_at=expires_at)
            db.add(cooldown)

        logger.info("Played with pet", user_id=user_id, reward=reward)

    emoji = PET_EMOJIS[pet.pet_type]
    await update.message.reply_text(
        f"{emoji} <b>Поиграл с питомцем</b>\n\n"
        f"Питомец нашёл для тебя {format_diamonds(reward)}\n"
        f"Счастье: {pet.happiness}%",
        parse_mode="HTML",
    )


async def show_pet(update: Update, user_id: int):
    """Show pet info."""
    with get_db() as db:
        pet = db.query(Pet).filter(Pet.user_id == user_id, Pet.is_alive.is_(True)).first()

        if not pet:
            text = (
                "🐾 <b>У тебя нет питомца</b>\n\n"
                "Купить:\n"
                f"🐱 Кот — /pet buy cat ({format_diamonds(PET_PRICES['cat'])})\n"
                f"🐶 Собака — /pet buy dog ({format_diamonds(PET_PRICES['dog'])})\n"
                f"🐉 Дракон — /pet buy dragon ({format_diamonds(PET_PRICES['dragon'])})"
            )
            await update.message.reply_text(text, parse_mode="HTML")
            return

        # Check if pet is starving
        days_since_fed = (datetime.utcnow() - pet.last_fed_at).days
        if days_since_fed >= DEATH_DAYS:
            pet.is_alive = False
            logger.info("Pet died from starvation", user_id=user_id, days=days_since_fed)

            await update.message.reply_text(
                "💀 <b>Твой питомец умер от голода</b>\n\n" "Ты не кормил его больше 3 дней",
                parse_mode="HTML",
            )
            return

        # Calculate hunger display (don't modify ORM object on view)
        hours_since_fed = (datetime.utcnow() - pet.last_fed_at).total_seconds() / 3600
        hunger_decrease = int(hours_since_fed * 2)  # 2% per hour
        display_hunger = max(0, pet.hunger - hunger_decrease)

        # Show pet info
        emoji = PET_EMOJIS[pet.pet_type]
        text = (
            f"{emoji} <b>{pet.name}</b>\n\n"
            f"🍖 Голод: {display_hunger}%\n"
            f"😊 Счастье: {pet.happiness}%\n\n"
            f"Покормлен: {days_since_fed} дней назад\n\n"
            f"Команды:\n"
            f"/pet feed — покормить ({format_diamonds(FEED_COST)})\n"
            f"/pet play — поиграть (раз в час)"
        )

        if days_since_fed >= 2:
            text += "\n\n⚠️ <b>Питомец скоро умрёт от голода!</b>"

        await update.message.reply_text(text, parse_mode="HTML")


def register_pet_handlers(application):
    """Register pet handlers."""
    application.add_handler(CommandHandler("pet", pet_command))
    logger.info("Pet handlers registered")
