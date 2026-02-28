"""Business service - passive income system."""

from typing import Tuple

import structlog
from sqlalchemy.orm import Session

from app.database.models import Business, User
from app.utils.formatters import format_diamonds

logger = structlog.get_logger()

# Business types and prices (ROI with 10% base maintenance: ~7-8 weeks break-even)
# 12 business types available; progressive maintenance scales with portfolio size
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
MAX_BUSINESSES_TOTAL = 5  # Maximum 5 businesses total (prevents inflation spiral)
SELL_REFUND_PERCENTAGE = 0.70  # 70% refund

# Business upgrade system: level 1 (base), level 2 (+50%), level 3 (+100%)
UPGRADE_COSTS = {
    2: 2.0,  # 2x purchase price to upgrade to level 2
    3: 5.0,  # 5x purchase price to upgrade to level 3
}
UPGRADE_MULTIPLIERS = {
    1: 1.0,
    2: 1.5,  # +50% payout
    3: 2.0,  # +100% payout
}
MAX_UPGRADE_LEVEL = 3


def get_maintenance_rate(business_count: int) -> float:
    """Progressive maintenance — scales with portfolio size to prevent income spiral."""
    if business_count <= 2:
        return 0.10  # 10% for 1-2 businesses
    elif business_count == 3:
        return 0.15  # 15% for 3
    elif business_count == 4:
        return 0.22  # 22% for 4
    else:
        return 0.30  # 30% for 5+


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

        # Calculate break-even with progressive maintenance (including this new business)
        new_count = db.query(Business).filter(Business.user_id == user_id).count()
        rate = get_maintenance_rate(new_count)
        net_payout = business_info["weekly_payout"] - int(business_info["weekly_payout"] * rate)
        weeks_to_break_even = round(business_price / net_payout, 1) if net_payout > 0 else 99
        maintenance_pct = int(rate * 100)

        message = (
            f"💼 <b>Поздравляем с покупкой!</b>\n\n"
            f"{business_info['name']}\n"
            f"💰 Цена: {format_diamonds(business_price)}\n"
            f"📈 Доход: {format_diamonds(net_payout)}/неделя\n"
            f"🔧 Обслуживание: {maintenance_pct}% ({new_count} из {MAX_BUSINESSES_TOTAL})\n\n"
            f"💡 Окупаемость: ~{weeks_to_break_even} недель\n\n"
            f"💰 Остаток: {format_diamonds(user.balance)}"
        )

        return True, message

    @staticmethod
    def get_user_businesses(db: Session, user_id: int) -> list:
        """Get all businesses for a user."""
        businesses = db.query(Business).filter(Business.user_id == user_id).all()
        rate = get_maintenance_rate(len(businesses))

        result = []
        for business in businesses:
            business_info = BUSINESS_TYPES.get(business.business_type, BUSINESS_TYPES[1])
            upgrade_mult = UPGRADE_MULTIPLIERS.get(business.upgrade_level, 1.0)
            gross = int(business_info["weekly_payout"] * upgrade_mult)
            net = gross - int(gross * rate)
            result.append(
                {
                    "id": business.id,
                    "name": business_info["name"],
                    "type": business.business_type,
                    "purchase_price": business.purchase_price,
                    "upgrade_level": business.upgrade_level,
                    "weekly_payout": net,
                    "gross_payout": gross,
                }
            )

        return result

    @staticmethod
    def upgrade_business(db: Session, business_id: int, user_id: int) -> Tuple[bool, str]:
        """Upgrade a business to the next level."""
        business = db.query(Business).filter(Business.id == business_id, Business.user_id == user_id).first()
        if not business:
            return False, "Бизнес не найден"

        current_level = business.upgrade_level
        if current_level >= MAX_UPGRADE_LEVEL:
            return False, f"Максимальный уровень ({MAX_UPGRADE_LEVEL})"

        next_level = current_level + 1
        business_info = BUSINESS_TYPES.get(business.business_type, BUSINESS_TYPES[1])
        upgrade_cost = int(business_info["price"] * UPGRADE_COSTS[next_level])

        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user or user.balance < upgrade_cost:
            return False, f"Нужно {format_diamonds(upgrade_cost)}"

        user.balance -= upgrade_cost
        business.upgrade_level = next_level

        # Calculate new payout
        all_biz = db.query(Business).filter(Business.user_id == user_id).count()
        rate = get_maintenance_rate(all_biz)
        new_mult = UPGRADE_MULTIPLIERS[next_level]
        gross = int(business_info["weekly_payout"] * new_mult)
        net = gross - int(gross * rate)
        bonus_pct = int((new_mult - 1) * 100)

        logger.info("Business upgraded", user_id=user_id, business_id=business_id, level=next_level)

        message = (
            f"⬆️ <b>Бизнес прокачан!</b>\n\n"
            f"{business_info['name']} → уровень {next_level}\n"
            f"💰 Цена: {format_diamonds(upgrade_cost)}\n"
            f"📈 Доход: {format_diamonds(net)}/нед (+{bonus_pct}%)\n\n"
            f"💰 Остаток: {format_diamonds(user.balance)}"
        )
        return True, message

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
        from collections import defaultdict

        all_businesses = db.query(Business).all()

        # Group by user for progressive maintenance
        user_businesses = defaultdict(list)
        for biz in all_businesses:
            user_businesses[biz.user_id].append(biz)

        payout_count = 0
        total_paid = 0

        for user_id, businesses in user_businesses.items():
            rate = get_maintenance_rate(len(businesses))
            user = db.query(User).filter(User.telegram_id == user_id).first()
            if not user:
                continue

            for business in businesses:
                business_info = BUSINESS_TYPES.get(business.business_type, BUSINESS_TYPES[1])
                upgrade_mult = UPGRADE_MULTIPLIERS.get(business.upgrade_level, 1.0)
                gross_payout = int(business_info["weekly_payout"] * upgrade_mult)
                maintenance = int(gross_payout * rate)
                payout = gross_payout - maintenance

                user.balance += payout
                payout_count += 1
                total_paid += payout

        logger.info("Business payouts completed", businesses=payout_count, total_paid=total_paid)

        return payout_count, total_paid
