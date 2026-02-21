"""Pet command handlers — full inline button menu."""

import html
import random
from datetime import datetime, timedelta

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import Cooldown, Pet, User
from app.handlers.quest import update_quest_progress
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds, format_word
from app.utils.telegram_helpers import delete_command_and_reply, safe_edit_message

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


# ==================== KEYBOARD BUILDERS ====================


def _pet_buy_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Keyboard for buying a pet."""
    keyboard = [
        [
            InlineKeyboardButton(
                f"🐱 Кот ({format_diamonds(PET_PRICES['cat'])})", callback_data=f"pet:buy:cat:{user_id}"
            )
        ],
        [
            InlineKeyboardButton(
                f"🐶 Собака ({format_diamonds(PET_PRICES['dog'])})", callback_data=f"pet:buy:dog:{user_id}"
            )
        ],
        [
            InlineKeyboardButton(
                f"🐉 Дракон ({format_diamonds(PET_PRICES['dragon'])})", callback_data=f"pet:buy:dragon:{user_id}"
            )
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def _pet_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Action buttons for pet owner."""
    keyboard = [
        [
            InlineKeyboardButton(f"🍖 Покормить ({FEED_COST})", callback_data=f"pet:feed:{user_id}"),
            InlineKeyboardButton("🎮 Поиграть", callback_data=f"pet:play:{user_id}"),
        ],
        [
            InlineKeyboardButton("🛍 Магазин", callback_data=f"pet:shop:{user_id}"),
            InlineKeyboardButton(f"✏️ Имя ({RENAME_COST})", callback_data=f"pet:rename:{user_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def _pet_shop_keyboard(user_id: int, owned: list) -> InlineKeyboardMarkup:
    """Accessory shop — only unbought items as buttons."""
    rows = []
    row = []
    for code, info in PET_ACCESSORIES.items():
        if code in owned:
            continue
        btn = InlineKeyboardButton(f"{info['emoji']} {info['price']}", callback_data=f"pet:acc:{code}:{user_id}")
        row.append(btn)
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("« Питомец", callback_data=f"pet:back:{user_id}")])
    return InlineKeyboardMarkup(rows)


# ==================== PET INFO BUILDER ====================


def _build_pet_status(db, user_id: int):
    """Build pet status text. Returns (text, keyboard, is_dead)."""
    pet = db.query(Pet).filter(Pet.user_id == user_id, Pet.is_alive.is_(True)).first()

    if not pet:
        # Check for dead pet
        dead_pet = db.query(Pet).filter(Pet.user_id == user_id, Pet.is_alive.is_(False)).first()
        if dead_pet:
            text = "💀 <b>Твой питомец умер</b>\n\nМожешь купить нового:"
        else:
            text = "🐾 <b>У тебя нет питомца</b>\n\nВыбери:"
        return text, _pet_buy_keyboard(user_id), False

    # Check starvation
    days_since_fed = (datetime.utcnow() - pet.last_fed_at).days
    if days_since_fed >= DEATH_DAYS:
        pet.is_alive = False
        from app.handlers.premium import build_premium_nudge

        nudge = build_premium_nudge("pet_dead", user_id)
        text = f"💀 <b>Твой питомец умер от голода</b>\n\nТы не кормил больше 3 дней{nudge}\n\nКупить нового:"
        return text, _pet_buy_keyboard(user_id), True

    # Live pet info
    hours_since_fed = (datetime.utcnow() - pet.last_fed_at).total_seconds() / 3600
    hunger_decrease = int(hours_since_fed * 2)
    display_hunger = max(0, pet.hunger - hunger_decrease)

    owned_acc = get_pet_accessories(pet)
    acc_display = format_accessories_display(owned_acc)

    emoji = PET_EMOJIS[pet.pet_type]
    name_display = pet.name
    if acc_display:
        name_display += f"  {acc_display}"

    text = f"{emoji} <b>{name_display}</b>\n\n" f"🍖 Голод: {display_hunger}%\n" f"😊 Счастье: {pet.happiness}%"

    if owned_acc:
        text += f"\n📦 Аксессуаров: {len(owned_acc)}/{len(PET_ACCESSORIES)}"

    if days_since_fed >= 2:
        text += "\n\n⚠️ <b>Скоро умрёт от голода!</b>"

    return text, _pet_menu_keyboard(user_id), False


# ==================== COMMAND HANDLER ====================


@require_registered
async def pet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /pet — show pet menu with buttons."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    args = context.args

    # Still support /pet rename [name] (needs text input)
    if args and args[0].lower() == "rename" and len(args) >= 2:
        new_name = " ".join(args[1:])[:30]
        await _do_rename(update.message, user_id, new_name)
        return

    with get_db() as db:
        text, keyboard, _ = _build_pet_status(db, user_id)

    reply = await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
    await delete_command_and_reply(update, reply, context, delay=90)


# ==================== CALLBACK HANDLERS ====================


async def pet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all pet callbacks — pet:{action}:{param}:{user_id}."""
    query = update.callback_query
    if not query or not update.effective_user:
        return

    parts = query.data.split(":")
    if len(parts) < 3:
        return

    action = parts[1]
    user_id = update.effective_user.id

    # Owner check (user_id is always last)
    owner_id = int(parts[-1])
    if user_id != owner_id:
        await query.answer("Эта кнопка не для тебя", show_alert=True)
        return

    # Ban check
    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user or user.is_banned:
            await query.answer("Доступ запрещён", show_alert=True)
            return

    if action == "buy":
        await _handle_buy(query, user_id, parts[2])
    elif action == "feed":
        await _handle_feed(query, user_id)
    elif action == "play":
        await _handle_play(query, user_id)
    elif action == "shop":
        await _handle_shop(query, user_id)
    elif action == "acc":
        await _handle_buy_accessory(query, user_id, parts[2])
    elif action == "back":
        await _handle_back(query, user_id)
    elif action == "rename":
        await query.answer(f"Напиши: /pet rename [имя] ({format_diamonds(RENAME_COST)})", show_alert=True)


async def _handle_buy(query, user_id: int, pet_type: str):
    """Buy a pet via button."""
    if pet_type not in PET_PRICES:
        return

    price = PET_PRICES[pet_type]

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()

        existing = db.query(Pet).filter(Pet.user_id == user_id, Pet.is_alive.is_(True)).first()
        if existing:
            await query.answer("У тебя уже есть питомец", show_alert=True)
            return

        if user.balance < price:
            await query.answer(
                f"Нужно {format_diamonds(price)}, у тебя {format_diamonds(user.balance)}", show_alert=True
            )
            return

        user.balance -= price

        dead_pet = db.query(Pet).filter(Pet.user_id == user_id, Pet.is_alive.is_(False)).first()
        if dead_pet:
            db.delete(dead_pet)
            db.flush()

        pet = Pet(
            user_id=user_id,
            pet_type=pet_type,
            name=PET_NAMES[pet_type],
            hunger=50,
            happiness=50,
            last_fed_at=datetime.utcnow(),
        )
        db.add(pet)

    await query.answer()

    emoji = PET_EMOJIS[pet_type]
    await safe_edit_message(
        query,
        f"{emoji} <b>Питомец куплен!</b>\n\n"
        f"{PET_NAMES[pet_type]}\n"
        f"Потрачено: {format_diamonds(price)}\n\n"
        f"Не забывай кормить каждые 3 дня!",
        reply_markup=_pet_menu_keyboard(user_id),
    )
    logger.info("Pet purchased", user_id=user_id, pet_type=pet_type, price=price)


async def _handle_feed(query, user_id: int):
    """Feed pet via button."""
    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        pet = db.query(Pet).filter(Pet.user_id == user_id, Pet.is_alive.is_(True)).first()

        if not pet:
            await query.answer("У тебя нет питомца", show_alert=True)
            return

        if user.balance < FEED_COST:
            await query.answer(f"Нужно {format_diamonds(FEED_COST)}", show_alert=True)
            return

        user.balance -= FEED_COST
        pet.last_fed_at = datetime.utcnow()
        pet.hunger = min(100, pet.hunger + 30)
        pet.happiness = min(100, pet.happiness + 10)

        hunger_val = pet.hunger
        happiness_val = pet.happiness
        pet_type = pet.pet_type

    await query.answer(f"🍖 Покормлено! Голод: {hunger_val}%")

    # Refresh pet menu
    with get_db() as db:
        text, keyboard, _ = _build_pet_status(db, user_id)
    await safe_edit_message(query, text, reply_markup=keyboard)

    try:
        update_quest_progress(user_id, "pet")
    except Exception:
        pass


async def _handle_play(query, user_id: int):
    """Play with pet via button."""
    with get_db() as db:
        pet = db.query(Pet).filter(Pet.user_id == user_id, Pet.is_alive.is_(True)).first()
        if not pet:
            await query.answer("У тебя нет питомца", show_alert=True)
            return

        cooldown = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "pet_play").first()
        if cooldown and cooldown.expires_at > datetime.utcnow():
            remaining = cooldown.expires_at - datetime.utcnow()
            minutes = int(remaining.total_seconds() / 60)
            await query.answer(f"Можешь поиграть через {minutes}м", show_alert=True)
            return

        reward = random.randint(PLAY_MIN_REWARD, PLAY_MAX_REWARD)
        user = db.query(User).filter(User.telegram_id == user_id).first()
        user.balance += reward

        pet.happiness = min(100, pet.happiness + 20)
        pet.last_played_at = datetime.utcnow()

        expires_at = datetime.utcnow() + timedelta(hours=PLAY_COOLDOWN_HOURS)
        if cooldown:
            cooldown.expires_at = expires_at
        else:
            db.add(Cooldown(user_id=user_id, action="pet_play", expires_at=expires_at))

    await query.answer(f"🎮 +{reward} алмазов!")

    # Refresh pet menu
    with get_db() as db:
        text, keyboard, _ = _build_pet_status(db, user_id)
    await safe_edit_message(query, text, reply_markup=keyboard)


async def _handle_shop(query, user_id: int):
    """Show accessory shop."""
    with get_db() as db:
        pet = db.query(Pet).filter(Pet.user_id == user_id, Pet.is_alive.is_(True)).first()
        if not pet:
            await query.answer("Сначала купи питомца", show_alert=True)
            return

        owned = get_pet_accessories(pet)

    text = "🛍 <b>Аксессуары</b>\n\n"
    for code, info in PET_ACCESSORIES.items():
        if code in owned:
            text += f"{info['emoji']} {info['name']} ✅\n"
        else:
            text += f"{info['emoji']} {info['name']} — {format_diamonds(info['price'])}\n"

    text += f"\n📦 {len(owned)}/{len(PET_ACCESSORIES)}"
    if len(owned) == len(PET_ACCESSORIES):
        text += " — всё куплено! 🎉"

    await query.answer()
    await safe_edit_message(query, text, reply_markup=_pet_shop_keyboard(user_id, owned))


async def _handle_buy_accessory(query, user_id: int, acc_code: str):
    """Buy accessory via button."""
    if acc_code not in PET_ACCESSORIES:
        return

    acc_info = PET_ACCESSORIES[acc_code]

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        pet = db.query(Pet).filter(Pet.user_id == user_id, Pet.is_alive.is_(True)).first()

        if not pet:
            await query.answer("Нет питомца", show_alert=True)
            return

        owned = get_pet_accessories(pet)
        if acc_code in owned:
            await query.answer("Уже куплено", show_alert=True)
            return

        price = acc_info["price"]
        if user.balance < price:
            await query.answer(f"Нужно {format_diamonds(price)}", show_alert=True)
            return

        user.balance -= price
        owned.append(acc_code)
        pet.accessories = ",".join(owned)
        pet.happiness = min(100, pet.happiness + 5)

    await query.answer(f"{acc_info['emoji']} {acc_info['name']} куплен!")

    # Refresh shop
    with get_db() as db:
        pet = db.query(Pet).filter(Pet.user_id == user_id, Pet.is_alive.is_(True)).first()
        current_owned = get_pet_accessories(pet) if pet else []

    text = "🛍 <b>Аксессуары</b>\n\n"
    for code, info in PET_ACCESSORIES.items():
        if code in current_owned:
            text += f"{info['emoji']} {info['name']} ✅\n"
        else:
            text += f"{info['emoji']} {info['name']} — {format_diamonds(info['price'])}\n"
    text += f"\n📦 {len(current_owned)}/{len(PET_ACCESSORIES)}"

    await safe_edit_message(query, text, reply_markup=_pet_shop_keyboard(user_id, current_owned))
    logger.info("Pet accessory bought", user_id=user_id, accessory=acc_code, price=acc_info["price"])


async def _handle_back(query, user_id: int):
    """Back to pet info."""
    with get_db() as db:
        text, keyboard, _ = _build_pet_status(db, user_id)
    await query.answer()
    await safe_edit_message(query, text, reply_markup=keyboard)


async def _do_rename(message, user_id: int, new_name: str):
    """Rename pet (still needs text input)."""
    safe_name = html.escape(new_name.strip())
    if not safe_name:
        await message.reply_text("❌ Имя не может быть пустым")
        return

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        pet = db.query(Pet).filter(Pet.user_id == user_id, Pet.is_alive.is_(True)).first()

        if not pet:
            await message.reply_text("❌ Нет питомца")
            return

        if user.balance < RENAME_COST:
            await message.reply_text(f"❌ Нужно {format_diamonds(RENAME_COST)}, у тебя {format_diamonds(user.balance)}")
            return

        old_name = pet.name
        user.balance -= RENAME_COST
        pet.name = safe_name

    await message.reply_text(
        f"✏️ <b>Переименован</b>\n\n{old_name} → {safe_name}\n\nПотрачено: {format_diamonds(RENAME_COST)}",
        parse_mode="HTML",
    )
    logger.info("Pet renamed", user_id=user_id, old_name=old_name, new_name=safe_name)


def register_pet_handlers(application):
    """Register pet handlers."""
    application.add_handler(CommandHandler("pet", pet_command))
    application.add_handler(CallbackQueryHandler(pet_callback, pattern=r"^pet:"))
    logger.info("Pet handlers registered")
