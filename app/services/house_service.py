"""House service for Wedding Telegram Bot."""

from datetime import datetime
from typing import Optional, Tuple

import structlog
from sqlalchemy.orm import Session

from app.database.models import House, Marriage, User
from app.utils.formatters import format_diamonds

logger = structlog.get_logger()

# House types with prices and protection levels
HOUSE_TYPES = {
    1: {"name": "🏚️ Хибара", "price": 1000, "protection": 0},
    2: {"name": "🏡 Деревянный домик", "price": 5000, "protection": 10},
    3: {"name": "🏠 Каменный дом", "price": 20000, "protection": 30},
    4: {"name": "🏘️ Коттедж", "price": 100000, "protection": 50},
    5: {"name": "🏰 Особняк", "price": 500000, "protection": 75},
    6: {"name": "🏯 Замок", "price": 2000000, "protection": 95},
}

SELL_REFUND_PERCENTAGE = 0.7  # 70% refund on sale


class HouseService:
    """Service for house operations."""

    @staticmethod
    def can_buy_house(db: Session, user_id: int, house_type: int) -> Tuple[bool, Optional[str]]:
        """Check if user can buy house.

        Returns:
            (can_buy, error_message)
        """
        # Validate house type
        if house_type not in HOUSE_TYPES:
            return False, "Неверный тип дома"

        # Check if user is married
        marriage = (
            db.query(Marriage)
            .filter(
                (Marriage.partner1_id == user_id) | (Marriage.partner2_id == user_id),
                Marriage.is_active == True,
            )
            .first()
        )

        if not marriage:
            return False, "Нужен брак чтобы купить дом"

        # Check if marriage already has house
        existing_house = db.query(House).filter(House.marriage_id == marriage.id).first()
        if existing_house:
            return False, f"У семьи уже есть дом: {HOUSE_TYPES[existing_house.house_type]['name']}"

        # Check balance
        user = db.query(User).filter(User.telegram_id == user_id).first()
        price = HOUSE_TYPES[house_type]["price"]

        if user.balance < price:
            return False, f"Недостаточно алмазов. Нужно: {format_diamonds(price)}"

        return True, None

    @staticmethod
    def buy_house(db: Session, user_id: int, house_type: int) -> Tuple[bool, str, int]:
        """Buy a house.

        Returns:
            (success, message, house_id)
        """
        # Get marriage
        marriage = (
            db.query(Marriage)
            .filter(
                (Marriage.partner1_id == user_id) | (Marriage.partner2_id == user_id),
                Marriage.is_active == True,
            )
            .first()
        )

        user = db.query(User).filter(User.telegram_id == user_id).first()
        price = HOUSE_TYPES[house_type]["price"]

        # Deduct payment
        user.balance -= price

        # Create house
        house = House(
            marriage_id=marriage.id,
            house_type=house_type,
            purchase_price=price,
            purchased_at=datetime.utcnow(),
        )
        db.add(house)
        db.commit()

        house_name = HOUSE_TYPES[house_type]["name"]
        message = (
            f"🏠 <b>Дом куплен</b>\n\n"
            f"{house_name}\n"
            f"💰 {format_diamonds(price)}\n\n"
            f"💰 Баланс: {format_diamonds(user.balance)}"
        )

        logger.info("House purchased", user_id=user_id, house_type=house_type, price=price)

        return True, message, house.id

    @staticmethod
    def can_sell_house(db: Session, user_id: int) -> Tuple[bool, Optional[str], Optional[int]]:
        """Check if user can sell house.

        Returns:
            (can_sell, error_message, house_id)
        """
        # Get marriage
        marriage = (
            db.query(Marriage)
            .filter(
                (Marriage.partner1_id == user_id) | (Marriage.partner2_id == user_id),
                Marriage.is_active == True,
            )
            .first()
        )

        if not marriage:
            return False, "Не в браке", None

        # Check if has house
        house = db.query(House).filter(House.marriage_id == marriage.id).first()

        if not house:
            return False, "У семьи нет дома", None

        return True, None, house.id

    @staticmethod
    def sell_house(db: Session, user_id: int) -> Tuple[bool, str]:
        """Sell house for 70% refund.

        Returns:
            (success, message)
        """
        # Get marriage
        marriage = (
            db.query(Marriage)
            .filter(
                (Marriage.partner1_id == user_id) | (Marriage.partner2_id == user_id),
                Marriage.is_active == True,
            )
            .first()
        )

        house = db.query(House).filter(House.marriage_id == marriage.id).first()
        user = db.query(User).filter(User.telegram_id == user_id).first()

        # Calculate refund
        refund = int(house.purchase_price * SELL_REFUND_PERCENTAGE)

        # Add refund to user
        user.balance += refund

        # Delete house
        db.delete(house)
        db.commit()

        house_name = HOUSE_TYPES[house.house_type]["name"]
        message = (
            f"🏠 <b>Дом продан</b>\n\n"
            f"{house_name}\n"
            f"💰 Возврат (70%): {format_diamonds(refund)}\n\n"
            f"💰 Баланс: {format_diamonds(user.balance)}"
        )

        logger.info("House sold", user_id=user_id, house_type=house.house_type, refund=refund)

        return True, message

    @staticmethod
    def get_house_info(db: Session, marriage_id: int) -> Optional[dict]:
        """Get house info for marriage.

        Returns:
            House info dict or None
        """
        house = db.query(House).filter(House.marriage_id == marriage_id).first()

        if not house:
            return None

        house_data = HOUSE_TYPES[house.house_type]

        return {
            "house_type": house.house_type,
            "name": house_data["name"],
            "price": house.purchase_price,
            "protection": house_data["protection"],
            "purchased_at": house.purchased_at,
        }
