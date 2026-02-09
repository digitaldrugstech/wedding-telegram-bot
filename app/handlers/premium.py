"""Premium shop — Telegram Stars microtransactions."""

import html
from datetime import datetime, timedelta
from typing import Dict

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, PreCheckoutQueryHandler, filters

from app.database.connection import get_db
from app.database.models import ActiveBoost, Cooldown, Pet, StarPurchase, User
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds
from app.utils.telegram_helpers import safe_edit_message

logger = structlog.get_logger()

# ==================== NUDGE THROTTLE (in-memory, resets on restart) ====================
# Key: (user_id, nudge_type), Value: datetime of last shown nudge
_nudge_timestamps: Dict[tuple, datetime] = {}
NUDGE_COOLDOWN_SECONDS = 1800  # 30 minutes per nudge type per user

# ==================== PRODUCT CATALOG ====================

# Base price per diamond (cheapest pack): 500 / 15 = 33.3 diamonds per star
# Used to calculate savings percentages for larger packs
_BASE_RATIO = 500 / 15

PRODUCTS = {
    # Diamond Packs
    "diamonds_500": {
        "name": "500 алмазов",
        "description": "Хватит на первый бизнес или пару дней в казино",
        "stars": 15,
        "diamonds": 500,
        "emoji": "💎",
        "category": "diamonds",
    },
    "diamonds_1500": {
        "name": "1,500 алмазов",
        "description": "Открой бизнес + купи дом — самый популярный пакет",
        "stars": 30,
        "diamonds": 1500,
        "emoji": "💎",
        "category": "diamonds",
        "badge": "🔥",
    },
    "diamonds_5000": {
        "name": "5,000 алмазов",
        "description": "Хватит на титул + бизнес + страховку на месяц",
        "stars": 75,
        "diamonds": 5000,
        "emoji": "💎",
        "category": "diamonds",
        "badge": "💰",
    },
    "diamonds_12000": {
        "name": "12,000 алмазов",
        "description": "Полная свобода — титул Король + бизнес-империя + запас",
        "stars": 150,
        "diamonds": 12000,
        "emoji": "💎",
        "category": "diamonds",
        "badge": "🏆",
    },
    # Boosts
    "cooldown_skip": {
        "name": "Сброс кулдауна",
        "description": "Все кулдауны обнулены — работай, играй, крути прямо сейчас",
        "stars": 5,
        "diamonds": 0,
        "emoji": "⏭",
        "category": "boost",
    },
    "double_income": {
        "name": "Двойной доход (24ч)",
        "description": "x2 к зарплате, бизнесу, рыбалке и шахте на 24 часа\nНа 10 уровне это 1300-2000 за /job вместо 650-1000",
        "stars": 50,
        "diamonds": 0,
        "emoji": "💰",
        "category": "boost",
    },
    "lucky_charm": {
        "name": "Талисман удачи (24ч)",
        "description": "+15% к каждому выигрышу в казино, колесе и скретчах\nДжекпот слотов: 34,500 вместо 30,000",
        "stars": 35,
        "diamonds": 0,
        "emoji": "🍀",
        "category": "boost",
    },
    "shield": {
        "name": "Щит (24ч)",
        "description": "Полная защита от /rob и /kidnap — спи спокойно 24 часа",
        "stars": 25,
        "diamonds": 0,
        "emoji": "🛡",
        "category": "boost",
    },
    # Micro-purchases
    "pet_revive": {
        "name": "Воскрешение питомца",
        "description": "Твой питомец вернётся с тем же именем и аксессуарами",
        "stars": 15,
        "diamonds": 0,
        "emoji": "💊",
        "category": "boost",
    },
    "extra_lottery": {
        "name": "+5 лотерейных билетов",
        "description": "5 билетов сверх лимита — в 1.5 раза больше шансов на джекпот",
        "stars": 10,
        "diamonds": 0,
        "emoji": "🎟",
        "category": "boost",
    },
    "promotion_chance": {
        "name": "Шанс повышения",
        "description": "Следующий /job даёт 50% шанс на повышение вместо обычных 2-5%",
        "stars": 20,
        "diamonds": 0,
        "emoji": "📈",
        "category": "boost",
    },
    # Special
    "starter_pack": {
        "name": "Стартовый набор",
        "description": "5,000 алмазов + талисман удачи (24ч) + сброс кулдаунов\nВсё для быстрого старта — экономия 40%",
        "stars": 50,
        "diamonds": 5000,
        "emoji": "🎁",
        "category": "special",
        "one_time": True,
        "badge": "x5",
    },
    "vip_week": {
        "name": "VIP Неделя",
        "description": "x2 доход + талисман удачи + щит на 7 дней\n+ значок 👑 в профиле и топах — экономия 55%",
        "stars": 200,
        "diamonds": 0,
        "emoji": "👑",
        "category": "special",
        "badge": "🌟",
    },
}


def _savings_percent(product_id: str) -> int:
    """Calculate savings percentage compared to base diamond pack."""
    product = PRODUCTS.get(product_id)
    if not product or product["diamonds"] == 0:
        return 0
    actual_ratio = product["diamonds"] / product["stars"]
    if actual_ratio <= _BASE_RATIO:
        return 0
    return int((1 - _BASE_RATIO / actual_ratio) * 100)


# ==================== SHOP COMMAND ====================


@require_registered
async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /premium or /donate command — show shop."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    text, keyboard = _build_shop_main(user_id)
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)


def _build_shop_main(user_id: int):
    """Build main shop text and keyboard with active boost status."""
    # Check active boosts
    boosts_text = _format_active_boosts(user_id)

    # Loyalty points display
    loyalty = get_loyalty_points(user_id)
    loyalty_line = f"\n🎖 Очки лояльности: {loyalty}" if loyalty > 0 else ""

    text = "⭐ <b>Премиум-магазин</b>\n\n"
    if boosts_text:
        text += f"<b>Активные бусты:</b>\n{boosts_text}\n"
    text += f"Оплата через Telegram Stars{loyalty_line}\n\nВыбери категорию:"

    keyboard = [
        [
            InlineKeyboardButton("💎 Алмазы", callback_data=f"premium:cat:diamonds:{user_id}"),
            InlineKeyboardButton("🚀 Бусты", callback_data=f"premium:cat:boost:{user_id}"),
        ],
        [
            InlineKeyboardButton("🎁 Спец. предложения", callback_data=f"premium:cat:special:{user_id}"),
            InlineKeyboardButton("🎖 Лояльность", callback_data=f"premium:cat:loyalty:{user_id}"),
        ],
        [InlineKeyboardButton("« Меню", callback_data=f"menu:main:{user_id}")],
    ]

    return text, InlineKeyboardMarkup(keyboard)


def _format_active_boosts(user_id: int, db=None) -> str:
    """Format active boosts for display. Returns empty string if no boosts.

    Pass an existing db session to avoid opening a nested one.
    """
    boost_names = {
        "double_income": ("💰", "Двойной доход"),
        "lucky_charm": ("🍀", "Талисман удачи"),
        "shield": ("🛡", "Щит"),
        "promotion_chance": ("📈", "Шанс повышения"),
    }

    def _query(session):
        lines = []
        boosts = (
            session.query(ActiveBoost)
            .filter(ActiveBoost.user_id == user_id, ActiveBoost.expires_at > datetime.utcnow())
            .all()
        )
        for boost in boosts:
            remaining = boost.expires_at - datetime.utcnow()
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            if hours > 0:
                time_str = f"{hours}ч {minutes}м"
            else:
                time_str = f"{minutes}м"
            emoji, name = boost_names.get(boost.boost_type, ("🚀", boost.boost_type))
            lines.append(f"{emoji} {name} — {time_str}")
        return "\n".join(lines)

    if db is not None:
        return _query(db)
    with get_db() as session:
        return _query(session)


async def premium_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle premium shop navigation."""
    query = update.callback_query
    if not query or not update.effective_user:
        return

    parts = query.data.split(":")
    if len(parts) < 4:
        return

    action = parts[1]
    param = parts[2]
    owner_id = int(parts[3])
    user_id = update.effective_user.id

    if user_id != owner_id:
        await query.answer("Эта кнопка не для тебя", show_alert=True)
        return

    await query.answer()

    if action == "cat":
        # Show category
        category = param
        text, keyboard = _build_category(user_id, category)
        await safe_edit_message(query, text, reply_markup=keyboard)

    elif action == "buy":
        # Send invoice for product
        product_id = param
        if product_id not in PRODUCTS:
            return

        product = PRODUCTS[product_id]

        # Check one-time purchase
        if product.get("one_time"):
            with get_db() as db:
                existing = (
                    db.query(StarPurchase)
                    .filter(StarPurchase.user_id == user_id, StarPurchase.product == product_id)
                    .first()
                )
                if existing:
                    await query.answer("Ты уже купил это предложение!", show_alert=True)
                    return

        # Check pet revive — must have a dead pet
        if product_id == "pet_revive":
            with get_db() as db:
                dead_pet = db.query(Pet).filter(Pet.user_id == user_id, Pet.is_alive.is_(False)).first()
                if not dead_pet:
                    await query.answer("У тебя нет умершего питомца", show_alert=True)
                    return

        # Send invoice to the chat where the button was pressed (not DM — user may not have started DM)
        chat_id = query.message.chat_id if query.message else user_id
        try:
            await context.bot.send_invoice(
                chat_id=chat_id,
                title=product["name"],
                description=product["description"],
                payload=product_id,
                currency="XTR",
                prices=[LabeledPrice(product["name"], product["stars"])],
                provider_token="",
            )
        except Exception as e:
            logger.error("Failed to send invoice", user_id=user_id, product=product_id, error=str(e))
            await query.answer("Не удалось создать платёж. Попробуй написать боту в ЛС: /premium", show_alert=True)

    elif action == "main":
        text, keyboard = _build_shop_main(user_id)
        await safe_edit_message(query, text, reply_markup=keyboard)


def _build_category(user_id: int, category: str):
    """Build category product list."""
    # Handle loyalty page separately
    if category == "loyalty":
        return _build_loyalty_page(user_id)

    products = {k: v for k, v in PRODUCTS.items() if v["category"] == category}

    CATEGORY_NAMES = {
        "diamonds": "💎 Алмазы",
        "boost": "🚀 Бусты",
        "special": "🎁 Спец. предложения",
    }

    text = f"⭐ <b>{CATEGORY_NAMES.get(category, category)}</b>\n\n"

    for product_id, product in products.items():
        badge = f" {product['badge']}" if product.get("badge") else ""
        if product["diamonds"] > 0 and category == "diamonds":
            ratio = product["diamonds"] // product["stars"]
            savings = _savings_percent(product_id)
            savings_text = f" • <b>экономия {savings}%</b>" if savings > 0 else ""
            text += f"{product['emoji']} <b>{product['name']}</b> — {product['stars']} ⭐{badge}\n"
            text += f"   ({ratio} алм/⭐){savings_text}\n"
            text += f"   <i>{product['description']}</i>\n\n"
        else:
            text += f"{product['emoji']} <b>{product['name']}</b> — {product['stars']} ⭐{badge}\n"
            text += f"   <i>{product['description']}</i>\n\n"

    # Show active boosts in boost category
    if category == "boost":
        boosts_text = _format_active_boosts(user_id)
        if boosts_text:
            text += f"<b>Активные:</b>\n{boosts_text}\n\n"

    keyboard = []
    for product_id, product in products.items():
        badge = f" {product.get('badge', '')}" if product.get("badge") else ""
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{product['emoji']} {product['name']} — {product['stars']} ⭐{badge}",
                    callback_data=f"premium:buy:{product_id}:{user_id}",
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("« Магазин", callback_data=f"premium:main:0:{user_id}")])

    return text, InlineKeyboardMarkup(keyboard)


# ==================== PAYMENT FLOW ====================


async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Approve pre-checkout queries for Stars payments."""
    query = update.pre_checkout_query
    if not query:
        return

    product_id = query.invoice_payload
    user_id = query.from_user.id

    # Validate product exists
    if product_id not in PRODUCTS:
        await query.answer(ok=False, error_message="Такого товара нет")
        return

    product = PRODUCTS[product_id]

    # Check one-time purchases
    if product.get("one_time"):
        with get_db() as db:
            existing = (
                db.query(StarPurchase)
                .filter(StarPurchase.user_id == user_id, StarPurchase.product == product_id)
                .first()
            )
            if existing:
                await query.answer(ok=False, error_message="Это одноразовое предложение")
                return

    # Check pet revive — must have dead pet
    if product_id == "pet_revive":
        with get_db() as db:
            dead_pet = db.query(Pet).filter(Pet.user_id == user_id, Pet.is_alive.is_(False)).first()
            if not dead_pet:
                await query.answer(ok=False, error_message="У тебя нет умершего питомца")
                return

    await query.answer(ok=True)


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle successful Stars payment — fulfill the purchase."""
    if not update.message or not update.message.successful_payment or not update.effective_user:
        return

    payment = update.message.successful_payment
    product_id = payment.invoice_payload
    user_id = update.effective_user.id
    stars = payment.total_amount
    charge_id = payment.telegram_payment_charge_id

    if product_id not in PRODUCTS:
        logger.error("Unknown product in payment", user_id=user_id, product=product_id)
        return

    product = PRODUCTS[product_id]

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            logger.error("User not found for payment", user_id=user_id)
            return

        # Grant diamonds (with loyalty bonus for diamond packs)
        diamonds_granted = product.get("diamonds", 0)
        loyalty_bonus_diamonds = 0
        if diamonds_granted > 0:
            bonus_pct = get_loyalty_bonus_percent(user_id)
            if bonus_pct > 0:
                loyalty_bonus_diamonds = int(diamonds_granted * bonus_pct / 100)
                diamonds_granted += loyalty_bonus_diamonds
            user.balance += diamonds_granted

        # Apply boosts
        boost_applied = []

        if product_id == "cooldown_skip":
            deleted = db.query(Cooldown).filter(Cooldown.user_id == user_id).delete()
            boost_applied.append(f"Кулдауны сброшены ({deleted})")

        elif product_id == "double_income":
            _apply_boost(db, user_id, "double_income", hours=24)
            boost_applied.append("x2 доход на 24ч")

        elif product_id == "lucky_charm":
            _apply_boost(db, user_id, "lucky_charm", hours=24)
            boost_applied.append("Талисман удачи на 24ч")

        elif product_id == "shield":
            _apply_boost(db, user_id, "shield", hours=24)
            boost_applied.append("Щит на 24ч")

        elif product_id == "pet_revive":
            dead_pet = db.query(Pet).filter(Pet.user_id == user_id, Pet.is_alive.is_(False)).first()
            if dead_pet:
                dead_pet.is_alive = True
                dead_pet.hunger = 50
                dead_pet.happiness = 50
                dead_pet.last_fed_at = datetime.utcnow()
                boost_applied.append(f"🐾 {dead_pet.name} воскрешён!")
            else:
                boost_applied.append("У тебя нет умершего питомца (возврат невозможен)")

        elif product_id == "extra_lottery":
            from app.database.models import Lottery, LotteryTicket
            from app.constants import MAX_TICKETS_PER_USER

            lottery = db.query(Lottery).filter(Lottery.is_active.is_(True)).first()
            if lottery:
                current_tickets = (
                    db.query(LotteryTicket)
                    .filter(LotteryTicket.lottery_id == lottery.id, LotteryTicket.user_id == user_id)
                    .count()
                )
                premium_cap = MAX_TICKETS_PER_USER + 5  # Premium allows 5 extra over normal limit
                can_add = max(0, premium_cap - current_tickets)
                if can_add == 0:
                    user.balance += 500
                    boost_applied.append(f"Уже максимум билетов — начислено {format_diamonds(500)}")
                else:
                    for _ in range(can_add):
                        db.add(LotteryTicket(lottery_id=lottery.id, user_id=user_id))
                    lottery.jackpot += can_add * 100  # 100 per ticket
                    boost_applied.append(f"{can_add} билетов куплено (джекпот: {format_diamonds(lottery.jackpot)})")
            else:
                # No active lottery — refund as diamonds
                user.balance += 500
                boost_applied.append(f"Нет активной лотереи — начислено {format_diamonds(500)}")

        elif product_id == "promotion_chance":
            _apply_boost(db, user_id, "promotion_chance", hours=24)
            boost_applied.append("50% шанс повышения на следующий /job")

        elif product_id == "starter_pack":
            # Starter pack: diamonds + lucky charm + cooldown skip
            _apply_boost(db, user_id, "lucky_charm", hours=24)
            db.query(Cooldown).filter(Cooldown.user_id == user_id).delete()
            boost_applied.append("Талисман удачи на 24ч")
            boost_applied.append("Все кулдауны сброшены")

        elif product_id == "vip_week":
            _apply_boost(db, user_id, "double_income", hours=168)
            _apply_boost(db, user_id, "lucky_charm", hours=168)
            _apply_boost(db, user_id, "shield", hours=168)
            boost_applied.append("Все бусты на 7 дней")

        # Log purchase
        purchase = StarPurchase(
            user_id=user_id,
            product=product_id,
            stars_amount=stars,
            diamonds_granted=diamonds_granted,
            chat_id=update.effective_chat.id if update.effective_chat else None,
            telegram_charge_id=charge_id,
        )
        db.add(purchase)

        balance = user.balance

    # Build confirmation message
    text = f"✅ <b>Оплачено!</b>\n\n"
    text += f"{product['emoji']} {product['name']}\n"
    text += f"⭐ Оплачено: {stars} Stars\n\n"

    if diamonds_granted > 0:
        text += f"💎 +{format_diamonds(diamonds_granted)}\n"
        if loyalty_bonus_diamonds > 0:
            text += f"🎖 Бонус лояльности: +{format_diamonds(loyalty_bonus_diamonds)}\n"

    for boost_text in boost_applied:
        text += f"🚀 {boost_text}\n"

    text += f"\n💰 Баланс: {format_diamonds(balance)}"

    await update.message.reply_text(text, parse_mode="HTML")

    logger.info(
        "Premium purchase",
        user_id=user_id,
        product=product_id,
        stars=stars,
        diamonds=diamonds_granted,
        charge_id=charge_id,
    )

    # Notify admin (DM only, not chat)
    try:
        from app.config import config

        admin_text = (
            f"💰 <b>Покупка!</b>\n\n"
            f"👤 {html.escape(update.effective_user.username or str(user_id))}\n"
            f"📦 {product['name']}\n"
            f"⭐ {stars} Stars"
        )
        await context.bot.send_message(chat_id=config.admin_user_id, text=admin_text, parse_mode="HTML")
    except Exception:
        pass


def _apply_boost(db, user_id: int, boost_type: str, hours: int):
    """Apply or extend a boost."""
    expires_at = datetime.utcnow() + timedelta(hours=hours)

    existing = db.query(ActiveBoost).filter(ActiveBoost.user_id == user_id, ActiveBoost.boost_type == boost_type).first()

    if existing:
        # Extend if still active, otherwise replace
        if existing.expires_at > datetime.utcnow():
            existing.expires_at = existing.expires_at + timedelta(hours=hours)
        else:
            existing.expires_at = expires_at
    else:
        db.add(ActiveBoost(user_id=user_id, boost_type=boost_type, expires_at=expires_at))


# ==================== BOOST CHECK HELPERS ====================


def has_active_boost(user_id: int, boost_type: str, db=None) -> bool:
    """Check if user has an active boost of given type.

    Pass an existing db session to avoid opening a nested one.
    """

    def _check(session):
        boost = (
            session.query(ActiveBoost)
            .filter(
                ActiveBoost.user_id == user_id,
                ActiveBoost.boost_type == boost_type,
                ActiveBoost.expires_at > datetime.utcnow(),
            )
            .first()
        )
        return boost is not None

    if db is not None:
        return _check(db)
    with get_db() as session:
        return _check(session)


def consume_boost(user_id: int, boost_type: str, db=None) -> bool:
    """Consume a one-time boost (e.g. promotion_chance). Returns True if consumed.

    Pass an existing db session to avoid opening a nested one.
    """

    def _consume(session):
        boost = (
            session.query(ActiveBoost)
            .filter(
                ActiveBoost.user_id == user_id,
                ActiveBoost.boost_type == boost_type,
                ActiveBoost.expires_at > datetime.utcnow(),
            )
            .first()
        )
        if boost:
            session.delete(boost)
            return True
        return False

    if db is not None:
        return _consume(db)
    with get_db() as session:
        return _consume(session)
        return False


def has_ever_purchased(user_id: int, db=None) -> bool:
    """Check if user has ever made a real premium purchase (excluding loyalty points).

    Pass an existing db session to avoid opening a nested one.
    """

    def _check(session):
        return (
            session.query(StarPurchase)
            .filter(StarPurchase.user_id == user_id, StarPurchase.product != "loyalty_point")
            .first()
        ) is not None

    if db is not None:
        return _check(db)
    with get_db() as session:
        return _check(session)


# ==================== PREMIUM NUDGE HELPERS ====================


def _should_show_nudge(user_id: int, nudge_type: str) -> bool:
    """Check if enough time has passed since the last nudge of this type for this user.

    Returns True if nudge should be shown, False if suppressed.
    Also updates the timestamp if returning True.
    """
    key = (user_id, nudge_type)
    now = datetime.utcnow()
    last_shown = _nudge_timestamps.get(key)

    if last_shown and (now - last_shown).total_seconds() < NUDGE_COOLDOWN_SECONDS:
        return False

    _nudge_timestamps[key] = now

    # Prune old entries periodically (keep memory bounded)
    if len(_nudge_timestamps) > 5000:
        cutoff = now - timedelta(seconds=NUDGE_COOLDOWN_SECONDS * 2)
        stale = [k for k, v in _nudge_timestamps.items() if v < cutoff]
        for k in stale:
            del _nudge_timestamps[k]

    return True


def build_premium_nudge(nudge_type: str, user_id: int) -> str:
    """Build a contextual premium hint (max once per 30 min per type per user).

    nudge_type: 'casino_loss', 'robbed', 'cooldown', 'daily', 'pet_dead', 'promotion'
    Returns HTML text snippet (1-2 lines), or empty string if throttled.

    Design: every nudge shows what the player WOULD HAVE gained, not what they're missing.
    """
    # Throttle: suppress if shown recently
    if not _should_show_nudge(user_id, nudge_type):
        return ""

    # Each nudge is phrased as a benefit, not a loss
    nudges = {
        "casino_loss": "\n\n🍀 <i>С талисманом удачи ты бы выиграл на 15% больше — /premium</i>",
        "robbed": "\n\n🛡 <i>Со щитом это ограбление бы не прошло — /premium</i>",
        "cooldown": "\n\n⏭ <i>Можно сбросить кулдаун и работать прямо сейчас — /premium</i>",
        "daily": "\n\n👑 <i>С VIP ты бы получил x2 за этот бонус — /premium</i>",
        "pet_dead": "\n\n💊 <i>Питомца можно воскресить, сохранив имя и аксессуары — /premium</i>",
        "promotion": "\n\n📈 <i>С бустом шанс повышения был бы 50% вместо 2-5% — /premium</i>",
    }
    return nudges.get(nudge_type, "")


# ==================== VIP BADGE ====================


def get_vip_badge(user_id: int, db=None) -> str:
    """Return a VIP badge string if user has any active premium boost, empty string otherwise.

    Used in profile, /top, /job responses so VIP players feel recognised.
    Pass an existing db session to avoid opening a nested one.
    """

    def _check(session):
        has_any = (
            session.query(ActiveBoost)
            .filter(ActiveBoost.user_id == user_id, ActiveBoost.expires_at > datetime.utcnow())
            .first()
        )
        return " 👑" if has_any else ""

    if db is not None:
        return _check(db)
    with get_db() as session:
        return _check(session)


def is_vip(user_id: int, db=None) -> bool:
    """Quick check: does user have any active boost (i.e. they're a premium user right now)?

    Pass an existing db session to avoid opening a nested one.
    """

    def _check(session):
        return (
            session.query(ActiveBoost)
            .filter(ActiveBoost.user_id == user_id, ActiveBoost.expires_at > datetime.utcnow())
            .first()
        ) is not None

    if db is not None:
        return _check(db)
    with get_db() as session:
        return _check(session)


# ==================== LOYALTY POINTS SYSTEM ====================

# Earn points through gameplay — NOT exchangeable for Stars, but for discounts (bonus diamonds on purchase)
# 1 point per /job, 1 per /daily, 1 per casino game, 2 per quest completion
# 100 points = +10% bonus diamonds on next diamond pack purchase

LOYALTY_POINTS_PER_TIER = 100  # Points needed for one bonus tier
LOYALTY_BONUS_PER_TIER = 10  # +10% bonus diamonds per tier (max 3 tiers = +30%)
LOYALTY_MAX_TIERS = 3


def get_loyalty_points(user_id: int) -> int:
    """Get accumulated loyalty points for user.

    Uses StarPurchase table with product='loyalty_point' (no schema change needed).
    """
    with get_db() as db:
        from sqlalchemy import func as sqlfunc

        result = (
            db.query(sqlfunc.count(StarPurchase.id))
            .filter(StarPurchase.user_id == user_id, StarPurchase.product == "loyalty_point")
            .scalar()
        )
        return result or 0


def add_loyalty_points(user_id: int, points: int = 1):
    """Award loyalty points for gameplay activity. Lightweight, fire-and-forget."""
    try:
        with get_db() as db:
            for _ in range(points):
                db.add(
                    StarPurchase(
                        user_id=user_id,
                        product="loyalty_point",
                        stars_amount=0,
                        diamonds_granted=0,
                    )
                )
    except Exception:
        pass  # Loyalty tracking is non-critical


def get_loyalty_tier(user_id: int) -> int:
    """Get current loyalty tier (0-3). Determines bonus % on diamond purchases."""
    points = get_loyalty_points(user_id)
    return min(points // LOYALTY_POINTS_PER_TIER, LOYALTY_MAX_TIERS)


def get_loyalty_bonus_percent(user_id: int) -> int:
    """Get bonus diamond percentage for next purchase (0, 10, 20, or 30)."""
    return get_loyalty_tier(user_id) * LOYALTY_BONUS_PER_TIER


def _build_loyalty_page(user_id: int):
    """Build the loyalty points info page."""
    points = get_loyalty_points(user_id)
    tier = get_loyalty_tier(user_id)
    bonus_pct = tier * LOYALTY_BONUS_PER_TIER
    next_tier_points = (tier + 1) * LOYALTY_POINTS_PER_TIER if tier < LOYALTY_MAX_TIERS else None

    text = "🎖 <b>Очки лояльности</b>\n\n"
    text += f"Текущие очки: <b>{points}</b>\n"
    text += f"Уровень: <b>{tier}/{LOYALTY_MAX_TIERS}</b>\n"

    if bonus_pct > 0:
        text += f"Бонус к алмазам: <b>+{bonus_pct}%</b> при покупке пакета\n"
    else:
        text += "Бонус к алмазам: пока нет\n"

    if next_tier_points:
        remaining = next_tier_points - points
        text += f"\nДо следующего уровня: <b>{remaining}</b> очков\n"
    else:
        text += "\n🏆 <b>Максимальный уровень!</b> +30% бонус к алмазам\n"

    text += (
        "\n<b>Как копить:</b>\n"
        "• /job — 1 очко\n"
        "• /daily — 1 очко\n"
        "• Казино (любая игра) — 1 очко\n"
        "• Квест выполнен — 2 очка\n"
        "\n<i>Очки работают как скидка: при покупке алмазов\n"
        "ты получаешь бонусные алмазы сверху.</i>"
    )

    keyboard = [[InlineKeyboardButton("« Магазин", callback_data=f"premium:main:0:{user_id}")]]
    return text, InlineKeyboardMarkup(keyboard)


# ==================== REGISTER HANDLERS ====================


def register_premium_handlers(application):
    """Register premium shop handlers."""
    application.add_handler(CommandHandler(["premium", "donate", "shop_stars"], premium_command))
    application.add_handler(CallbackQueryHandler(premium_callback, pattern=r"^premium:"))
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    logger.info("Premium handlers registered")
