"""Russian roulette — multiplayer gambling minigame."""

import asyncio
import html
import random
from datetime import datetime

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import CasinoGame, User
from app.handlers.quest import update_quest_progress
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds, format_word

logger = structlog.get_logger()

RR_MIN_BET = 50
RR_MAX_BET = 5000
RR_MIN_PLAYERS = 2
RR_MAX_PLAYERS = 6
RR_JOIN_TIMEOUT_SECONDS = 90  # 1.5 minutes to join
RR_HOUSE_FEE_PERCENT = 5  # 5% house cut

# Active rounds: {chat_id: {bet, players: {user_id: username}, host_id, created_at}}
active_rounds = {}


@require_registered
async def rr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /rr [bet] — start a Russian roulette round."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not context.args:
        await update.message.reply_text(
            "🔫 <b>Русская рулетка</b>\n\n"
            f"/rr [ставка] — начать раунд\n\n"
            f"• {RR_MIN_PLAYERS}-{RR_MAX_PLAYERS} игроков, каждый ставит одинаково\n"
            f"• Один «умирает» — теряет ставку\n"
            f"• Остальные делят выигрыш\n"
            f"• Комиссия: {RR_HOUSE_FEE_PERCENT}%\n\n"
            f"Ставки: {format_diamonds(RR_MIN_BET)} - {format_diamonds(RR_MAX_BET)}\n\n"
            f"<i>Чем больше игроков, тем выгоднее!</i>",
            parse_mode="HTML",
        )
        return

    try:
        bet = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Ставка должна быть числом")
        return

    if bet < RR_MIN_BET or bet > RR_MAX_BET:
        await update.message.reply_text(f"❌ Ставка: {format_diamonds(RR_MIN_BET)} - {format_diamonds(RR_MAX_BET)}")
        return

    # Check if round already active in this chat
    if chat_id in active_rounds:
        await update.message.reply_text("❌ В этом чате уже идёт раунд\n\nДождись окончания или присоединяйся!")
        return

    # Check balance
    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user or user.balance < bet:
            await update.message.reply_text(
                f"❌ Недостаточно алмазов\n\nНужно: {format_diamonds(bet)}\n"
                f"У тебя: {format_diamonds(user.balance if user else 0)}"
            )
            return

        # Reserve bet
        user.balance -= bet
        balance = user.balance

    if update.effective_user.username:
        display_name = f"@{html.escape(update.effective_user.username)}"
    else:
        display_name = html.escape(update.effective_user.first_name or f"User{user_id}")

    active_rounds[chat_id] = {
        "bet": bet,
        "players": {user_id: display_name},
        "host_id": user_id,
        "created_at": datetime.utcnow(),
    }

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(f"🔫 Войти ({format_diamonds(bet)})", callback_data=f"rr:join:{chat_id}"),
            ],
            [
                InlineKeyboardButton("🎯 КРУТИТЬ!", callback_data=f"rr:spin:{chat_id}:{user_id}"),
            ],
        ]
    )

    await update.message.reply_text(
        f"🔫 <b>Русская рулетка</b>\n\n"
        f"💰 Ставка: {format_diamonds(bet)} с каждого\n\n"
        f"👥 Игроки (1/{RR_MAX_PLAYERS}):\n"
        f"• {display_name}\n\n"
        f"⏰ {RR_JOIN_TIMEOUT_SECONDS // 60}м {RR_JOIN_TIMEOUT_SECONDS % 60}с на вход\n"
        f"Нужно минимум {format_word(RR_MIN_PLAYERS, 'игрок', 'игрока', 'игроков')}\n\n"
        f"<i>Организатор нажимает «КРУТИТЬ!» когда все готовы</i>",
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    logger.info("RR round started", user_id=user_id, chat_id=chat_id, bet=bet)


async def rr_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle join button for Russian roulette."""
    query = update.callback_query
    if not query or not update.effective_user:
        return

    user_id = update.effective_user.id
    parts = query.data.split(":")
    chat_id = int(parts[2])

    if chat_id not in active_rounds:
        await query.answer("❌ Раунд уже завершён", show_alert=True)
        return

    rnd = active_rounds[chat_id]

    # Check timeout
    elapsed = (datetime.utcnow() - rnd["created_at"]).total_seconds()
    if elapsed > RR_JOIN_TIMEOUT_SECONDS:
        # Refund all players
        _refund_all(rnd)
        del active_rounds[chat_id]
        await query.answer("❌ Время вышло, ставки возвращены", show_alert=True)
        return

    if user_id in rnd["players"]:
        await query.answer("Ты уже в игре!", show_alert=True)
        return

    if len(rnd["players"]) >= RR_MAX_PLAYERS:
        await query.answer("❌ Максимум игроков!", show_alert=True)
        return

    bet = rnd["bet"]

    # Check registration, ban, and balance
    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            await query.answer("❌ Ты не зарегистрирован — /start", show_alert=True)
            return
        if user.is_banned:
            await query.answer("❌ Ты забанен", show_alert=True)
            return
        if user.balance < bet:
            await query.answer(f"❌ Нужно {format_diamonds(bet)}", show_alert=True)
            return
        user.balance -= bet

    if update.effective_user.username:
        display_name = f"@{html.escape(update.effective_user.username)}"
    else:
        display_name = html.escape(update.effective_user.first_name or f"User{user_id}")
    rnd["players"][user_id] = display_name
    count = len(rnd["players"])

    await query.answer(f"Ты в игре! (всего {count})")

    # Update message
    player_list = "\n".join(f"• {name}" for name in rnd["players"].values())
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(f"🔫 Войти ({format_diamonds(bet)})", callback_data=f"rr:join:{chat_id}"),
            ],
            [
                InlineKeyboardButton("🎯 КРУТИТЬ!", callback_data=f"rr:spin:{chat_id}:{rnd['host_id']}"),
            ],
        ]
    )

    try:
        await query.edit_message_text(
            f"🔫 <b>Русская рулетка</b>\n\n"
            f"💰 Ставка: {format_diamonds(bet)} с каждого\n\n"
            f"👥 Игроки ({count}/{RR_MAX_PLAYERS}):\n"
            f"{player_list}\n\n"
            f"💰 Банк: {format_diamonds(bet * count)}\n\n"
            f"<i>Организатор нажимает «КРУТИТЬ!» когда все готовы</i>",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except BadRequest:
        pass

    logger.info("RR player joined", user_id=user_id, chat_id=chat_id, count=count)


async def rr_spin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle spin button — execute the roulette."""
    query = update.callback_query
    if not query or not update.effective_user:
        return

    user_id = update.effective_user.id
    parts = query.data.split(":")
    chat_id = int(parts[2])
    host_id = int(parts[3])

    if user_id != host_id:
        await query.answer("❌ Только организатор может крутить", show_alert=True)
        return

    # Ban check
    with get_db() as db:
        host = db.query(User).filter(User.telegram_id == user_id).first()
        if not host or host.is_banned:
            await query.answer("Доступ запрещён", show_alert=True)
            return

    if chat_id not in active_rounds:
        await query.answer("❌ Раунд уже завершён", show_alert=True)
        return

    try:
        rnd = active_rounds.pop(chat_id)
        players = rnd["players"]
        bet = rnd["bet"]
        count = len(players)

        await query.answer()

        if count < RR_MIN_PLAYERS:
            # Refund all
            _refund_all(rnd)
            try:
                await query.edit_message_text(
                    f"❌ <b>Раунд отменён</b>\n\n"
                    f"Недостаточно игроков: {count}/{RR_MIN_PLAYERS}\n"
                    f"Ставки возвращены",
                    parse_mode="HTML",
                )
            except BadRequest:
                pass
            return

        # Animate the barrel spinning
        player_ids = list(players.keys())

        # Animation frames
        frames = [
            "🔫 Крутим барабан...\n\n🔄 |  |  |  |  |  |",
            "🔫 Барабан крутится...\n\n|  🔄  |  |  |  |",
            "🔫 Замедляется...\n\n|  |  🔄  |  |  |",
            "🔫 Почти...\n\n|  |  |  🔄  |  |",
            "🔫 ...\n\n|  |  |  |  🔄  |",
        ]

        try:
            for frame in frames:
                await query.edit_message_text(frame)
                await asyncio.sleep(0.8)
        except BadRequest:
            pass

        # Pick the loser
        loser_id = random.choice(player_ids)
        loser_name = players[loser_id]

        # Calculate payouts
        total_pot = bet * count
        house_fee = max(1, int(total_pot * RR_HOUSE_FEE_PERCENT / 100))
        distributable = total_pot - house_fee
        winners = [pid for pid in player_ids if pid != loser_id]
        per_winner = distributable // len(winners) if winners else 0
        remainder = distributable - (per_winner * len(winners)) if winners else 0

        # Pay winners (remainder goes to a random winner so no diamonds vanish)
        with get_db() as db:
            bonus_winner = random.choice(winners) if winners and remainder > 0 else None
            for winner_id in winners:
                payout = per_winner + (remainder if winner_id == bonus_winner else 0)
                winner_user = db.query(User).filter(User.telegram_id == winner_id).first()
                if winner_user:
                    winner_user.balance += payout

            # Record casino games
            for pid in player_ids:
                if pid == loser_id:
                    db.add(CasinoGame(user_id=pid, bet_amount=bet, result="loss", payout=0))
                else:
                    db.add(CasinoGame(user_id=pid, bet_amount=bet, result="win", payout=per_winner))

        # Build result
        profit = per_winner - bet
        winner_list = "\n".join(f"  ✅ {players[wid]} (+{format_diamonds(profit)})" for wid in winners)

        result_text = (
            f"🔫💥 <b>ВЫСТРЕЛ!</b>\n\n"
            f"💀 {loser_name} — убит! (-{format_diamonds(bet)})\n\n"
            f"Выжившие:\n{winner_list}\n\n"
            f"💰 Банк: {format_diamonds(total_pot)}\n"
            f"💸 Комиссия: {format_diamonds(house_fee)}\n"
            f"👤 Каждому: {format_diamonds(per_winner)}"
        )

        try:
            await query.edit_message_text(result_text, parse_mode="HTML")
        except BadRequest:
            pass

        # Track quest progress for winners
        for winner_id in winners:
            try:
                update_quest_progress(winner_id, "casino")
            except Exception:
                pass

        logger.info(
            "RR completed",
            chat_id=chat_id,
            players=count,
            loser=loser_id,
            pot=total_pot,
            per_winner=per_winner,
        )
    except Exception as e:
        _refund_all(rnd)
        logger.error("Roulette processing failed, refunded", error=str(e), exc_info=True)
        try:
            await query.edit_message_text("❌ Ошибка, ставки возвращены")
        except Exception:
            pass


def _refund_all(rnd: dict):
    """Refund all players in a round."""
    bet = rnd["bet"]
    with get_db() as db:
        for pid in rnd["players"]:
            user = db.query(User).filter(User.telegram_id == pid).first()
            if user:
                user.balance += bet


def register_roulette_handlers(application):
    """Register Russian roulette handlers."""
    application.add_handler(CommandHandler("rr", rr_command))
    application.add_handler(CallbackQueryHandler(rr_join_callback, pattern=r"^rr:join:"))
    application.add_handler(CallbackQueryHandler(rr_spin_callback, pattern=r"^rr:spin:"))
    logger.info("Russian roulette handlers registered")
