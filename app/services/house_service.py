"""House service - buying, selling, and protection mechanics."""

from typing import Optional, Tuple

import structlog
from sqlalchemy.orm import Session

from app.database.models import House, Marriage, User
from app.utils.formatters import format_diamonds

logger = structlog.get_logger()

# House types and prices
HOUSE_TYPES = {
    1: {"name": "🏚️ Хибара", "price": 1000, "protection": 10},
    2: {"name": "🏡 Деревянный домик", "price": 5000, "protection": 25},
    3: {"name": "🏠 Каменный дом", "price": 20000, "protection": 40},
    4: {"name": "🏘️ Коттедж", "price": 100000, "protection": 60},
    5: {"name": "🏰 Особняк", "price": 500000, "protection": 80},
    6: {"name": "🏯 Замок", "price": 2000000, "protection": 95},
}

SELL_REFUND_PERCENTAGE = 0.70  # 70% refund


class HouseService:
    """Service for managing houses."""

    @staticmethod
    def can_buy_house(db: Session, user_id: int, house_type: int) -> Tuple[bool, str]:
        """Check if user can buy a house."""
        # Validate house type
        if house_type not in HOUSE_TYPES:
            return False, "Неверный тип дома"

        # Check if married
        marriage = (
            db.query(Marriage)
            .filter(
                Marriage.is_active.is_(True),
                ((Marriage.partner1_id == user_id) | (Marriage.partner2_id == user_id)),
            )
            .first()
        )

        if not marriage:
            return False, "Нужен брак чтобы купить дом"

        # Check if marriage already has a house
        existing_house = db.query(House).filter(House.marriage_id == marriage.id).first()

        if existing_house:
            return False, "У твоей семьи уже есть дом"

        # Check balance
        user = db.query(User).filter(User.telegram_id == user_id).first()
        house_price = HOUSE_TYPES[house_type]["price"]

        if user.balance < house_price:
            return False, f"Недостаточно алмазов (нужно {format_diamonds(house_price)})"

        return True, ""

    @staticmethod
    def buy_house(db: Session, user_id: int, house_type: int) -> Tuple[bool, str, Optional[int]]:
        """Buy a house."""
        # Get marriage
        marriage = (
            db.query(Marriage)
            .filter(
                Marriage.is_active.is_(True),
                ((Marriage.partner1_id == user_id) | (Marriage.partner2_id == user_id)),
            )
            .first()
        )

        if not marriage:
            return False, "Нужен брак чтобы купить дом", None

        # Get house details
        house_info = HOUSE_TYPES[house_type]
        house_price = house_info["price"]

        # Get user and charge
        user = db.query(User).filter(User.telegram_id == user_id).first()
        user.balance -= house_price

        # Create house
        house = House(marriage_id=marriage.id, house_type=house_type, purchase_price=house_price)

        db.add(house)
        db.flush()
        db.refresh(house)

        logger.info(
            "House purchased", user_id=user_id, marriage_id=marriage.id, house_type=house_type, price=house_price
        )

        message = (
            f"🏠 <b>Поздравляем с покупкой!</b>\n\n"
            f"{house_info['name']}\n"
            f"💰 Цена: {format_diamonds(house_price)}\n"
            f"🛡️ Защита: {house_info['protection']}%\n\n"
            f"💡 Дом защищает детей от похищения\n\n"
            f"💰 Остаток: {format_diamonds(user.balance)}"
        )

        return True, message, house.id

    @staticmethod
    def can_sell_house(db: Session, user_id: int) -> Tuple[bool, str, Optional[int]]:
        """Check if user can sell their house."""
        # Get marriage
        marriage = (
            db.query(Marriage)
            .filter(
                Marriage.is_active.is_(True),
                ((Marriage.partner1_id == user_id) | (Marriage.partner2_id == user_id)),
            )
            .first()
        )

        if not marriage:
            return False, "Нужен брак чтобы управлять домом", None

        # Check if house exists
        house = db.query(House).filter(House.marriage_id == marriage.id).first()

        if not house:
            return False, "У твоей семьи нет дома", None

        return True, "", house.id

    @staticmethod
    def sell_house(db: Session, user_id: int) -> Tuple[bool, str]:
        """Sell house (70% refund)."""
        # Get marriage
        marriage = (
            db.query(Marriage)
            .filter(
                Marriage.is_active.is_(True),
                ((Marriage.partner1_id == user_id) | (Marriage.partner2_id == user_id)),
            )
            .first()
        )

        if not marriage:
            return False, "Нужен брак чтобы управлять домом"

        # Get house
        house = db.query(House).filter(House.marriage_id == marriage.id).first()

        if not house:
            return False, "У твоей семьи нет дома"

        # Calculate refund (70%)
        refund_amount = int(house.purchase_price * SELL_REFUND_PERCENTAGE)

        # Get user and refund
        user = db.query(User).filter(User.telegram_id == user_id).first()
        user.balance += refund_amount

        # Delete house
        db.delete(house)


        logger.info("House sold", user_id=user_id, marriage_id=marriage.id, refund=refund_amount)

        message = (
            f"🏠 <b>Дом продан</b>\n\n"
            f"💰 Возврат: {format_diamonds(refund_amount)} (70%)\n"
            f"💰 Твой баланс: {format_diamonds(user.balance)}"
        )

        return True, message

    @staticmethod
    def get_house_info(db: Session, house_id: int) -> dict:
        """Get house information."""
        house = db.query(House).filter(House.id == house_id).first()

        if not house:
            return {"name": "Дом не найден", "price": 0, "protection": 0}

        house_info = HOUSE_TYPES.get(house.house_type, HOUSE_TYPES[1])

        return {
            "name": house_info["name"],
            "price": house.purchase_price,
            "protection": house_info["protection"],
            "type": house.house_type,
        }

    @staticmethod
    def get_protection_bonus(db: Session, marriage_id: int) -> int:
        """Get protection bonus from house (for kidnapping mechanics)."""
        house = db.query(House).filter(House.marriage_id == marriage_id).first()

        if not house:
            return 0

        house_info = HOUSE_TYPES.get(house.house_type, HOUSE_TYPES[1])
        return house_info["protection"]

    @staticmethod
    def has_house(db: Session, marriage_id: int) -> bool:
        """Check if marriage has a house."""
        house = db.query(House).filter(House.marriage_id == marriage_id).first()
        return house is not None
