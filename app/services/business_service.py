"""Business service - passive income system."""

from typing import Tuple

import structlog
from sqlalchemy.orm import Session

from app.database.models import Business, User
from app.utils.formatters import format_diamonds

logger = structlog.get_logger()

# Business types and prices (balanced ROI: 12-17% per week, 6-8 weeks to break even)
# 12 businesses total (3x original 4)
BUSINESS_TYPES = {
    # Tier 1: Starter (1,000 - 5,000 💎)
    1: {"name": "🏪 Палатка на рынке", "price": 1000, "weekly_payout": 170},  # 17% ROI, 5.9 weeks
    2: {"name": "🌭 Киоск с хот-догами", "price": 2000, "weekly_payout": 320},  # 16% ROI, 6.3 weeks
    3: {"name": "☕ Кофейня", "price": 3500, "weekly_payout": 540},  # 15% ROI, 6.5 weeks
    4: {"name": "🏬 Магазин на спавне", "price": 5000, "weekly_payout": 750},  # 15% ROI, 6.7 weeks
    # Tier 2: Medium (10,000 - 50,000 💎)
    5: {"name": "🍕 Пиццерия", "price": 10000, "weekly_payout": 1450},  # 14.5% ROI, 6.9 weeks
    6: {"name": "🎮 Игровой клуб", "price": 20000, "weekly_payout": 2800},  # 14% ROI, 7.1 weeks
    7: {"name": "🏦 Филиал банка", "price": 25000, "weekly_payout": 3400},  # 13.6% ROI, 7.4 weeks
    8: {"name": "🏨 Отель", "price": 50000, "weekly_payout": 6500},  # 13% ROI, 7.7 weeks
    # Tier 3: Premium (100,000 - 500,000 💎)
    9: {"name": "🏙️ Свой город", "price": 150000, "weekly_payout": 19000},  # 12.7% ROI, 7.9 weeks
    10: {"name": "🏭 Завод", "price": 250000, "weekly_payout": 31000},  # 12.4% ROI, 8.1 weeks
    11: {"name": "✈️ Авиакомпания", "price": 400000, "weekly_payout": 48000},  # 12% ROI, 8.3 weeks
    12: {"name": "🌐 IT-корпорация", "price": 500000, "weekly_payout": 60000},  # 12% ROI, 8.3 weeks
}

MAX_BUSINESSES_PER_TYPE = 3  # Maximum 3 businesses of each type
MAX_BUSINESSES_TOTAL = 8  # Maximum 8 businesses total (prevents inflation spiral)
SELL_REFUND_PERCENTAGE = 0.70  # 70% refund
MAINTENANCE_RATE = 0.08  # 8% maintenance costs (deducted from weekly payout)


class BusinessService:
    """Service for managing businesses."""

    @staticmethod
    def can_buy_business(db: Session, user_id: int, business_type: int) -> Tuple[bool, str]:
        """Check if user can buy a business."""
        # Validate business type
        if business_type not in BUSINESS_TYPES:
            return False, "Неверный тип бизнеса"

        # Check global business cap
        total_businesses = db.query(Business).filter(Business.user_id == user_id).count()
        if total_businesses >= MAX_BUSINESSES_TOTAL:
            return False, f"Максимум {MAX_BUSINESSES_TOTAL} бизнесов"

        # Check if user already has 3 of this type
        user_businesses = (
            db.query(Business).filter(Business.user_id == user_id, Business.business_type == business_type).count()
        )

        if user_businesses >= MAX_BUSINESSES_PER_TYPE:
            return False, f"Максимум {MAX_BUSINESSES_PER_TYPE} бизнеса каждого типа"

        # Check balance
        user = db.query(User).filter(User.telegram_id == user_id).first()
        business_price = BUSINESS_TYPES[business_type]["price"]

        if user.balance < business_price:
            return False, f"Недостаточно алмазов (нужно {format_diamonds(business_price)})"

        return True, ""

    @staticmethod
    def buy_business(db: Session, user_id: int, business_type: int) -> Tuple[bool, str]:
        """Buy a business."""
        # Get business details
        business_info = BUSINESS_TYPES[business_type]
        business_price = business_info["price"]

        # Get user and charge
        user = db.query(User).filter(User.telegram_id == user_id).first()
        user.balance -= business_price

        # Create business
        business = Business(user_id=user_id, business_type=business_type, purchase_price=business_price)

        db.add(business)
        db.flush()

        logger.info("Business purchased", user_id=user_id, business_type=business_type, price=business_price)

        net_payout = business_info["weekly_payout"] - int(business_info["weekly_payout"] * MAINTENANCE_RATE)
        weeks_to_break_even = round(business_price / net_payout, 1) if net_payout > 0 else 99

        message = (
            f"💼 <b>Поздравляем с покупкой!</b>\n\n"
            f"{business_info['name']}\n"
            f"💰 Цена: {format_diamonds(business_price)}\n"
            f"📈 Доход: {format_diamonds(net_payout)}/неделя (за вычетом обслуживания)\n\n"
            f"💡 Окупаемость: ~{weeks_to_break_even} недель\n\n"
            f"💰 Остаток: {format_diamonds(user.balance)}"
        )

        return True, message

    @staticmethod
    def get_user_businesses(db: Session, user_id: int) -> list:
        """Get all businesses for a user."""
        businesses = db.query(Business).filter(Business.user_id == user_id).all()

        result = []
        for business in businesses:
            business_info = BUSINESS_TYPES.get(business.business_type, BUSINESS_TYPES[1])
            gross = business_info["weekly_payout"]
            net = gross - int(gross * MAINTENANCE_RATE)
            result.append(
                {
                    "id": business.id,
                    "name": business_info["name"],
                    "type": business.business_type,
                    "purchase_price": business.purchase_price,
                    "weekly_payout": net,
                }
            )

        return result

    @staticmethod
    def sell_business(db: Session, business_id: int, user_id: int) -> Tuple[bool, str]:
        """Sell business (70% refund)."""
        # Get business
        business = db.query(Business).filter(Business.id == business_id, Business.user_id == user_id).first()

        if not business:
            return False, "Бизнес не найден"

        # Calculate refund (70%)
        refund_amount = int(business.purchase_price * SELL_REFUND_PERCENTAGE)

        # Get user and refund
        user = db.query(User).filter(User.telegram_id == user_id).first()
        user.balance += refund_amount

        # Delete business
        business_name = BUSINESS_TYPES.get(business.business_type, BUSINESS_TYPES[1])["name"]
        db.delete(business)

        logger.info("Business sold", user_id=user_id, business_id=business_id, refund=refund_amount)

        message = (
            f"💼 <b>Бизнес продан</b>\n\n"
            f"{business_name}\n"
            f"💰 Возврат: {format_diamonds(refund_amount)} (70%)\n"
            f"💰 Твой баланс: {format_diamonds(user.balance)}"
        )

        return True, message

    @staticmethod
    def calculate_total_income(db: Session, user_id: int) -> int:
        """Calculate total weekly income from all businesses."""
        businesses = BusinessService.get_user_businesses(db, user_id)
        total = sum(b["weekly_payout"] for b in businesses)
        return total

    @staticmethod
    def payout_all_businesses(db: Session):
        """Weekly payout for all businesses (scheduled task)."""
        all_businesses = db.query(Business).all()

        payout_count = 0
        total_paid = 0

        for business in all_businesses:
            business_info = BUSINESS_TYPES.get(business.business_type, BUSINESS_TYPES[1])
            gross_payout = business_info["weekly_payout"]
            maintenance = int(gross_payout * MAINTENANCE_RATE)
            payout = gross_payout - maintenance

            # Get user and pay
            user = db.query(User).filter(User.telegram_id == business.user_id).first()
            if user:
                user.balance += payout
                payout_count += 1
                total_paid += payout



        logger.info("Business payouts completed", businesses=payout_count, total_paid=total_paid)

        return payout_count, total_paid
