"""Blackjack command handlers."""

import random
from datetime import datetime, timedelta

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.database.connection import get_db
from app.database.models import CasinoGame, Cooldown, User
from app.handlers.quest import update_quest_progress
from app.utils.decorators import require_registered
from app.utils.formatters import format_diamonds
from app.utils.keyboards import casino_after_game_keyboard

logger = structlog.get_logger()

BLACKJACK_COOLDOWN_SECONDS = 60
BLACKJACK_MIN_BET = 10
BLACKJACK_MAX_BET = 1000

SUITS = ["♠️", "♥️", "♦️", "♣️"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
CARD_VALUES = {
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "10": 10,
    "J": 10,
    "Q": 10,
    "K": 10,
    "A": 11,
}


def create_deck():
    """Create and shuffle a 52-card deck."""
    deck = [(rank, suit) for suit in SUITS for rank in RANKS]
    random.shuffle(deck)
    return deck


def fmt_card(card):
    """Format card as string."""
    return f"{card[1]}{card[0]}"


def fmt_hand(cards):
    """Format hand as string."""
    return " ".join(fmt_card(c) for c in cards)


def hand_value(cards):
    """Calculate hand value with ace handling."""
    value = sum(CARD_VALUES[c[0]] for c in cards)
    aces = sum(1 for c in cards if c[0] == "A")
    while value > 21 and aces > 0:
        value -= 10
        aces -= 1
    return value


def is_blackjack(cards):
    """Check for natural blackjack (2 cards = 21)."""
    return len(cards) == 2 and hand_value(cards) == 21


def get_bj_keyboard(user_id):
    """Hit/Stand buttons."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🃏 Ещё", callback_data=f"bj:hit:{user_id}"),
                InlineKeyboardButton("✋ Хватит", callback_data=f"bj:stand:{user_id}"),
            ]
        ]
    )


def build_game_text(player_cards, dealer_cards, bet, hide_dealer=True):
    """Build game state display."""
    player_val = hand_value(player_cards)
    if hide_dealer:
        dealer_display = f"{fmt_card(dealer_cards[0])} 🂠"
        dealer_val = "?"
    else:
        dealer_display = fmt_hand(dealer_cards)
        dealer_val = str(hand_value(dealer_cards))
    return (
        f"🃏 <b>Блэкджек</b>\n\n"
        f"Ставка: {format_diamonds(bet)}\n\n"
        f"Ты: {fmt_hand(player_cards)} = <b>{player_val}</b>\n"
        f"Дилер: {dealer_display} = <b>{dealer_val}</b>"
    )


def _finish_game(user_id, bet, payout, result_type):
    """Record game result and set cooldown."""
    with get_db() as db:
        if payout > 0:
            # Lucky charm bonus (+5%)
            from app.handlers.premium import has_active_boost

            if has_active_boost(user_id, "lucky_charm", db=db):
                payout += int(payout * 0.05)

            user = db.query(User).filter(User.telegram_id == user_id).first()
            user.balance += payout

        cooldown = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "blackjack").first()
        expires_at = datetime.utcnow() + timedelta(seconds=BLACKJACK_COOLDOWN_SECONDS)
        if cooldown:
            cooldown.expires_at = expires_at
        else:
            db.add(Cooldown(user_id=user_id, action="blackjack", expires_at=expires_at))

        db.add(CasinoGame(user_id=user_id, bet_amount=bet, result=result_type, payout=payout))

    try:
        update_quest_progress(user_id, "casino")
    except Exception:
        pass


@require_registered
async def blackjack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start blackjack game (/blackjack [bet])."""
    user_id = update.effective_user.id

    if context.user_data.get("bj_active"):
        await update.message.reply_text("❌ У тебя уже идёт игра. Доиграй её")
        return

    if not context.args:
        await update.message.reply_text(
            "🃏 <b>Блэкджек</b>\n\n"
            f"/blackjack [ставка] — играть\n"
            f"/bj [ставка] — коротко\n\n"
            f"Лимиты: {format_diamonds(BLACKJACK_MIN_BET)} - {format_diamonds(BLACKJACK_MAX_BET)}\n\n"
            "🃏 Блэкджек (21): x2.5\n"
            "🏆 Победа: x2\n"
            "🤝 Ничья: возврат",
            parse_mode="HTML",
        )
        return

    try:
        bet = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Ставка должна быть числом")
        return

    if bet < BLACKJACK_MIN_BET or bet > BLACKJACK_MAX_BET:
        await update.message.reply_text(
            f"❌ Ставка: {format_diamonds(BLACKJACK_MIN_BET)} - {format_diamonds(BLACKJACK_MAX_BET)}"
        )
        return

    # Check balance and cooldown, deduct bet
    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()

        if user.balance < bet:
            await update.message.reply_text(
                f"❌ Недостаточно алмазов\n\n"
                f"Нужно: {format_diamonds(bet)}\n"
                f"У тебя: {format_diamonds(user.balance)}"
            )
            return

        cooldown = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "blackjack").first()

        if cooldown and cooldown.expires_at > datetime.utcnow():
            remaining = cooldown.expires_at - datetime.utcnow()
            seconds_left = int(remaining.total_seconds())
            await update.message.reply_text(f"⏰ Следующая игра через {seconds_left}с")
            return

        user.balance -= bet

    # Deal cards
    deck = create_deck()
    player_cards = [deck.pop(), deck.pop()]
    dealer_cards = [deck.pop(), deck.pop()]

    # Store game state
    context.user_data["bj_active"] = True
    context.user_data["bj_deck"] = deck
    context.user_data["bj_player"] = player_cards
    context.user_data["bj_dealer"] = dealer_cards
    context.user_data["bj_bet"] = bet

    # Check for natural blackjack
    player_bj = is_blackjack(player_cards)
    dealer_bj = is_blackjack(dealer_cards)

    if player_bj and dealer_bj:
        # Push — both have blackjack
        context.user_data["bj_active"] = False
        _finish_game(user_id, bet, bet, "win")
        text = (
            f"🃏 <b>Ничья!</b>\n\n"
            f"Ставка: {format_diamonds(bet)}\n\n"
            f"Ты: {fmt_hand(player_cards)} = <b>21</b>\n"
            f"Дилер: {fmt_hand(dealer_cards)} = <b>21</b>\n\n"
            f"🤝 Оба блэкджек! Возврат: {format_diamonds(bet)}"
        )
        await update.message.reply_text(
            text, parse_mode="HTML", reply_markup=casino_after_game_keyboard("blackjack", user_id, bet=bet)
        )
        logger.info("Blackjack push", user_id=user_id, bet=bet)
        return

    if player_bj:
        # Player natural blackjack
        context.user_data["bj_active"] = False
        payout = int(bet * 2.5)
        _finish_game(user_id, bet, payout, "win")
        text = (
            f"🃏 <b>БЛЭКДЖЕК!</b> 🎉\n\n"
            f"Ставка: {format_diamonds(bet)}\n\n"
            f"Ты: {fmt_hand(player_cards)} = <b>21</b>\n"
            f"Дилер: {fmt_hand(dealer_cards)} = <b>{hand_value(dealer_cards)}</b>\n\n"
            f"💰 Выигрыш: {format_diamonds(payout)} (x2.5)"
        )
        await update.message.reply_text(
            text, parse_mode="HTML", reply_markup=casino_after_game_keyboard("blackjack", user_id, bet=bet)
        )
        logger.info("Blackjack natural", user_id=user_id, bet=bet, payout=payout)
        return

    # Normal game — show hand with buttons
    text = build_game_text(player_cards, dealer_cards, bet)
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=get_bj_keyboard(user_id))


async def blackjack_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Hit/Stand buttons."""
    query = update.callback_query
    if not query or not update.effective_user:
        return

    parts = query.data.split(":")
    if len(parts) != 3:
        return

    action = parts[1]
    owner_id = int(parts[2])
    user_id = update.effective_user.id

    if user_id != owner_id:
        await query.answer(
            "⚠️ Эта кнопка не для тебя",
            show_alert=True,
        )
        return

    # Ban check
    with get_db() as db:
        bj_user = db.query(User).filter(User.telegram_id == user_id).first()
        if not bj_user or bj_user.is_banned:
            context.user_data["bj_active"] = False
            await query.answer("Доступ запрещён", show_alert=True)
            return

    await query.answer()

    if not context.user_data.get("bj_active"):
        try:
            await query.edit_message_text("❌ Игра не найдена. Начни новую: /blackjack")
        except Exception:
            pass
        return

    deck = context.user_data["bj_deck"]
    player_cards = context.user_data["bj_player"]
    dealer_cards = context.user_data["bj_dealer"]
    bet = context.user_data["bj_bet"]

    if action == "hit":
        player_cards.append(deck.pop())
        player_val = hand_value(player_cards)

        if player_val > 21:
            # Bust
            context.user_data["bj_active"] = False
            _finish_game(user_id, bet, 0, "loss")
            # Lucky charm nudge on loss (throttled)
            from app.handlers.premium import build_premium_nudge, has_active_boost as _bj_has_boost

            nudge = ""
            if not _bj_has_boost(user_id, "lucky_charm"):
                nudge = build_premium_nudge("casino_loss", user_id)
            text = (
                f"🃏 <b>Перебор!</b>\n\n"
                f"Ставка: {format_diamonds(bet)}\n\n"
                f"Ты: {fmt_hand(player_cards)} = <b>{player_val}</b>\n"
                f"Дилер: {fmt_hand(dealer_cards)} = <b>{hand_value(dealer_cards)}</b>\n\n"
                f"💸 Потеряно: {format_diamonds(bet)}{nudge}"
            )
            try:
                await query.edit_message_text(
                    text, parse_mode="HTML", reply_markup=casino_after_game_keyboard("blackjack", user_id, bet=bet)
                )
            except Exception:
                pass
            logger.info("Blackjack bust", user_id=user_id, bet=bet, player_value=player_val)
            return

        if player_val == 21:
            # Auto-stand on 21
            action = "stand"
        else:
            # Show updated hand
            text = build_game_text(player_cards, dealer_cards, bet)
            try:
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=get_bj_keyboard(user_id))
            except Exception:
                pass
            return

    if action == "stand":
        # Dealer plays
        while hand_value(dealer_cards) < 17:
            dealer_cards.append(deck.pop())

        player_val = hand_value(player_cards)
        dealer_val = hand_value(dealer_cards)
        context.user_data["bj_active"] = False

        if dealer_val > 21:
            payout = bet * 2
            result_line = f"🏆 Дилер перебрал! Выигрыш: {format_diamonds(payout)}"
            result_type = "win"
        elif player_val > dealer_val:
            payout = bet * 2
            result_line = f"🏆 Победа! Выигрыш: {format_diamonds(payout)}"
            result_type = "win"
        elif player_val == dealer_val:
            payout = bet
            result_line = f"🤝 Ничья! Возврат: {format_diamonds(bet)}"
            result_type = "win"
        else:
            payout = 0
            result_line = f"💸 Проигрыш: {format_diamonds(bet)}"
            result_type = "loss"

        _finish_game(user_id, bet, payout, result_type)

        # Lucky charm nudge on loss (throttled)
        loss_nudge = ""
        if result_type == "loss":
            from app.handlers.premium import build_premium_nudge, has_active_boost as _bj_stand_boost

            if not _bj_stand_boost(user_id, "lucky_charm"):
                loss_nudge = build_premium_nudge("casino_loss", user_id)

        text = (
            f"🃏 <b>Блэкджек</b>\n\n"
            f"Ставка: {format_diamonds(bet)}\n\n"
            f"Ты: {fmt_hand(player_cards)} = <b>{player_val}</b>\n"
            f"Дилер: {fmt_hand(dealer_cards)} = <b>{dealer_val}</b>\n\n"
            f"{result_line}{loss_nudge}"
        )

        try:
            await query.edit_message_text(
                text, parse_mode="HTML", reply_markup=casino_after_game_keyboard("blackjack", user_id, bet=bet)
            )
        except Exception:
            pass

        logger.info(
            "Blackjack result",
            user_id=user_id,
            bet=bet,
            player=player_val,
            dealer=dealer_val,
            payout=payout,
        )


async def blackjack_bet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle blackjack bet from button — cbet:blackjack:{amount}:{user_id}."""
    query = update.callback_query
    if not update.effective_user:
        return

    parts = query.data.split(":")
    if len(parts) != 4:
        return

    amount_str = parts[2]
    owner_id = int(parts[3])

    if update.effective_user.id != owner_id:
        await query.answer("Эта кнопка не для тебя", show_alert=True)
        return

    user_id = update.effective_user.id

    if context.user_data.get("bj_active"):
        await query.answer("У тебя уже идёт игра", show_alert=True)
        return

    # Parse bet
    if amount_str == "all":
        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == user_id).first()
            if not user:
                await query.answer("Доступ запрещён", show_alert=True)
                return
            bet = min(user.balance, BLACKJACK_MAX_BET)
            if bet < BLACKJACK_MIN_BET:
                await query.answer(f"Недостаточно алмазов (мин. {BLACKJACK_MIN_BET})", show_alert=True)
                return
    else:
        try:
            bet = int(amount_str)
        except ValueError:
            return

    if bet < BLACKJACK_MIN_BET or bet > BLACKJACK_MAX_BET:
        await query.answer(f"Ставка: {BLACKJACK_MIN_BET}-{BLACKJACK_MAX_BET}", show_alert=True)
        return

    # Check balance and cooldown, deduct bet
    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user or user.is_banned:
            await query.answer("Доступ запрещён", show_alert=True)
            return

        if user.balance < bet:
            await query.answer(f"Недостаточно алмазов ({format_diamonds(user.balance)})", show_alert=True)
            return

        cooldown = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "blackjack").first()
        if cooldown and cooldown.expires_at > datetime.utcnow():
            remaining = cooldown.expires_at - datetime.utcnow()
            await query.answer(f"Подожди {int(remaining.total_seconds())}с", show_alert=True)
            return

        user.balance -= bet

    await query.answer()

    # Deal cards
    deck = create_deck()
    player_cards = [deck.pop(), deck.pop()]
    dealer_cards = [deck.pop(), deck.pop()]

    # Store game state
    context.user_data["bj_active"] = True
    context.user_data["bj_deck"] = deck
    context.user_data["bj_player"] = player_cards
    context.user_data["bj_dealer"] = dealer_cards
    context.user_data["bj_bet"] = bet

    # Check for natural blackjack
    player_bj = is_blackjack(player_cards)
    dealer_bj = is_blackjack(dealer_cards)

    if player_bj and dealer_bj:
        context.user_data["bj_active"] = False
        _finish_game(user_id, bet, bet, "win")
        text = (
            f"🃏 <b>Ничья!</b>\n\n"
            f"Ставка: {format_diamonds(bet)}\n\n"
            f"Ты: {fmt_hand(player_cards)} = <b>21</b>\n"
            f"Дилер: {fmt_hand(dealer_cards)} = <b>21</b>\n\n"
            f"🤝 Оба блэкджек! Возврат: {format_diamonds(bet)}"
        )
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=casino_after_game_keyboard("blackjack", user_id, bet=bet),
        )
        return

    if player_bj:
        context.user_data["bj_active"] = False
        payout = int(bet * 2.5)
        _finish_game(user_id, bet, payout, "win")
        text = (
            f"🃏 <b>БЛЭКДЖЕК!</b> 🎉\n\n"
            f"Ставка: {format_diamonds(bet)}\n\n"
            f"Ты: {fmt_hand(player_cards)} = <b>21</b>\n"
            f"Дилер: {fmt_hand(dealer_cards)} = <b>{hand_value(dealer_cards)}</b>\n\n"
            f"💰 Выигрыш: {format_diamonds(payout)} (x2.5)"
        )
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=casino_after_game_keyboard("blackjack", user_id, bet=bet),
        )
        return

    # Normal game — show hand with buttons
    text = build_game_text(player_cards, dealer_cards, bet)
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=get_bj_keyboard(user_id),
    )


def register_blackjack_handlers(application):
    """Register blackjack handlers."""
    application.add_handler(CommandHandler(["blackjack", "bj"], blackjack_command))
    application.add_handler(CallbackQueryHandler(blackjack_callback, pattern=r"^bj:"))
    application.add_handler(CallbackQueryHandler(blackjack_bet_callback, pattern=r"^cbet:blackjack:"))
    logger.info("Blackjack handlers registered")
