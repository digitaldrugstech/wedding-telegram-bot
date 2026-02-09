"""Pet command handlers."""

import html
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

# Accessories shop
PET_ACCESSORIES = {
    "bow": {"name": "Бантик", "emoji": "🎀", "price": 100},
    "bell": {"name": "Колокольчик", "emoji": "🔔", "price": 200},
    "scarf": {"name": "Шарфик", "emoji": "🧣", "price": 300},
    "glasses": {"name": "Очки", "emoji": "😎", "price": 400},
    "crown": {"name": "Корона", "emoji": "👑", "price": 500},
    "hat": {"name": "Шляпа", "emoji": "🎩", "price": 600},
    "collar": {"name": "Ошейник", "emoji": "💎", "price": 750},
    "wings": {"name": "Крылья", "emoji": "🦋", "price": 1000},
}

RENAME_COST = 200
FEED_COST = 10
PLAY_COOLDOWN_HOURS = 1
PLAY_MIN_REWARD = 5
PLAY_MAX_REWARD = 15
DEATH_DAYS = 3


def get_pet_accessories(pet):
    """Get list of accessory codes for a pet."""
    if not pet.accessories:
        return []
    return [a for a in pet.accessories.split(",") if a]


def format_accessories_display(accessories_list):
    """Format accessories as emoji string for display."""
    if not accessories_list:
        return ""
    emojis = [PET_ACCESSORIES[a]["emoji"] for a in accessories_list if a in PET_ACCESSORIES]
    return " ".join(emojis)


@require_registered
async def pet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show pet info or buy pet (/pet [buy cat|dog|dragon])."""
    user_id = update.effective_user.id
    args = context.args

    if args:
        subcmd = args[0].lower()

        if subcmd == "buy":
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

        elif subcmd == "feed":
            await feed_pet(update, user_id)
            return

        elif subcmd == "play":
            await play_with_pet(update, user_id)
            return

        elif subcmd == "shop":
            await pet_shop(update, user_id)
            return

        elif subcmd == "acc":
            if len(args) < 2:
                await update.message.reply_text("❌ Укажи аксессуар\n\nСписок: /pet shop")
                return
            await buy_accessory(update, user_id, args[1].lower())
            return

        elif subcmd == "rename":
            if len(args) < 2:
                await update.message.reply_text(f"❌ Укажи имя\n\n/pet rename [имя] — {format_diamonds(RENAME_COST)}")
                return
            new_name = " ".join(args[1:])[:30]
            await rename_pet(update, user_id, new_name)
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
        f"💡 Не забывай кормить питомца каждые 3 дня\n"
        f"🛍 /pet shop — аксессуары для питомца",
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

        # Extract values before session closes
        pet_type = pet.pet_type
        hunger_val = pet.hunger
        happiness_val = pet.happiness

    emoji = PET_EMOJIS[pet_type]
    await update.message.reply_text(
        f"{emoji} <b>Покормил питомца</b>\n\n"
        f"🍖 Голод: {hunger_val}%\n"
        f"😊 Счастье: {happiness_val}%\n\n"
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

        # Extract values before session closes
        pet_type = pet.pet_type
        happiness_val = pet.happiness

    emoji = PET_EMOJIS[pet_type]
    await update.message.reply_text(
        f"{emoji} <b>Поиграл с питомцем</b>\n\n"
        f"Питомец нашёл для тебя {format_diamonds(reward)}\n"
        f"😊 Счастье: {happiness_val}%",
        parse_mode="HTML",
    )


async def pet_shop(update: Update, user_id: int):
    """Show pet accessories shop."""
    with get_db() as db:
        pet = db.query(Pet).filter(Pet.user_id == user_id, Pet.is_alive.is_(True)).first()

        if not pet:
            await update.message.reply_text("❌ Сначала купи питомца\n\n/pet buy [cat|dog|dragon]")
            return

        owned = get_pet_accessories(pet)

    text = "🛍 <b>Аксессуары для питомца</b>\n\n"

    for code, info in PET_ACCESSORIES.items():
        if code in owned:
            text += f"{info['emoji']} {info['name']} — <i>куплено</i>\n"
        else:
            text += f"{info['emoji']} {info['name']} — {format_diamonds(info['price'])} (/pet acc {code})\n"

    total_value = sum(PET_ACCESSORIES[a]["price"] for a in owned)
    text += f"\n📦 Куплено: {len(owned)}/{len(PET_ACCESSORIES)}"
    if total_value > 0:
        text += f" (на {format_diamonds(total_value)})"

    text += f"\n\n✏️ /pet rename [имя] — переименовать ({format_diamonds(RENAME_COST)})"

    await update.message.reply_text(text, parse_mode="HTML")


async def buy_accessory(update: Update, user_id: int, acc_code: str):
    """Buy a pet accessory."""
    if acc_code not in PET_ACCESSORIES:
        await update.message.reply_text("❌ Неизвестный аксессуар\n\nСписок: /pet shop")
        return

    acc_info = PET_ACCESSORIES[acc_code]

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        pet = db.query(Pet).filter(Pet.user_id == user_id, Pet.is_alive.is_(True)).first()

        if not pet:
            await update.message.reply_text("❌ Сначала купи питомца")
            return

        # Check if already owned
        owned = get_pet_accessories(pet)
        if acc_code in owned:
            await update.message.reply_text(f"❌ У питомца уже есть {acc_info['emoji']} {acc_info['name']}")
            return

        # Check balance
        price = acc_info["price"]
        if user.balance < price:
            await update.message.reply_text(
                f"❌ Недостаточно алмазов\n\n"
                f"Нужно: {format_diamonds(price)}\n"
                f"У тебя: {format_diamonds(user.balance)}"
            )
            return

        # Buy
        user.balance -= price
        owned.append(acc_code)
        pet.accessories = ",".join(owned)
        pet.happiness = min(100, pet.happiness + 5)

        balance = user.balance
        happiness_val = pet.happiness

    await update.message.reply_text(
        f"{acc_info['emoji']} <b>Аксессуар куплен!</b>\n\n"
        f"{acc_info['emoji']} {acc_info['name']} для твоего питомца\n"
        f"😊 Счастье: {happiness_val}%\n\n"
        f"💰 Потрачено: {format_diamonds(price)}\n"
        f"💰 Баланс: {format_diamonds(balance)}",
        parse_mode="HTML",
    )

    logger.info("Pet accessory bought", user_id=user_id, accessory=acc_code, price=price)


async def rename_pet(update: Update, user_id: int, new_name: str):
    """Rename pet."""
    safe_name = html.escape(new_name.strip())
    if not safe_name or len(safe_name) < 1:
        await update.message.reply_text("❌ Имя не может быть пустым")
        return

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        pet = db.query(Pet).filter(Pet.user_id == user_id, Pet.is_alive.is_(True)).first()

        if not pet:
            await update.message.reply_text("❌ Сначала купи питомца")
            return

        if user.balance < RENAME_COST:
            await update.message.reply_text(
                f"❌ Недостаточно алмазов\n\nНужно: {format_diamonds(RENAME_COST)}\n"
                f"У тебя: {format_diamonds(user.balance)}"
            )
            return

        old_name = pet.name
        user.balance -= RENAME_COST
        pet.name = safe_name

    await update.message.reply_text(
        f"✏️ <b>Питомец переименован</b>\n\n"
        f"{old_name} -> {safe_name}\n\n"
        f"Потрачено: {format_diamonds(RENAME_COST)}",
        parse_mode="HTML",
    )

    logger.info("Pet renamed", user_id=user_id, old_name=old_name, new_name=safe_name)


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

            from app.handlers.premium import build_premium_nudge

            nudge = build_premium_nudge("pet_dead", user_id)
            await update.message.reply_text(
                f"💀 <b>Твой питомец умер от голода</b>\n\nТы не кормил его больше 3 дней{nudge}",
                parse_mode="HTML",
            )
            return

        # Calculate hunger display (don't modify ORM object on view)
        hours_since_fed = (datetime.utcnow() - pet.last_fed_at).total_seconds() / 3600
        hunger_decrease = int(hours_since_fed * 2)  # 2% per hour
        display_hunger = max(0, pet.hunger - hunger_decrease)

        # Accessories display
        owned_acc = get_pet_accessories(pet)
        acc_display = format_accessories_display(owned_acc)

        # Show pet info
        emoji = PET_EMOJIS[pet.pet_type]
        name_display = pet.name
        if acc_display:
            name_display += f"  {acc_display}"

        text = f"{emoji} <b>{name_display}</b>\n\n" f"🍖 Голод: {display_hunger}%\n" f"😊 Счастье: {pet.happiness}%\n"

        if owned_acc:
            text += f"📦 Аксессуаров: {len(owned_acc)}/{len(PET_ACCESSORIES)}\n"

        text += (
            f"\nПокормлен: {days_since_fed} дней назад\n\n"
            f"Команды:\n"
            f"/pet feed — покормить ({format_diamonds(FEED_COST)})\n"
            f"/pet play — поиграть (раз в час)\n"
            f"/pet shop — магазин аксессуаров\n"
            f"/pet rename [имя] — переименовать ({format_diamonds(RENAME_COST)})"
        )

        if days_since_fed >= 2:
            text += "\n\n⚠️ <b>Питомец скоро умрёт от голода!</b>"

        await update.message.reply_text(text, parse_mode="HTML")


def register_pet_handlers(application):
    """Register pet handlers."""
    application.add_handler(CommandHandler("pet", pet_command))
    logger.info("Pet handlers registered")
