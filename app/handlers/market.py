"""Чёрный рынок — rotating risky deals, refreshes every 8 hours."""

import html
import random
from datetime import datetime
from typing import Dict, List, Optional

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import User
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds
from app.utils.telegram_helpers import delete_command_and_reply, safe_edit_message

logger = structlog.get_logger()

# ==================== ITEM CATALOG ====================

MARKET_ITEMS = [
    {
        "id": "mystery_small",
        "name": "📦 Маленький сундук",
        "desc": "Случайная награда: 50-500💎",
        "price": 200,
        "stock": 5,
        "action": "mystery",
        "params": {"min": 50, "max": 500},
    },
    {
        "id": "mystery_big",
        "name": "🎁 Большой сундук",
        "desc": "Случайная награда: 200-2000💎",
        "price": 800,
        "stock": 3,
        "action": "mystery",
        "params": {"min": 200, "max": 2000},
    },
    {
        "id": "stolen_gems",
        "name": "💎 Краденые алмазы",
        "desc": "1000💎 за полцены, 30% шанс ареста",
        "price": 500,
        "stock": 3,
        "action": "stolen",
        "params": {"reward": 1000, "catch_chance": 0.30, "fine": 500},
    },
    {
        "id": "contraband",
        "name": "🚬 Контрабанда",
        "desc": "2000💎 за четверть цены, 40% шанс ареста",
        "price": 500,
        "stock": 2,
        "action": "stolen",
        "params": {"reward": 2000, "catch_chance": 0.40, "fine": 750},
    },
    {
        "id": "cooldown_reset",
        "name": "⏰ Сброс кулдауна",
        "desc": "Сбрасывает кулдаун на /job",
        "price": 250,
        "stock": 5,
        "action": "cooldown_reset",
        "params": {},
    },
    {
        "id": "diamond_dust",
        "name": "✨ Алмазная пыль",
        "desc": "50% шанс x3, 50% потерять всё",
        "price": 300,
        "stock": 4,
        "action": "gamble",
        "params": {"multiplier": 3, "win_chance": 0.50},
    },
    {
        "id": "loaded_dice",
        "name": "🎲 Шулерские кости",
        "desc": "40% шанс x4, 60% потеря",
        "price": 400,
        "stock": 3,
        "action": "gamble",
        "params": {"multiplier": 4, "win_chance": 0.40},
    },
    {
        "id": "info_broker",
        "name": "🕵️ Информатор",
        "desc": "Баланс 3 случайных игроков",
        "price": 150,
        "stock": 5,
        "action": "info",
        "params": {},
    },
    {
        "id": "mega_chest",
        "name": "👑 Королевский сундук",
        "desc": "Награда: 500-5000💎",
        "price": 2000,
        "stock": 1,
        "action": "mystery",
        "params": {"min": 500, "max": 5000},
    },
    {
        "id": "dark_deal",
        "name": "🃏 Тёмная сделка",
        "desc": "33% шанс x5, 67% потеря",
        "price": 500,
        "stock": 2,
        "action": "gamble",
        "params": {"multiplier": 5, "win_chance": 0.33},
    },
]

# ==================== IN-MEMORY STATE ====================

_REFRESH_HOURS = 8
_current_stock: Optional[Dict] = None


def _should_refresh() -> bool:
    if _current_stock is None:
        return True
    hours_since = (datetime.utcnow() - _current_stock["refreshed_at"]).total_seconds() / 3600
    return hours_since >= _REFRESH_HOURS


def _refresh_stock():
    global _current_stock
    items = random.sample(MARKET_ITEMS, k=min(5, len(MARKET_ITEMS)))
    stock_items = []
    for item in items:
        stock_items.append({**item, "remaining": item["stock"]})
    _current_stock = {
        "items": stock_items,
        "refreshed_at": datetime.utcnow(),
    }


def _get_stock() -> Dict:
    if _should_refresh():
        _refresh_stock()
    return _current_stock


# ==================== HELPERS ====================


def _build_market_text(stock: Dict) -> str:
    hours_left = _REFRESH_HOURS - (datetime.utcnow() - stock["refreshed_at"]).total_seconds() / 3600
    hours_left = max(0, int(hours_left))

    text = f"🏴 <b>Чёрный рынок</b>\n\n⏰ Обновление через {hours_left}ч\n\n"

    for i, item in enumerate(stock["items"], 1):
        sold_out = "❌ ПРОДАНО" if item["remaining"] <= 0 else f"📦 {item['remaining']} шт."
        text += (
            f"{i}. <b>{item['name']}</b> — {format_diamonds(item['price'])}\n"
            f"   {item['desc']}\n"
            f"   {sold_out}\n\n"
        )

    return text


def _build_market_keyboard(user_id: int, stock: Dict) -> InlineKeyboardMarkup:
    rows = []
    for item in stock["items"]:
        if item["remaining"] > 0:
            rows.append(
                [
                    InlineKeyboardButton(
                        f"{item['name']} ({format_diamonds(item['price'])})",
                        callback_data=f"market:buy:{item['id']}:{user_id}",
                    )
                ]
            )
    rows.append([InlineKeyboardButton("« Игры", callback_data=f"menu:games:{user_id}")])
    return InlineKeyboardMarkup(rows)


def _process_purchase(db, user: User, item: Dict) -> str:
    """Process item effect in the same DB transaction as payment."""
    action = item["action"]
    params = item["params"]

    if action == "mystery":
        reward = random.randint(params["min"], params["max"])
        user.balance += reward
        return (
            f"📦 <b>Открыт!</b>\n\n"
            f"Внутри: {format_diamonds(reward)}\n"
            f"💰 Баланс: {format_diamonds(user.balance)}"
        )

    elif action == "stolen":
        caught = random.random() < params["catch_chance"]
        if caught:
            fine = min(params["fine"], user.balance)
            user.balance -= fine
            return (
                f"🚨 <b>Попался!</b>\n\n"
                f"Интерпол задержал при покупке\n"
                f"💸 Штраф: {format_diamonds(fine)}\n"
                f"💰 Баланс: {format_diamonds(user.balance)}"
            )
        else:
            user.balance += params["reward"]
            return (
                f"🤫 <b>Сделка прошла!</b>\n\n"
                f"Получено: {format_diamonds(params['reward'])}\n"
                f"💰 Баланс: {format_diamonds(user.balance)}"
            )

    elif action == "cooldown_reset":
        from app.database.models import Cooldown

        db.query(Cooldown).filter(Cooldown.user_id == user.telegram_id, Cooldown.action == "work").delete()
        return f"⏰ <b>Кулдаун сброшен!</b>\n\nМожно снова /job\n💰 Баланс: {format_diamonds(user.balance)}"

    elif action == "gamble":
        won = random.random() < params.get("win_chance", 0.5)
        if won:
            reward = item["price"] * params["multiplier"]
            user.balance += reward
            return (
                f"✨ <b>Джекпот!</b>\n\n"
                f"Награда: {format_diamonds(reward)} (x{params['multiplier']})\n"
                f"💰 Баланс: {format_diamonds(user.balance)}"
            )
        else:
            return f"💨 <b>Пшик...</b>\n\nТовар оказался подделкой\n💰 Баланс: {format_diamonds(user.balance)}"

    elif action == "info":
        from sqlalchemy import func

        players = (
            db.query(User)
            .filter(User.telegram_id != user.telegram_id, User.is_banned.is_(False))
            .order_by(func.random())
            .limit(3)
            .all()
        )
        info = ""
        for p in players:
            display = f"@{html.escape(p.username)}" if p.username else f"ID {p.telegram_id}"
            info += f"  {display}: {format_diamonds(p.balance)}\n"
        return f"🕵️ <b>Разведданные:</b>\n\n{info}\n💰 Баланс: {format_diamonds(user.balance)}"

    return f"✅ Куплено!\n💰 Баланс: {format_diamonds(user.balance)}"


# ==================== HANDLERS ====================


@require_registered
async def market_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show black market."""
    if not update.message or not update.effective_user:
        return

    user_id = update.effective_user.id
    stock = _get_stock()
    text = _build_market_text(stock)
    keyboard = _build_market_keyboard(user_id, stock)

    reply = await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
    await delete_command_and_reply(update, reply, context, delay=120)


async def market_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle market:* callbacks."""
    query = update.callback_query
    if not query or not update.effective_user:
        return

    data = query.data
    parts = data.split(":")
    action = parts[1]
    user_id = update.effective_user.id

    if action == "buy":
        item_id = parts[2]
        owner_id = int(parts[3])

        if user_id != owner_id:
            await query.answer("Эта кнопка не для тебя", show_alert=True)
            return

        # Ban check
        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == user_id).first()
            if not user or user.is_banned:
                await query.answer("Доступ запрещён", show_alert=True)
                return

        await query.answer()

        stock = _get_stock()
        item = None
        for it in stock["items"]:
            if it["id"] == item_id:
                item = it
                break

        if not item:
            await safe_edit_message(query, "❌ Товар не найден")
            return

        if item["remaining"] <= 0:
            await safe_edit_message(query, "❌ Товар распродан")
            return

        # Deduct price + process item in single transaction
        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == user_id).first()
            if user.balance < item["price"]:
                await safe_edit_message(
                    query,
                    f"❌ Недостаточно алмазов\n\nНужно: {format_diamonds(item['price'])}\nБаланс: {format_diamonds(user.balance)}",
                )
                return

            user.balance -= item["price"]
            item["remaining"] -= 1

            result = _process_purchase(db, user, item)

        # Update message
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("« Рынок", callback_data=f"market:list:{user_id}")]]
        )
        await safe_edit_message(query, result, reply_markup=keyboard)

        logger.info("Market purchase", user_id=user_id, item=item_id)

    elif action == "list":
        owner_id = int(parts[2])
        if user_id != owner_id:
            await query.answer("Эта кнопка не для тебя", show_alert=True)
            return

        await query.answer()
        stock = _get_stock()
        text = _build_market_text(stock)
        keyboard = _build_market_keyboard(user_id, stock)
        await safe_edit_message(query, text, reply_markup=keyboard)


# ==================== REGISTRATION ====================


def register_market_handlers(application):
    """Register market handlers."""
    application.add_handler(CommandHandler("market", market_command))
    application.add_handler(CallbackQueryHandler(market_callback, pattern=r"^market:"))
