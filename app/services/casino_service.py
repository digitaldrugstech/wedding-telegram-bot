"""Casino service for Wedding Telegram Bot."""

import random
from datetime import datetime
from typing import Optional, Tuple

import structlog
from sqlalchemy.orm import Session

from app.database.models import User
from app.utils.formatters import format_diamonds

logger = structlog.get_logger()

# Casino game types
DICE = "dice"  # 🎲 1-6
DARTS = "darts"  # 🎯 1-6
BASKETBALL = "basketball"  # 🏀 1-5
SLOT_MACHINE = "slot_machine"  # 🎰 1-64
BOWLING = "bowling"  # 🎳 1-6
FOOTBALL = "football"  # ⚽ 1-5

# Bet limits
MIN_BET = 10
MAX_BET = 1000

# Payout multipliers by game and result
PAYOUTS = {
    DICE: {
        6: 5.0,  # Jackpot - выпало 6
        5: 2.5,  # Хороший результат
        4: 1.5,  # Средний результат
        3: 0.0,  # Возврат ставки
        2: 0.0,  # Проигрыш
        1: 0.0,  # Проигрыш
    },
    DARTS: {
        6: 10.0,  # Bullseye - в яблочко
        5: 3.0,  # Очень близко
        4: 1.5,  # Близко
        3: 0.0,  # Возврат ставки
        2: 0.0,  # Мимо
        1: 0.0,  # Полный промах
    },
    BASKETBALL: {
        5: 4.0,  # Идеальный бросок
        4: 2.0,  # Хороший бросок
        3: 1.0,  # Попал в кольцо
        2: 0.0,  # Мимо
        1: 0.0,  # Полный промах
    },
    BOWLING: {
        6: 6.0,  # Strike!
        5: 3.0,  # Почти страйк
        4: 1.5,  # Хороший результат
        3: 0.0,  # Возврат ставки
        2: 0.0,  # Слабо
        1: 0.0,  # Промах
    },
    FOOTBALL: {
        5: 5.0,  # Гол в девятку
        4: 2.5,  # Гол
        3: 1.0,  # Попал в ворота
        2: 0.0,  # Мимо ворот
        1: 0.0,  # Промах
    },
    SLOT_MACHINE: {
        # Telegram slot machine results (from official lookup table):
        # 64 = Seven Seven Seven - JACKPOT!
        # 1, 22, 43 = Three matching symbols (Bar/Grape/Lemon)
        # 16, 32, 48 = Two sevens + other symbol
        # All others = Loss
        64: 50.0,  # 🎰 JACKPOT! 7️⃣7️⃣7️⃣
        1: 10.0,  # Три BAR 🍫🍫🍫
        22: 10.0,  # Три винограда 🍇🍇🍇
        43: 10.0,  # Три лимона 🍋🍋🍋
        16: 3.0,  # Две семёрки 7️⃣7️⃣
        32: 3.0,  # Две семёрки 7️⃣7️⃣
        48: 3.0,  # Две семёрки 7️⃣7️⃣
    },
}

# Result messages
RESULT_MESSAGES = {
    DICE: {
        6: "🎲 Джекпот! Выпало 6!",
        5: "🎲 Отлично! Выпало 5",
        4: "🎲 Неплохо! Выпало 4",
        3: "🎲 Средне. Выпало 3",
        2: "🎲 Плохо. Выпало 2",
        1: "🎲 Проигрыш. Выпало 1",
    },
    DARTS: {
        6: "🎯 ЯБЛОЧКО! Идеальный бросок!",
        5: "🎯 Отлично! Почти в центр",
        4: "🎯 Неплохо! Близко к центру",
        3: "🎯 Средне. Попал в мишень",
        2: "🎯 Мимо мишени",
        1: "🎯 Полный промах!",
    },
    BASKETBALL: {
        5: "🏀 SWISH! Идеальный бросок!",
        4: "🏀 Отлично! Чистое попадание",
        3: "🏀 Попал в кольцо",
        2: "🏀 Мимо кольца",
        1: "🏀 Воздух! Промах",
    },
    BOWLING: {
        6: "🎳 СТРАЙК! Все кегли!",
        5: "🎳 Почти страйк! 9 кеглей",
        4: "🎳 Хорошо! 7-8 кеглей",
        3: "🎳 Средне. 5-6 кеглей",
        2: "🎳 Слабо. 2-3 кегли",
        1: "🎳 Промах! 0 кеглей",
    },
    FOOTBALL: {
        5: "⚽ ГОЛ В ДЕВЯТКУ! Красота!",
        4: "⚽ ГОООЛ! Чистый удар!",
        3: "⚽ Гол! Попал в ворота",
        2: "⚽ Мимо ворот",
        1: "⚽ Промах! Аут",
    },
    SLOT_MACHINE: {
        64: "🎰 ДЖЕКПОТ! 7️⃣7️⃣7️⃣",
        1: "🎰 Три BAR! 🍫🍫🍫",
        22: "🎰 Три винограда! 🍇🍇🍇",
        43: "🎰 Три лимона! 🍋🍋🍋",
        16: "🎰 Две семёрки! 7️⃣7️⃣",
        32: "🎰 Две семёрки! 7️⃣7️⃣",
        48: "🎰 Две семёрки! 7️⃣7️⃣",
    },
}


class CasinoService:
    """Service for casino games."""

    @staticmethod
    def can_bet(db: Session, user_id: int, amount: int) -> Tuple[bool, Optional[str]]:
        """Check if user can place a bet.

        Returns:
            (can_bet, error_message)
        """
        if amount < MIN_BET:
            return False, f"Минимальная ставка: {format_diamonds(MIN_BET)}"

        if amount > MAX_BET:
            return False, f"Максимальная ставка: {format_diamonds(MAX_BET)}"

        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            return False, "Пользователь не найден"

        if user.balance < amount:
            return False, f"Недостаточно алмазов. У тебя: {format_diamonds(user.balance)}"

        return True, None

    @staticmethod
    def calculate_winnings(game_type: str, result: int, bet_amount: int) -> Tuple[int, float]:
        """Calculate winnings based on game result.

        Returns:
            (winnings, multiplier)
        """
        multiplier = PAYOUTS.get(game_type, {}).get(result, 0.0)
        winnings = int(bet_amount * multiplier)
        return winnings, multiplier

    @staticmethod
    def get_result_message(game_type: str, result: int, bet_amount: int, winnings: int, multiplier: float) -> str:
        """Generate result message for game.

        Returns:
            Formatted message string
        """
        result_text = RESULT_MESSAGES.get(game_type, {}).get(result, "Результат")

        message = f"<b>🎰 Казино</b>\n\n{result_text}\n\n"

        if winnings > bet_amount:
            # Win
            profit = winnings - bet_amount
            message += (
                f"💰 Ставка: {format_diamonds(bet_amount)}\n"
                f"✅ Выигрыш: {format_diamonds(winnings)} (x{multiplier})\n"
                f"💎 Прибыль: +{format_diamonds(profit)}"
            )
        elif winnings == bet_amount:
            # Return bet
            message += f"💰 Ставка возвращена: {format_diamonds(bet_amount)}"
        else:
            # Loss
            message += f"💰 Ставка: {format_diamonds(bet_amount)}\n" f"❌ Проигрыш: -{format_diamonds(bet_amount)}"

        return message

    @staticmethod
    def play_game(db: Session, user_id: int, game_type: str, bet_amount: int, dice_value: int) -> Tuple[bool, str, int, int]:
        """Process any casino game.

        Args:
            game_type: Type of game (dice, darts, basketball, slot_machine)
            dice_value: The result from Telegram API
            bet_amount: Bet amount

        Returns:
            (success, message, winnings, final_balance)
        """
        user = db.query(User).filter(User.telegram_id == user_id).first()

        # Deduct bet
        user.balance -= bet_amount

        # Calculate winnings
        winnings, multiplier = CasinoService.calculate_winnings(game_type, dice_value, bet_amount)

        # Add winnings
        user.balance += winnings

        db.commit()

        # Generate message
        message = CasinoService.get_result_message(game_type, dice_value, bet_amount, winnings, multiplier)
        message += f"\n\n💰 Баланс: {format_diamonds(user.balance)}"

        logger.info(
            f"{game_type.capitalize()} game played",
            user_id=user_id,
            bet=bet_amount,
            result=dice_value,
            winnings=winnings,
            balance=user.balance,
        )

        return True, message, winnings, user.balance
