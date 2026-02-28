"""Тотализатор — periodic community betting events in production chat."""

import html
import random
from datetime import datetime, timedelta
from typing import Dict, Optional

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.constants import PRODUCTION_CHAT_ID
from app.database.connection import get_db
from app.database.models import User
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds, format_word
from app.utils.telegram_helpers import schedule_delete

logger = structlog.get_logger()

# ==================== CONSTANTS ====================

TOTO_DURATION_MINUTES = 30
TOTO_MIN_BET = 100
TOTO_MAX_BET = 5000
TOTO_HOUSE_CUT = 0.10  # 10%

# ==================== QUESTIONS POOL ====================

QUESTIONS = [
    {"q": "🔴 Красное или ⚫ Чёрное?", "a": "🔴 Красное", "b": "⚫ Чёрное"},
    {"q": "🔥 Огонь или 💧 Вода?", "a": "🔥 Огонь", "b": "💧 Вода"},
    {"q": "☀️ Солнце или 🌙 Луна?", "a": "☀️ Солнце", "b": "🌙 Луна"},
    {"q": "⚔️ Атака или 🛡 Защита?", "a": "⚔️ Атака", "b": "🛡 Защита"},
    {"q": "🐉 Дракон или 🦅 Орёл?", "a": "🐉 Дракон", "b": "🦅 Орёл"},
    {"q": "💎 Алмаз или 🪙 Золото?", "a": "💎 Алмаз", "b": "🪙 Золото"},
    {"q": "🏔 Горы или 🏖 Пляж?", "a": "🏔 Горы", "b": "🏖 Пляж"},
    {"q": "🐺 Волк или 🦊 Лиса?", "a": "🐺 Волк", "b": "🦊 Лиса"},
    {"q": "⬆️ Вверх или ⬇️ Вниз?", "a": "⬆️ Вверх", "b": "⬇️ Вниз"},
    {"q": "🚀 Ракета или 🛸 НЛО?", "a": "🚀 Ракета", "b": "🛸 НЛО"},
    {"q": "🍕 Пицца или 🍔 Бургер?", "a": "🍕 Пицца", "b": "🍔 Бургер"},
    {"q": "🗡 Меч или 🏹 Лук?", "a": "🗡 Меч", "b": "🏹 Лук"},
    {"q": "🌊 Шторм или 🌈 Радуга?", "a": "🌊 Шторм", "b": "🌈 Радуга"},
    {"q": "🎸 Рок или 🎤 Поп?", "a": "🎸 Рок", "b": "🎤 Поп"},
    {"q": "🐱 Кот или 🐶 Пёс?", "a": "🐱 Кот", "b": "🐶 Пёс"},
]

# ==================== IN-MEMORY STATE ====================

_active_round: Optional[Dict] = None


# ==================== ROUND HELPERS ====================


def _build_announcement(r: Dict, closed: bool = False) -> str:
    status = "🔒 ЗАКРЫТ" if closed else "🟢 СТАВКИ ОТКРЫТЫ"
    total_pool = r["pool_a"] + r["pool_b"]
    total_players = r["count_a"] + r["count_b"]

    remaining = ""
    if not closed:
        delta = r["closes_at"] - datetime.utcnow()
        mins = max(0, int(delta.total_seconds() // 60))
        remaining = f"\n⏰ Закрытие через {mins} мин"

    return (
        f"🎰 <b>ТОТАЛИЗАТОР</b> [{status}]\n\n"
        f"{r['question']}\n\n"
        f"<b>{r['option_a']}</b> — {format_diamonds(r['pool_a'])} ({r['count_a']} чел.)\n"
        f"<b>{r['option_b']}</b> — {format_diamonds(r['pool_b'])} ({r['count_b']} чел.)\n\n"
        f"💰 Пул: {format_diamonds(total_pool)} | "
        f"{format_word(total_players, 'игрок', 'игрока', 'игроков')}"
        f"{remaining}\n"
        f"📊 Ставка: {format_diamonds(TOTO_MIN_BET)} — {format_diamonds(TOTO_MAX_BET)}"
    )


def _build_side_keyboard(r: Dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(r["option_a"], callback_data="toto:side:a"),
                InlineKeyboardButton(r["option_b"], callback_data="toto:side:b"),
            ]
        ]
    )


def _build_bet_picker(side: str, option_name: str, user_id: int) -> InlineKeyboardMarkup:
    amounts = [100, 250, 500, 1000, 2500, 5000]
    rows = []
    row = []
    for amt in amounts:
        row.append(InlineKeyboardButton(f"{amt}💎", callback_data=f"toto:bet:{side}:{amt}:{user_id}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("« Отмена", callback_data=f"toto:cancel:{user_id}")])
    return InlineKeyboardMarkup(rows)


# ==================== SCHEDULER JOBS ====================


async def start_toto_round(application):
    """APScheduler job: start a new round and post in production chat."""
    global _active_round

    if _active_round and not _active_round.get("resolved"):
        return  # Round still active

    q = random.choice(QUESTIONS)
    now = datetime.utcnow()
    new_round = {
        "question": q["q"],
        "option_a": q["a"],
        "option_b": q["b"],
        "bets": {},  # {user_id: {"side": "a"/"b", "amount": int}}
        "pool_a": 0,
        "pool_b": 0,
        "count_a": 0,
        "count_b": 0,
        "created_at": now,
        "closes_at": now + timedelta(minutes=TOTO_DURATION_MINUTES),
        "message_id": None,
        "chat_id": PRODUCTION_CHAT_ID,
        "resolved": False,
    }

    try:
        msg = await application.bot.send_message(
            chat_id=PRODUCTION_CHAT_ID,
            text=_build_announcement(new_round),
            parse_mode="HTML",
            reply_markup=_build_side_keyboard(new_round),
        )
        new_round["message_id"] = msg.message_id
        _active_round = new_round

        # Schedule resolution via APScheduler
        from app.tasks.scheduler import scheduler

        if scheduler:
            scheduler.add_job(
                resolve_toto_round,
                trigger="date",
                run_date=datetime.now() + timedelta(minutes=TOTO_DURATION_MINUTES),
                args=[application],
                id="toto_resolve",
                replace_existing=True,
            )

        logger.info("Toto round started", question=q["q"])
    except Exception as e:
        logger.error("Failed to start toto round", error=str(e))
        _active_round = None


async def resolve_toto_round(application):
    """APScheduler job: resolve active round, distribute payouts."""
    global _active_round

    r = _active_round
    if not r or r.get("resolved"):
        return

    r["resolved"] = True
    total_pool = r["pool_a"] + r["pool_b"]

    # Not enough — refund all
    if r["count_a"] == 0 or r["count_b"] == 0:
        with get_db() as db:
            for uid, bet_info in r["bets"].items():
                user = db.query(User).filter(User.telegram_id == uid).first()
                if user:
                    user.balance += bet_info["amount"]

        try:
            await application.bot.edit_message_text(
                chat_id=r["chat_id"],
                message_id=r["message_id"],
                text=(
                    f"🎰 <b>ТОТАЛИЗАТОР</b> [ОТМЕНЁН]\n\n"
                    f"{r['question']}\n\n"
                    f"❌ Ставки только на одну сторону\n"
                    f"💰 Все ставки возвращены"
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass

        _active_round = None
        return

    # Determine winner (50/50)
    winning_side = random.choice(["a", "b"])
    losing_side = "b" if winning_side == "a" else "a"

    winning_option = r[f"option_{winning_side}"]
    losing_pool = r[f"pool_{losing_side}"]
    winning_pool = r[f"pool_{winning_side}"]

    # House cut from losing pool
    house_take = int(losing_pool * TOTO_HOUSE_CUT)
    distributable = losing_pool - house_take

    # Distribute winnings proportionally
    winners = []
    with get_db() as db:
        for uid, bet_info in r["bets"].items():
            if bet_info["side"] == winning_side:
                share = int(bet_info["amount"] / winning_pool * distributable)
                payout = bet_info["amount"] + share
                user = db.query(User).filter(User.telegram_id == uid).first()
                if user:
                    user.balance += payout
                    winners.append((uid, bet_info["amount"], share, user.username))

    # Build results text
    winners_text = ""
    for uid, bet, share, username in sorted(winners, key=lambda x: -x[2])[:10]:
        display = f"@{html.escape(username)}" if username else f"ID {uid}"
        winners_text += f"  {display}: +{format_diamonds(share)}\n"

    winning_count = r[f"count_{winning_side}"]

    result_text = (
        f"🎰 <b>ТОТАЛИЗАТОР</b> [РЕЗУЛЬТАТ]\n\n"
        f"{r['question']}\n\n"
        f"🏆 Победа: <b>{winning_option}</b>\n\n"
        f"💰 Пул: {format_diamonds(total_pool)}\n"
        f"🏦 Комиссия: {format_diamonds(house_take)}\n"
        f"🎉 {format_word(winning_count, 'победитель', 'победителя', 'победителей')} "
        f"делят {format_diamonds(distributable)}\n\n"
    )

    if winners_text:
        result_text += f"<b>Выигрыши:</b>\n{winners_text}"

    try:
        await application.bot.edit_message_text(
            chat_id=r["chat_id"],
            message_id=r["message_id"],
            text=result_text,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error("Failed to post toto results", error=str(e))

    logger.info(
        "Toto round resolved",
        winning_side=winning_side,
        total_pool=total_pool,
        house_take=house_take,
        winners=len(winners),
    )
    _active_round = None


# ==================== CALLBACK HANDLER ====================


async def toto_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all toto:* callbacks."""
    query = update.callback_query
    if not query or not update.effective_user:
        return

    data = query.data
    parts = data.split(":")
    action = parts[1]
    user_id = update.effective_user.id

    if action == "side":
        # Public button — anyone can click
        r = _active_round
        if not r or r.get("resolved"):
            await query.answer("Нет активного раунда", show_alert=True)
            return

        if datetime.utcnow() >= r["closes_at"]:
            await query.answer("Приём ставок закрыт", show_alert=True)
            return

        if user_id in r["bets"]:
            existing = r["bets"][user_id]
            side_name = r[f"option_{existing['side']}"]
            await query.answer(f"Ты уже поставил {format_diamonds(existing['amount'])} на {side_name}", show_alert=True)
            return

        # Check registration + ban
        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == user_id).first()
            if not user:
                await query.answer("Сначала зарегистрируйся: /start", show_alert=True)
                return
            if user.is_banned:
                await query.answer("Забанен", show_alert=True)
                return

        await query.answer()

        side = parts[2]
        option_name = r[f"option_{side}"]

        # Send bet picker as reply to announcement
        picker_text = f"🎰 Ставка на <b>{option_name}</b>\n\nВыбери сумму:"
        picker_kb = _build_bet_picker(side, option_name, user_id)

        msg = await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=picker_text,
            parse_mode="HTML",
            reply_markup=picker_kb,
            reply_to_message_id=query.message.message_id,
        )

        # Auto-delete picker after 60s
        schedule_delete(context, query.message.chat_id, [msg.message_id], delay=60)

    elif action == "bet":
        try:
            side = parts[2]
            amount = int(parts[3])
            owner_id = int(parts[4])
        except (ValueError, IndexError):
            return

        if user_id != owner_id:
            await query.answer("Эта кнопка не для тебя", show_alert=True)
            return

        r = _active_round
        if not r or r.get("resolved"):
            await query.answer("Раунд завершён", show_alert=True)
            return

        if datetime.utcnow() >= r["closes_at"]:
            await query.answer("Приём ставок закрыт", show_alert=True)
            return

        if user_id in r["bets"]:
            await query.answer("Ты уже сделал ставку", show_alert=True)
            return

        # Validate and deduct
        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == user_id).first()
            if not user or user.is_banned:
                await query.answer("Доступ запрещён", show_alert=True)
                return

            if user.balance < amount:
                await query.answer(f"Недостаточно: {format_diamonds(user.balance)}", show_alert=True)
                return

            user.balance -= amount

        # Record bet
        r["bets"][user_id] = {"side": side, "amount": amount}
        r[f"pool_{side}"] += amount
        r[f"count_{side}"] += 1

        option_name = r[f"option_{side}"]
        await query.answer(f"Ставка {format_diamonds(amount)} на {option_name} принята!")

        # Edit picker to confirmation
        try:
            await query.edit_message_text(
                f"✅ <b>Ставка принята!</b>\n\n"
                f"🎰 {option_name}: {format_diamonds(amount)}\n"
                f"💰 Пул: {format_diamonds(r['pool_a'] + r['pool_b'])}",
                parse_mode="HTML",
            )
        except Exception:
            pass

        # Update main announcement (may fail on flood control — ok)
        try:
            await context.bot.edit_message_text(
                chat_id=r["chat_id"],
                message_id=r["message_id"],
                text=_build_announcement(r),
                parse_mode="HTML",
                reply_markup=_build_side_keyboard(r),
            )
        except Exception:
            pass

        logger.info("Toto bet placed", user_id=user_id, side=side, amount=amount)

    elif action == "cancel":
        owner_id = int(parts[2])
        if user_id != owner_id:
            await query.answer("Эта кнопка не для тебя", show_alert=True)
            return

        await query.answer()
        try:
            await query.delete_message()
        except Exception:
            pass


# ==================== COMMANDS ====================


@require_registered
async def toto_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current toto round status."""
    if not update.message or not update.effective_user:
        return

    r = _active_round
    if not r or r.get("resolved"):
        await update.message.reply_text(
            "🎰 <b>Тотализатор</b>\n\n" "Сейчас нет активного раунда\n" "Раунды открываются каждые 3 часа в чате",
            parse_mode="HTML",
        )
        return

    user_id = update.effective_user.id
    text = _build_announcement(r)

    if user_id in r["bets"]:
        bet = r["bets"][user_id]
        option = r[f"option_{bet['side']}"]
        text += f"\n\n✅ Твоя ставка: {format_diamonds(bet['amount'])} на {option}"
        await update.message.reply_text(text, parse_mode="HTML")
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=_build_side_keyboard(r))


# ==================== SHUTDOWN REFUND ====================


def refund_active_toto():
    """Refund all bets on shutdown (called from post_shutdown)."""
    global _active_round
    r = _active_round
    if not r or r.get("resolved"):
        return

    with get_db() as db:
        for uid, bet_info in r["bets"].items():
            user = db.query(User).filter(User.telegram_id == uid).first()
            if user:
                user.balance += bet_info["amount"]

    logger.info("Refunded toto bets on shutdown", count=len(r["bets"]))
    _active_round = None


# ==================== REGISTRATION ====================


def register_toto_handlers(application):
    """Register toto handlers."""
    application.add_handler(CommandHandler("toto", toto_command))
    application.add_handler(CallbackQueryHandler(toto_callback, pattern=r"^toto:"))
