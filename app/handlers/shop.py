"""Shop command handlers — cosmetic titles and decorations."""

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import User
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds
from app.utils.telegram_helpers import delete_command_and_reply, safe_edit_message

logger = structlog.get_logger()

# Available titles for purchase (id: {name, price, emoji})
SHOP_TITLES = {
    "vip": {"name": "VIP", "emoji": "👑", "display": "👑 VIP", "price": 500},
    "legend": {"name": "Легенда", "emoji": "⭐", "display": "⭐ Легенда", "price": 2000},
    "diamond": {"name": "Алмазный", "emoji": "💎", "display": "💎 Алмазный", "price": 5000},
    "boss": {"name": "Босс", "emoji": "🦁", "display": "🦁 Босс", "price": 3000},
    "shadow": {"name": "Тень", "emoji": "🌑", "display": "🌑 Тень", "price": 1000},
    "fire": {"name": "Огненный", "emoji": "🔥", "display": "🔥 Огненный", "price": 1500},
    "ice": {"name": "Ледяной", "emoji": "❄️", "display": "❄️ Ледяной", "price": 1500},
    "toxic": {"name": "Токсик", "emoji": "☠️", "display": "☠️ Токсик", "price": 800},
    "angel": {"name": "Ангел", "emoji": "😇", "display": "😇 Ангел", "price": 2500},
    "devil": {"name": "Дьявол", "emoji": "😈", "display": "😈 Дьявол", "price": 2500},
    "king": {"name": "Король", "emoji": "🤴", "display": "🤴 Король", "price": 10000},
    "queen": {"name": "Королева", "emoji": "👸", "display": "👸 Королева", "price": 10000},
    # Streak-exclusive titles (earned from crates, not buyable)
    "survivor": {"name": "Выживший", "emoji": "🔥", "display": "🔥 Выживший", "price": 0},
    "dedicated": {"name": "Преданный", "emoji": "💪", "display": "💪 Преданный", "price": 0},
    "veteran": {"name": "Ветеран", "emoji": "⚔️", "display": "⚔️ Ветеран", "price": 0},
    "immortal": {"name": "Бессмертный", "emoji": "🌟", "display": "🌟 Бессмертный", "price": 0},
    "mythic": {"name": "Мифический", "emoji": "🐲", "display": "🐲 Мифический", "price": 0},
}


def get_user_titles(user):
    """Get list of purchased title IDs."""
    if not user.purchased_titles:
        return []
    return [t for t in user.purchased_titles.split(",") if t]


def add_user_title(user, title_id):
    """Add a title to user's purchased list."""
    titles = get_user_titles(user)
    if title_id not in titles:
        titles.append(title_id)
        user.purchased_titles = ",".join(titles)


@require_registered
async def shop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show shop (/shop)."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        balance = user.balance
        owned = get_user_titles(user)
        active = user.active_title

    # Build shop text
    text = "<b>🏪 Магазин титулов</b>\n\n"

    if active and active in SHOP_TITLES:
        text += f"Текущий титул: {SHOP_TITLES[active]['display']}\n\n"

    text += f"💰 Баланс: {format_diamonds(balance)}\n\n"
    text += "<b>Доступные титулы:</b>\n"

    # Streak-exclusive titles (price=0) shown separately
    STREAK_TITLE_IDS = {"survivor", "dedicated", "veteran", "immortal", "mythic"}

    # Sort buyable titles by price
    buyable_titles = [(tid, td) for tid, td in SHOP_TITLES.items() if tid not in STREAK_TITLE_IDS]
    buyable_titles.sort(key=lambda x: x[1]["price"])

    for title_id, title_data in buyable_titles:
        status = "✅" if title_id in owned else ""
        text += f"{title_data['display']} — {format_diamonds(title_data['price'])} {status}\n"

    # Show streak titles if any are owned
    streak_owned = [tid for tid in STREAK_TITLE_IDS if tid in owned]
    if streak_owned:
        text += "\n<b>Эксклюзивные (из сундуков):</b>\n"
        for tid in sorted(streak_owned):
            td = SHOP_TITLES[tid]
            text += f"✅ {td['display']}\n"

    text += f"\n✅ = куплено ({len(owned)}/{len(SHOP_TITLES)})"
    text += "\n\n🎁 /crate — сундуки за серию /daily"

    # Build keyboard (only for buyable titles)
    keyboard = []
    row = []
    for title_id, title_data in buyable_titles:
        if title_id in owned:
            label = f"✅ {title_data['emoji']}"
        else:
            label = f"{title_data['emoji']} {format_diamonds(title_data['price'])}"
        row.append(InlineKeyboardButton(label, callback_data=f"shop:{title_id}:{user_id}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    if owned:
        keyboard.append([InlineKeyboardButton("🚫 Снять титул", callback_data=f"shop:remove:{user_id}")])

    reply = await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    await delete_command_and_reply(update, reply, context, delay=120)


async def shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle shop button clicks."""
    query = update.callback_query
    if not query or not update.effective_user:
        return

    parts = query.data.split(":")
    if len(parts) != 3:
        return

    title_id = parts[1]
    try:
        owner_id = int(parts[2])
    except (ValueError, IndexError):
        return
    user_id = update.effective_user.id

    if user_id != owner_id:
        await query.answer("⚠️ Эта кнопка не для тебя", show_alert=True)
        return

    # Ban check
    with get_db() as db:
        user_check = db.query(User).filter(User.telegram_id == user_id).first()
        if not user_check or user_check.is_banned:
            await query.answer("Доступ запрещён", show_alert=True)
            return

    await query.answer()

    # Handle remove title
    if title_id == "remove":
        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == user_id).first()
            user.active_title = None

        await safe_edit_message(query, "🚫 Титул снят\n\n/shop — магазин")
        return

    # Check if valid title
    if title_id not in SHOP_TITLES:
        return

    title_data = SHOP_TITLES[title_id]

    # Block streak-exclusive titles (price=0) from being bought via crafted callback
    if title_data["price"] == 0:
        await query.answer("❌ Этот титул можно получить только из сундуков", show_alert=True)
        return

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        owned = get_user_titles(user)

        if title_id in owned:
            # Already owned — equip it
            user.active_title = title_id
            await safe_edit_message(
                query,
                f"✅ Титул установлен: {title_data['display']}\n\n/shop — магазин",
            )
            logger.info("Title equipped", user_id=user_id, title=title_id)
            return

        # Need to buy
        if user.balance < title_data["price"]:
            await safe_edit_message(
                query,
                f"❌ Недостаточно алмазов\n\n"
                f"Цена: {format_diamonds(title_data['price'])}\n"
                f"У тебя: {format_diamonds(user.balance)}",
            )
            return

        # Buy and equip
        user.balance -= title_data["price"]
        add_user_title(user, title_id)
        user.active_title = title_id
        balance = user.balance

    await safe_edit_message(
        query,
        f"🎉 <b>Куплено!</b>\n\n"
        f"Титул: {title_data['display']}\n"
        f"Потрачено: {format_diamonds(title_data['price'])}\n"
        f"Баланс: {format_diamonds(balance)}\n\n"
        f"/shop — магазин",
    )

    logger.info("Title purchased", user_id=user_id, title=title_id, price=title_data["price"])


def register_shop_handlers(application):
    """Register shop handlers."""
    application.add_handler(CommandHandler("shop", shop_command))
    application.add_handler(CallbackQueryHandler(shop_callback, pattern=r"^shop:"))
    logger.info("Shop handlers registered")
