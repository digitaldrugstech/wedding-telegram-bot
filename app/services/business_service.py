"""Business service for Wedding Telegram Bot."""

from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import structlog
from sqlalchemy.orm import Session

from app.database.models import Business, User
from app.utils.formatters import format_diamonds

logger = structlog.get_logger()

# Business types with prices and weekly payouts
BUSINESS_TYPES = {
    1: {"name": "🏪 Палатка на рынке", "price": 1000, "weekly_payout": 200},
    2: {"name": "🏬 Магазин на спавне", "price": 5000, "weekly_payout": 1000},
    3: {"name": "🏦 Филиал банка", "price": 25000, "weekly_payout": 5000},
    4: {"name": "🏙️ Свой город", "price": 150000, "weekly_payout": 30000},
}

MAX_BUSINESSES_PER_TYPE = 3
SELL_REFUND_PERCENTAGE = 0.7  # 70% refund


class BusinessService:
    """Service for business operations."""

    @staticmethod
    def can_buy_business(db: Session, user_id: int, business_type: int) -> Tuple[bool, Optional[str]]:
        """Check if user can buy business.

        Returns:
            (can_buy, error_message)
        """
        if business_type not in BUSINESS_TYPES:
            return False, "Неверный тип бизнеса"

        # Check how many of this type user already has
        count = db.query(Business).filter(
            Business.user_id == user_id,
            Business.business_type == business_type
        ).count()

        if count >= MAX_BUSINESSES_PER_TYPE:
            return False, f"Максимум {MAX_BUSINESSES_PER_TYPE} бизнеса каждого типа"

        # Check balance
        user = db.query(User).filter(User.telegram_id == user_id).first()
        price = BUSINESS_TYPES[business_type]["price"]

        if user.balance < price:
            return False, f"Недостаточно алмазов. Нужно: {format_diamonds(price)}"

        return True, None

    @staticmethod
    def buy_business(db: Session, user_id: int, business_type: int) -> Tuple[bool, str]:
        """Buy a business.

        Returns:
            (success, message)
        """
        user = db.query(User).filter(User.telegram_id == user_id).first()
        price = BUSINESS_TYPES[business_type]["price"]

        # Deduct payment
        user.balance -= price

        # Create business
        business = Business(
            user_id=user_id,
            business_type=business_type,
            purchase_price=price,
            purchased_at=datetime.utcnow(),
            last_payout_at=datetime.utcnow(),
        )
        db.add(business)
        db.commit()

        business_name = BUSINESS_TYPES[business_type]["name"]
        weekly_payout = BUSINESS_TYPES[business_type]["weekly_payout"]

        message = (
            f"💼 <b>Бизнес куплен</b>\n\n"
            f"{business_name}\n"
            f"💰 Цена: {format_diamonds(price)}\n"
            f"📈 Доход: {format_diamonds(weekly_payout)}/неделя\n\n"
            f"💰 Баланс: {format_diamonds(user.balance)}"
        )

        logger.info("Business purchased", user_id=user_id, business_type=business_type, price=price)

        return True, message

    @staticmethod
    def get_user_businesses(db: Session, user_id: int) -> List[dict]:
        """Get all user's businesses.

        Returns:
            List of business dicts
        """
        businesses = db.query(Business).filter(Business.user_id == user_id).all()

        result = []
        for business in businesses:
            business_data = BUSINESS_TYPES[business.business_type]
            result.append({
                "id": business.id,
                "business_type": business.business_type,
                "name": business_data["name"],
                "price": business.purchase_price,
                "weekly_payout": business_data["weekly_payout"],
                "purchased_at": business.purchased_at,
                "last_payout_at": business.last_payout_at,
            })

        return result

    @staticmethod
    def sell_business(db: Session, user_id: int, business_id: int) -> Tuple[bool, str]:
        """Sell business for 70% refund.

        Returns:
            (success, message)
        """
        business = db.query(Business).filter(
            Business.id == business_id,
            Business.user_id == user_id
        ).first()

        if not business:
            return False, "Бизнес не найден"

        user = db.query(User).filter(User.telegram_id == user_id).first()

        # Calculate refund
        refund = int(business.purchase_price * SELL_REFUND_PERCENTAGE)

        # Add refund
        user.balance += refund

        # Delete business
        db.delete(business)
        db.commit()

        business_name = BUSINESS_TYPES[business.business_type]["name"]
        message = (
            f"💼 <b>Бизнес продан</b>\n\n"
            f"{business_name}\n"
            f"💰 Возврат (70%): {format_diamonds(refund)}\n\n"
            f"💰 Баланс: {format_diamonds(user.balance)}"
        )

        logger.info("Business sold", user_id=user_id, business_id=business_id, refund=refund)

        return True, message

    @staticmethod
    def process_payouts(db: Session):
        """Process weekly payouts for all businesses (called by scheduler).

        Returns:
            Number of payouts processed
        """
        now = datetime.utcnow()
        one_week_ago = now - timedelta(weeks=1)

        # Get businesses that need payout
        businesses = db.query(Business).filter(
            Business.last_payout_at <= one_week_ago
        ).all()

        count = 0
        for business in businesses:
            user = db.query(User).filter(User.telegram_id == business.user_id).first()
            payout = BUSINESS_TYPES[business.business_type]["weekly_payout"]

            user.balance += payout
            business.last_payout_at = now

            count += 1
            logger.info("Business payout", user_id=user.telegram_id, business_id=business.id, payout=payout)

        db.commit()

        return count
