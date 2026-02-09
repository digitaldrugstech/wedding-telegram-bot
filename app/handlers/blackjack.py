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

logger = structlog.get_logger()

BLACKJACK_COOLDOWN_SECONDS = 60
BLACKJACK_MIN_BET = 10
BLACKJACK_MAX_BET = 1000

SUITS = ["\u2660\ufe0f", "\u2665\ufe0f", "\u2666\ufe0f", "\u2663\ufe0f"]
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
                InlineKeyboardButton("\U0001f0cf \u0415\u0449\u0451", callback_data=f"bj:hit:{user_id}"),
                InlineKeyboardButton(
                    "\u270b \u0425\u0432\u0430\u0442\u0438\u0442", callback_data=f"bj:stand:{user_id}"
                ),
            ]
        ]
    )


def build_game_text(player_cards, dealer_cards, bet, hide_dealer=True):
    """Build game state display."""
    player_val = hand_value(player_cards)
    if hide_dealer:
        dealer_display = f"{fmt_card(dealer_cards[0])} \U0001f0a0"
        dealer_val = "?"
    else:
        dealer_display = fmt_hand(dealer_cards)
        dealer_val = str(hand_value(dealer_cards))
    return (
        f"\U0001f0cf <b>\u0411\u043b\u044d\u043a\u0434\u0436\u0435\u043a</b>\n\n"
        f"\u0421\u0442\u0430\u0432\u043a\u0430: {format_diamonds(bet)}\n\n"
        f"\u0422\u044b: {fmt_hand(player_cards)} = <b>{player_val}</b>\n"
        f"\u0414\u0438\u043b\u0435\u0440: {dealer_display} = <b>{dealer_val}</b>"
    )


def _finish_game(user_id, bet, payout, result_type):
    """Record game result and set cooldown."""
    with get_db() as db:
        if payout > 0:
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
        await update.message.reply_text(
            "\u274c \u0423 \u0442\u0435\u0431\u044f \u0443\u0436\u0435 \u0438\u0434\u0451\u0442 \u0438\u0433\u0440\u0430. \u0414\u043e\u0438\u0433\u0440\u0430\u0439 \u0435\u0451"
        )
        return

    if not context.args:
        await update.message.reply_text(
            "\U0001f0cf <b>\u0411\u043b\u044d\u043a\u0434\u0436\u0435\u043a</b>\n\n"
            f"/blackjack [\u0441\u0442\u0430\u0432\u043a\u0430] \u2014 \u0438\u0433\u0440\u0430\u0442\u044c\n"
            f"/bj [\u0441\u0442\u0430\u0432\u043a\u0430] \u2014 \u043a\u043e\u0440\u043e\u0442\u043a\u043e\n\n"
            f"\u041b\u0438\u043c\u0438\u0442\u044b: {format_diamonds(BLACKJACK_MIN_BET)} - {format_diamonds(BLACKJACK_MAX_BET)}\n\n"
            "\U0001f0cf \u0411\u043b\u044d\u043a\u0434\u0436\u0435\u043a (21): x2.5\n"
            "\U0001f3c6 \u041f\u043e\u0431\u0435\u0434\u0430: x2\n"
            "\U0001f91d \u041d\u0438\u0447\u044c\u044f: \u0432\u043e\u0437\u0432\u0440\u0430\u0442",
            parse_mode="HTML",
        )
        return

    try:
        bet = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "\u274c \u0421\u0442\u0430\u0432\u043a\u0430 \u0434\u043e\u043b\u0436\u043d\u0430 \u0431\u044b\u0442\u044c \u0447\u0438\u0441\u043b\u043e\u043c"
        )
        return

    if bet < BLACKJACK_MIN_BET or bet > BLACKJACK_MAX_BET:
        await update.message.reply_text(
            f"\u274c \u0421\u0442\u0430\u0432\u043a\u0430: {format_diamonds(BLACKJACK_MIN_BET)} - {format_diamonds(BLACKJACK_MAX_BET)}"
        )
        return

    # Check balance and cooldown, deduct bet
    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == user_id).first()

        if user.balance < bet:
            await update.message.reply_text(
                f"\u274c \u041d\u0435\u0434\u043e\u0441\u0442\u0430\u0442\u043e\u0447\u043d\u043e \u0430\u043b\u043c\u0430\u0437\u043e\u0432\n\n"
                f"\u041d\u0443\u0436\u043d\u043e: {format_diamonds(bet)}\n"
                f"\u0423 \u0442\u0435\u0431\u044f: {format_diamonds(user.balance)}"
            )
            return

        cooldown = db.query(Cooldown).filter(Cooldown.user_id == user_id, Cooldown.action == "blackjack").first()

        if cooldown and cooldown.expires_at > datetime.utcnow():
            remaining = cooldown.expires_at - datetime.utcnow()
            seconds_left = int(remaining.total_seconds())
            await update.message.reply_text(
                f"\u23f0 \u0421\u043b\u0435\u0434\u0443\u044e\u0449\u0430\u044f \u0438\u0433\u0440\u0430 \u0447\u0435\u0440\u0435\u0437 {seconds_left}\u0441"
            )
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
            f"\U0001f0cf <b>\u041d\u0438\u0447\u044c\u044f!</b>\n\n"
            f"\u0421\u0442\u0430\u0432\u043a\u0430: {format_diamonds(bet)}\n\n"
            f"\u0422\u044b: {fmt_hand(player_cards)} = <b>21</b>\n"
            f"\u0414\u0438\u043b\u0435\u0440: {fmt_hand(dealer_cards)} = <b>21</b>\n\n"
            f"\U0001f91d \u041e\u0431\u0430 \u0431\u043b\u044d\u043a\u0434\u0436\u0435\u043a! \u0412\u043e\u0437\u0432\u0440\u0430\u0442: {format_diamonds(bet)}"
        )
        await update.message.reply_text(text, parse_mode="HTML")
        logger.info("Blackjack push", user_id=user_id, bet=bet)
        return

    if player_bj:
        # Player natural blackjack
        context.user_data["bj_active"] = False
        payout = int(bet * 2.5)
        _finish_game(user_id, bet, payout, "win")
        text = (
            f"\U0001f0cf <b>\u0411\u041b\u042d\u041a\u0414\u0416\u0415\u041a!</b> \U0001f389\n\n"
            f"\u0421\u0442\u0430\u0432\u043a\u0430: {format_diamonds(bet)}\n\n"
            f"\u0422\u044b: {fmt_hand(player_cards)} = <b>21</b>\n"
            f"\u0414\u0438\u043b\u0435\u0440: {fmt_hand(dealer_cards)} = <b>{hand_value(dealer_cards)}</b>\n\n"
            f"\U0001f4b0 \u0412\u044b\u0438\u0433\u0440\u044b\u0448: {format_diamonds(payout)} (x2.5)"
        )
        await update.message.reply_text(text, parse_mode="HTML")
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
            "\u26a0\ufe0f \u042d\u0442\u0430 \u043a\u043d\u043e\u043f\u043a\u0430 \u043d\u0435 \u0434\u043b\u044f \u0442\u0435\u0431\u044f",
            show_alert=True,
        )
        return

    await query.answer()

    if not context.user_data.get("bj_active"):
        try:
            await query.edit_message_text(
                "\u274c \u0418\u0433\u0440\u0430 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430. \u041d\u0430\u0447\u043d\u0438 \u043d\u043e\u0432\u0443\u044e: /blackjack"
            )
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
            text = (
                f"\U0001f0cf <b>\u041f\u0435\u0440\u0435\u0431\u043e\u0440!</b>\n\n"
                f"\u0421\u0442\u0430\u0432\u043a\u0430: {format_diamonds(bet)}\n\n"
                f"\u0422\u044b: {fmt_hand(player_cards)} = <b>{player_val}</b>\n"
                f"\u0414\u0438\u043b\u0435\u0440: {fmt_hand(dealer_cards)} = <b>{hand_value(dealer_cards)}</b>\n\n"
                f"\U0001f4b8 \u041f\u043e\u0442\u0435\u0440\u044f\u043d\u043e: {format_diamonds(bet)}"
            )
            try:
                await query.edit_message_text(text, parse_mode="HTML")
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
            result_line = f"\U0001f3c6 \u0414\u0438\u043b\u0435\u0440 \u043f\u0435\u0440\u0435\u0431\u0440\u0430\u043b! \u0412\u044b\u0438\u0433\u0440\u044b\u0448: {format_diamonds(payout)}"
            result_type = "win"
        elif player_val > dealer_val:
            payout = bet * 2
            result_line = f"\U0001f3c6 \u041f\u043e\u0431\u0435\u0434\u0430! \u0412\u044b\u0438\u0433\u0440\u044b\u0448: {format_diamonds(payout)}"
            result_type = "win"
        elif player_val == dealer_val:
            payout = bet
            result_line = f"\U0001f91d \u041d\u0438\u0447\u044c\u044f! \u0412\u043e\u0437\u0432\u0440\u0430\u0442: {format_diamonds(bet)}"
            result_type = "win"
        else:
            payout = 0
            result_line = f"\U0001f4b8 \u041f\u0440\u043e\u0438\u0433\u0440\u044b\u0448: {format_diamonds(bet)}"
            result_type = "loss"

        _finish_game(user_id, bet, payout, result_type)

        text = (
            f"\U0001f0cf <b>\u0411\u043b\u044d\u043a\u0434\u0436\u0435\u043a</b>\n\n"
            f"\u0421\u0442\u0430\u0432\u043a\u0430: {format_diamonds(bet)}\n\n"
            f"\u0422\u044b: {fmt_hand(player_cards)} = <b>{player_val}</b>\n"
            f"\u0414\u0438\u043b\u0435\u0440: {fmt_hand(dealer_cards)} = <b>{dealer_val}</b>\n\n"
            f"{result_line}"
        )

        try:
            await query.edit_message_text(text, parse_mode="HTML")
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


def register_blackjack_handlers(application):
    """Register blackjack handlers."""
    application.add_handler(CommandHandler(["blackjack", "bj"], blackjack_command))
    application.add_handler(CallbackQueryHandler(blackjack_callback, pattern=r"^bj:"))
    logger.info("Blackjack handlers registered")
