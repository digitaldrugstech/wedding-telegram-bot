"""Casino service - gambling with Telegram Dice API."""

import os
from datetime import datetime, timedelta
from typing import Tuple

import structlog
from sqlalchemy.orm import Session

from app.database.models import CasinoGame, User
from app.utils.formatters import format_diamonds

logger = structlog.get_logger()

# Check if DEBUG mode (DEV environment)
IS_DEBUG = os.environ.get("LOG_LEVEL", "INFO").upper() == "DEBUG"

# Constants
MIN_BET = 10
MAX_BET = 1000
CASINO_COOLDOWN_SECONDS = 60  # 1 minute

# Game types
SLOT_MACHINE = "slots"
DICE = "dice"
DARTS = "darts"
BASKETBALL = "basketball"
BOWLING = "bowling"
FOOTBALL = "football"

# Payout multipliers based on dice value
PAYOUT_MULTIPLIERS = {
    SLOT_MACHINE: {
        # Slot machine (1-64, jackpot at 64,43,22,1)
        64: 50,  # Jackpot (777) x50
        43: 10,  # Three same x10
        22: 5,  # Two same x5
        1: 2,  # Bar x2
        # All others: 0x (loss)
    },
    DICE: {
        # Dice (1-6)
        6: 5,  # Six x5
        5: 3,  # Five x3
        4: 1.5,  # Four x1.5
        # 1-3: 0x (loss)
    },
    DARTS: {
        # Darts (1-6, bullseye at 6)
        6: 10,  # Bullseye x10
        5: 5,  # Near bullseye x5
        4: 2,  # Good shot x2
        # 1-3: 0x (loss)
    },
    BASKETBALL: {
        # Basketball (1-5, score at 4-5)
        5: 4,  # Perfect shot x4
        4: 2,  # Good shot x2
        # 1-3: 0x (loss)
    },
    BOWLING: {
        # Bowling (1-6, strike at 6)
        6: 6,  # Strike x6
        5: 3,  # Spare x3
        4: 1.5,  # Half x1.5
        # 1-3: 0x (loss)
    },
    FOOTBALL: {
        # Football (1-5, goal at 3-5)
        5: 5,  # Perfect goal x5
        4: 3,  # Good goal x3
        3: 1.5,  # Goal x1.5
        # 1-2: 0x (loss)
    },
}


class CasinoService:
    """Service for casino games."""

    @staticmethod
    def can_bet(db: Session, user_id: int, bet_amount: int) -> Tuple[bool, str]:
        """Check if user can place a bet."""
        # Validate bet amount
        if bet_amount < MIN_BET:
            return False, f"Минимальная ставка: {format_diamonds(MIN_BET)}"

        if bet_amount > MAX_BET:
            return False, f"Максимальная ставка: {format_diamonds(MAX_BET)}"

        # Check balance
        user = db.query(User).filter(User.telegram_id == user_id).first()

        if user.balance < bet_amount:
            return False, f"Недостаточно алмазов (баланс: {format_diamonds(user.balance)})"

        # Check cooldown (skip in DEBUG mode)
        if not IS_DEBUG:
            last_game = (
                db.query(CasinoGame).filter(CasinoGame.user_id == user_id).order_by(CasinoGame.played_at.desc()).first()
            )

            if last_game:
                time_since_last = datetime.utcnow() - last_game.played_at
                if time_since_last.total_seconds() < CASINO_COOLDOWN_SECONDS:
                    remaining = CASINO_COOLDOWN_SECONDS - int(time_since_last.total_seconds())
                    return False, f"⏰ Подожди: {remaining} сек"

        return True, ""

    @staticmethod
    def play_game(
        db: Session, user_id: int, game_type: str, bet_amount: int, dice_value: int
    ) -> Tuple[bool, str, int, int]:
        """Process casino game result."""
        user = db.query(User).filter(User.telegram_id == user_id).first()

        # Calculate payout
        multipliers = PAYOUT_MULTIPLIERS.get(game_type, {})
        multiplier = multipliers.get(dice_value, 0)
        winnings = int(bet_amount * multiplier) if multiplier > 0 else 0

        # Deduct bet from balance
        user.balance -= bet_amount

        # Add winnings
        if winnings > 0:
            user.balance += winnings
            result = "win"
            payout = winnings
        else:
            result = "loss"
            payout = 0

        # Save game record
        game = CasinoGame(user_id=user_id, bet_amount=bet_amount, result=result, payout=payout)

        db.add(game)
        db.commit()

        logger.info(
            "Casino game played",
            user_id=user_id,
            game_type=game_type,
            bet=bet_amount,
            dice_value=dice_value,
            result=result,
            payout=payout,
        )

        # Build result message
        game_names = {
            SLOT_MACHINE: "Слот-машина",
            DICE: "Кости",
            DARTS: "Дартс",
            BASKETBALL: "Баскетбол",
            BOWLING: "Боулинг",
            FOOTBALL: "Футбол",
        }
        game_name = game_names.get(game_type, "Казино")

        if winnings > 0:
            profit = winnings - bet_amount
            message = (
                f"🎉 <b>Выигрыш!</b>\n\n"
                f"🎮 {game_name}\n"
                f"🎲 Результат: {dice_value}\n"
                f"💰 Ставка: {format_diamonds(bet_amount)}\n"
                f"🏆 Выплата: {format_diamonds(winnings)} (x{multiplier})\n"
                f"💎 Профит: +{format_diamonds(profit)}\n\n"
                f"💰 Баланс: {format_diamonds(user.balance)}"
            )
        else:
            message = (
                f"😔 <b>Проигрыш</b>\n\n"
                f"🎮 {game_name}\n"
                f"🎲 Результат: {dice_value}\n"
                f"💰 Ставка: {format_diamonds(bet_amount)}\n"
                f"💎 Потеря: -{format_diamonds(bet_amount)}\n\n"
                f"💰 Баланс: {format_diamonds(user.balance)}"
            )

        # Add DEBUG mode note
        if IS_DEBUG:
            message += "\n\n🔧 <i>Кулдаун убран (DEV)</i>"

        return True, message, winnings, user.balance

    @staticmethod
    def get_user_stats(db: Session, user_id: int) -> dict:
        """Get user's casino statistics."""
        games = db.query(CasinoGame).filter(CasinoGame.user_id == user_id).all()

        if not games:
            return {
                "total_games": 0,
                "total_bet": 0,
                "total_winnings": 0,
                "total_profit": 0,
                "win_rate": 0,
            }

        total_games = len(games)
        total_bet = sum(game.bet_amount for game in games)
        total_winnings = sum(game.payout for game in games)
        total_profit = total_winnings - total_bet
        wins = sum(1 for game in games if game.result == "win")
        win_rate = (wins / total_games * 100) if total_games > 0 else 0

        return {
            "total_games": total_games,
            "total_bet": total_bet,
            "total_winnings": total_winnings,
            "total_profit": total_profit,
            "win_rate": win_rate,
        }
