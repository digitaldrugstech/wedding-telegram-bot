"""Casino service - gambling with Telegram Dice API."""

import os
from datetime import datetime
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
VIP_MAX_BET = 2000  # Premium users get higher limit
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
        # Slot machine (1-64, jackpot at 64,43,22,1 + bonus 16,32,48)
        # EV: 30/64 + 5/64 + 3/64 + 2/64 + 2/64 + 1.5/64 + 1.5/64 = 0.703 (30% house edge)
        64: 30,  # Jackpot (777) x30
        43: 5,  # Three same x5
        22: 3,  # Two same x3
        1: 2,  # Bar x2
        16: 2,  # Small win x2
        32: 1.5,  # Small win x1.5
        48: 1.5,  # Small win x1.5
        # All others: 0x (loss)
    },
    DICE: {
        # Dice (1-6, each 1/6)
        # EV: 3/6 + 2/6 = 0.833 (17% house edge)
        6: 3,  # Six x3
        5: 2,  # Five x2
        # 1-4: 0x (loss)
    },
    DARTS: {
        # Darts (1-6, each 1/6)
        # EV: 5/6 = 0.833 (17% house edge)
        6: 5,  # Bullseye x5
        # 1-5: 0x (loss)
    },
    BASKETBALL: {
        # Basketball (1-5, each 1/5)
        # EV: 3/5 + 1.5/5 = 0.900 (10% house edge)
        5: 3,  # Perfect shot x3
        4: 1.5,  # Good shot x1.5
        # 1-3: 0x (loss)
    },
    BOWLING: {
        # Bowling (1-6, each 1/6)
        # EV: 4/6 + 1.5/6 = 0.917 (8% house edge)
        6: 4,  # Strike x4
        5: 1.5,  # Spare x1.5
        # 1-4: 0x (loss)
    },
    FOOTBALL: {
        # Football (1-5, each 1/5)
        # EV: 3/5 + 1.5/5 = 0.900 (10% house edge)
        5: 3,  # Perfect goal x3
        4: 1.5,  # Good goal x1.5
        # 1-3: 0x (loss)
    },
}


class CasinoService:
    """Service for casino games."""

    @staticmethod
    def reserve_bet(db: Session, user_id: int, bet_amount: int) -> Tuple[bool, str]:
        """Validate and immediately deduct bet (prevents TOCTOU race condition)."""
        # Validate bet amount
        if bet_amount < MIN_BET:
            return False, f"Минимальная ставка: {format_diamonds(MIN_BET)}"

        # VIP players get higher max bet (2000 instead of 1000)
        from app.handlers.premium import is_vip

        effective_max = VIP_MAX_BET if is_vip(user_id, db=db) else MAX_BET
        if bet_amount > effective_max:
            return False, f"Максимальная ставка: {format_diamonds(effective_max)}"

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

        # Deduct bet immediately (atomic with check)
        user.balance -= bet_amount

        return True, ""

    @staticmethod
    def play_game(
        db: Session, user_id: int, game_type: str, bet_amount: int, dice_value: int
    ) -> Tuple[bool, str, int, int]:
        """Process casino game result (bet already deducted by reserve_bet)."""
        user = db.query(User).filter(User.telegram_id == user_id).first()

        # Import premium helpers (must be at top of method to avoid NameError on loss path)
        from app.handlers.premium import build_premium_nudge, has_active_boost

        # Calculate payout
        multipliers = PAYOUT_MULTIPLIERS.get(game_type, {})
        multiplier = multipliers.get(dice_value, 0)
        winnings = int(bet_amount * multiplier) if multiplier > 0 else 0

        # Lucky charm bonus (+10%)
        lucky_bonus = 0
        if winnings > 0:
            if has_active_boost(user_id, "lucky_charm", db=db):
                lucky_bonus = int(winnings * 0.10)
                winnings += lucky_bonus

        # Add winnings (bet already deducted)
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
            lucky_text = f"\n🍀 Талисман удачи: +{format_diamonds(lucky_bonus)}" if lucky_bonus > 0 else ""
            message = (
                f"🎉 <b>Выигрыш!</b>\n\n"
                f"🎮 {game_name}\n"
                f"🎲 Результат: {dice_value}\n"
                f"💰 Ставка: {format_diamonds(bet_amount)}\n"
                f"🏆 Выплата: {format_diamonds(winnings)} (x{multiplier})\n"
                f"💎 Профит: +{format_diamonds(profit)}{lucky_text}\n\n"
                f"💰 Баланс: {format_diamonds(user.balance)}"
            )
        else:
            # Add lucky charm nudge on loss (throttled: max once per 30 min)
            nudge = ""
            if not has_active_boost(user_id, "lucky_charm", db=db):
                nudge = build_premium_nudge("casino_loss", user_id)
            message = (
                f"😔 <b>Проигрыш</b>\n\n"
                f"🎮 {game_name}\n"
                f"🎲 Результат: {dice_value}\n"
                f"💰 Ставка: {format_diamonds(bet_amount)}\n"
                f"💎 Потеря: -{format_diamonds(bet_amount)}\n\n"
                f"💰 Баланс: {format_diamonds(user.balance)}{nudge}"
            )

        # Add DEBUG mode note
        if IS_DEBUG:
            message += "\n\n🔧 <i>Кулдаун убран (тест)</i>"

        # Award loyalty point for playing casino
        try:
            from app.handlers.premium import add_loyalty_points

            add_loyalty_points(user_id, 1, db=db)
        except Exception:
            pass

        return True, message, winnings, user.balance

    @staticmethod
    def get_user_stats(db: Session, user_id: int) -> dict:
        """Get user's casino statistics (DB-level aggregation)."""
        from sqlalchemy import case, func

        row = (
            db.query(
                func.count(CasinoGame.id).label("total_games"),
                func.coalesce(func.sum(CasinoGame.bet_amount), 0).label("total_bet"),
                func.coalesce(func.sum(CasinoGame.payout), 0).label("total_winnings"),
                func.sum(case((CasinoGame.result == "win", 1), else_=0)).label("wins"),
            )
            .filter(CasinoGame.user_id == user_id)
            .first()
        )

        total_games = row.total_games or 0
        if total_games == 0:
            return {
                "total_games": 0,
                "total_bet": 0,
                "total_winnings": 0,
                "total_profit": 0,
                "win_rate": 0,
            }

        total_bet = row.total_bet
        total_winnings = row.total_winnings
        wins = row.wins or 0

        return {
            "total_games": total_games,
            "total_bet": total_bet,
            "total_winnings": total_winnings,
            "total_profit": total_winnings - total_bet,
            "win_rate": (wins / total_games * 100) if total_games > 0 else 0,
        }
