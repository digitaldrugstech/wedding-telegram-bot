"""Scratch card command handlers."""

import asyncio
import random
from collections import Counter
from datetime import datetime, timedelta

import structlog
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import CasinoGame, Cooldown, User
from app.handlers.quest import update_quest_progress
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds

logger = structlog.get_logger()

SCRATCH_COOLDOWN_SECONDS = 30
SCRATCH_MIN_BET = 10
SCRATCH_MAX_BET = 1000

# Prize tiers with weights (total weight=100)
# EV = 0.02*5 + 0.13*2.5 + 0.25*1.5 + 0.60*0 = 0.10 + 0.325 + 0.375 = 0.80
# House edge = 20%
SCRATCH_PRIZES = [
    {"symbol": "\U0001f48e", "name": "Алмаз", "multiplier": 5.0, "weight": 2},
    {"symbol": "\u2b50", "name": "Звезда", "multiplier": 2.5, "weight": 13},
    {"symbol": "\U0001f381", "name": "Подарок", "multiplier": 1.5, "weight": 25},
    {"symbol": "\u274c", "name": "Пусто", "multiplier": 0, "weight": 60},
]

# Symbols for grid decoration
GRID_SYMBOLS = ["\U0001f48e", "\u2b50", "\U0001f381", "\U0001f340", "\U0001f525", "\U0001f4b0"]


def generate_scratch_result():
    """Generate scratch card result using weighted random."""
    weights = [p["weight"] for p in SCRATCH_PRIZES]
    return random.choices(SCRATCH_PRIZES, weights=weights, k=1)[0]


def generate_grid(winning_symbol=None, is_win=False):
    """Generate a 3x3 visual grid for display."""
    if is_win and winning_symbol:
        # Place 3 winning symbols + 6 random others
        other_symbols = [s for s in GRID_SYMBOLS if s != winning_symbol]
        grid = [winning_symbol] * 3 + [random.choice(other_symbols) for _ in range(6)]
        random.shuffle(grid)
    else:
        # No win — max 2 of any symbol (guaranteed by pool of 2 each)
        pool = GRID_SYMBOLS * 2
        random.shuffle(pool)
        grid = pool[:9]
    return grid


def format_grid(grid, revealed=None):
    """Format grid as text. revealed=None shows all, otherwise only revealed positions."""
    rows = []
    for row in range(3):
        cells = []
        for col in range(3):
            idx = row * 3 + col
            if revealed is None or idx in revealed:
                cells.append(grid[idx])
            else:
                cells.append("\u2b1c")
        rows.append(" ".join(cells))
    return "\n".join(rows)


@require_registered
async def scratch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scratch card game (/scratch [bet])."""
    user_id = update.effective_user.id

    # Parse bet
    if not context.args:
        await update.message.reply_text(
            "\U0001f3ab <b>Скретч-карта</b>\n\n"
            f"Используй: /scratch [ставка]\n"
            f"Лимиты: {format_diamonds(SCRATCH_MIN_BET)} - {format_diamonds(SCRATCH_MAX_BET)}\n\n"
            "Царапай и ищи 3 одинаковых символа!\n\n"
            "\U0001f48e x5 | \u2b50 x2.5 | \U0001f381 x1.5",
            parse_mode="HTML",
        )
        return

    try:
        bet = int(context.args[0])
    except ValueError:
        await update.message.reply_text("\u274c Ставка должна быть числом")
        return

    if bet < SCRATCH_MIN_BET or bet > SCRATCH_MAX_BET:
        await update.message.reply_text(
            f"\u274c Ставка: {format_diamonds(SCRATCH_MIN_BET)} - {format_diamonds(SCRATCH_MAX_BET)}"
        )
        return

    # Phase 1: Check balance and cooldown, deduct bet
    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()

        if user.balance < bet:
            await update.message.reply_text(
                f"\u274c Недостаточно алмазов\n\n"
                f"Нужно: {format_diamonds(bet)}\n"
                f"У тебя: {format_diamonds(user.balance)}"
            )
            return

        cooldown = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "scratch").first()

        if cooldown and cooldown.expires_at > datetime.utcnow():
            remaining = cooldown.expires_at - datetime.utcnow()
            seconds_left = int(remaining.total_seconds())
            await update.message.reply_text(f"\u23f0 Следующая скретч-карта через {seconds_left}с")
            return

        # Deduct bet and set cooldown
        user.balance -= bet

        expires_at = datetime.utcnow() + timedelta(seconds=SCRATCH_COOLDOWN_SECONDS)
        if cooldown:
            cooldown.expires_at = expires_at
        else:
            cooldown = Cooldown(user_id=user_id, action="scratch", expires_at=expires_at)
            db.add(cooldown)

    # Phase 2: Generate result and animate (DB session released)
    prize = generate_scratch_result()
    is_win = prize["multiplier"] > 0
    winning_symbol = prize["symbol"] if is_win else None
    grid = generate_grid(winning_symbol, is_win)

    hidden_grid = format_grid(grid, revealed=set())
    msg = await update.message.reply_text(
        f"\U0001f3ab <b>Скретч-карта</b>\n\n{hidden_grid}\n\nЦарапаю...",
        parse_mode="HTML",
    )

    # Reveal squares progressively
    reveal_order = list(range(9))
    random.shuffle(reveal_order)
    reveal_steps = [3, 5, 7, 9]

    for step in reveal_steps:
        await asyncio.sleep(0.6)
        revealed = set(reveal_order[:step])
        partial_grid = format_grid(grid, revealed)
        try:
            await msg.edit_text(
                f"\U0001f3ab <b>Скретч-карта</b>\n\n{partial_grid}\n\nЦарапаю...",
                parse_mode="HTML",
            )
        except Exception:
            pass

    await asyncio.sleep(0.4)

    # Phase 3: Calculate payout and award
    payout = int(bet * prize["multiplier"])

    with get_db() as db:
        if payout > 0:
            user = db.query(User).filter(User.telegram_id == user_id).first()
            user.balance += payout

        result_type = "win" if payout > 0 else "loss"
        game = CasinoGame(user_id=user_id, bet_amount=bet, result=result_type, payout=payout)
        db.add(game)

    # Build result text
    full_grid = format_grid(grid)

    if prize["multiplier"] == 5.0:
        result_text = (
            f"\U0001f3ab <b>ДЖЕКПОТ!</b> \U0001f389\U0001f389\U0001f389\n\n"
            f"{full_grid}\n\n"
            f"3x {prize['symbol']} \u2014 Множитель x5!\n"
            f"Выигрыш: {format_diamonds(payout)}"
        )
    elif payout > 0:
        net = payout - bet
        result_text = (
            f"\U0001f3ab <b>Победа!</b>\n\n"
            f"{full_grid}\n\n"
            f"3x {prize['symbol']} \u2014 Множитель x{prize['multiplier']}\n"
            f"Выигрыш: {format_diamonds(payout)}\n"
            f"Чистая прибыль: {format_diamonds(net)}"
        )
    else:
        result_text = (
            f"\U0001f3ab <b>Скретч-карта</b>\n\n"
            f"{full_grid}\n\n"
            f"Нет совпадений...\n"
            f"Потрачено: {format_diamonds(bet)}"
        )

    try:
        await msg.edit_text(result_text, parse_mode="HTML")
    except Exception:
        await update.message.reply_text(result_text, parse_mode="HTML")

    # Track quest
    try:
        update_quest_progress(user_id, "casino")
    except Exception:
        pass

    logger.info("Scratch card played", user_id=user_id, bet=bet, payout=payout, symbol=prize["symbol"])


def register_scratch_handlers(application):
    """Register scratch card handlers."""
    application.add_handler(CommandHandler("scratch", scratch_command))
    logger.info("Scratch card handlers registered")
